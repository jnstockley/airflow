import logging
import os
from datetime import timedelta, datetime

import requests
from airflow.decorators import task
from airflow.models import Variable, TaskInstance
from airflow.models.dag import dag

from cloudflare.cloudflare_api import get_dns_zone_id, get_all_a_record_ips, get_zero_trust_app_ids, get_app_policy_ids, \
    delete_app_policies, create_app_policy

logger = logging.getLogger(__name__)

default_args = {
    'owner': 'jackstockley',
    'retries': 0,
    'retry_delay': timedelta(minutes=5),
    'email': ['jack@jstockley.com'],
    'email_on_failure': True,
}

env = Variable.get("env")

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"

@dag(
    dag_id='Cloudflare-Apps',
    description='Update Cloudflare App allowed IP addresses',
    schedule_interval='@once' if env == 'dev' else '*/5 * * * *',
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=['cloudflare', 'infrastructure'],
)
def cloudflare_apps():
    @task()
    def get_all_ips(ti: TaskInstance):
        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            logger.info("Getting DNS zone ID")
            dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)

            logger.info("Getting All A record IPs")
            ips = get_all_a_record_ips(dns_zone_id, cloudflare_api_key)

            ti.xcom_push(key='dns_zone_id', value=dns_zone_id)
            ti.xcom_push(key='ips', value=ips)


        main()

    @task()
    def update_cloudflare_apps(ti: TaskInstance):
        dns_zone_id = ti.xcom_pull(key='dns_zone_id')
        ips: list[str] = ti.xcom_pull(key='ips')
        apps: list[str] = Variable.get("CLOUDFLARE_APPS").split('|')
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():

            for app in apps:
                app_id = get_zero_trust_app_ids(dns_zone_id, app, cloudflare_api_key)
                policy_ids = get_app_policy_ids(dns_zone_id, app_id, cloudflare_api_key)

                delete_app_policies(dns_zone_id, app_id, policy_ids, cloudflare_api_key)
                create_app_policy(dns_zone_id, app_id, ips, cloudflare_api_key)


        main()


    get_all_ips() >> update_cloudflare_apps()

cloudflare_apps()
