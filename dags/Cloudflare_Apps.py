import logging
from datetime import timedelta, datetime

import requests
from airflow.decorators import task
from airflow.models import Variable, TaskInstance
from airflow.models.dag import dag

from plugins.cloudflare.cloudflare_api import (
    get_dns_zone_id,
    get_zero_trust_app_ids,
    get_app_policy_ids,
    delete_app_policies,
    create_app_policy,
    get_dns_record_id,
    update_dns_record,
)


logger = logging.getLogger(__name__)

default_args = {
    "owner": "jackstockley",
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
    "email": ["jack@jstockley.com"],
    "email_on_failure": True,
}

env = Variable.get("env")

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


@dag(
    dag_id="Cloudflare-Apps",
    description="Update Cloudflare App allowed IP addresses",
    schedule_interval="@once" if env == "dev" else "*/5 * * * *",
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
)
def cloudflare_apps():
    @task()
    def get_all_ips(ti: TaskInstance):
        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")
        api_key = Variable.get("API_KEY")

        def get_ips_from_api(api_key: str):
            headers = {"x-api-key": api_key}
            response = requests.get("https://api.jstockley.com/ip/", headers=headers)
            if response.status_code != 200:
                logger.error(
                    f"Failed to get IPs from API. Status code: {response.status_code} -> "
                    f"{response.json()}"
                )
                raise ConnectionError(
                    f"Failed to get IPs from API. Status code: {response.status_code} -> "
                    f"{response.json()}"
                )
            return response.json()

        def main():
            logger.info("Getting DNS zone ID")
            dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)

            logger.info("Getting IPs from API")
            ips = get_ips_from_api(api_key)

            ti.xcom_push(key="dns_zone_id", value=dns_zone_id)
            ti.xcom_push(key="ips", value=ips)

        main()

    @task()
    def update_cloudflare_dns_record(ti: TaskInstance):
        ips = ti.xcom_pull(key="ips")

        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            for ipv4_address in ips:
                match ipv4_address["id"]:
                    case "racknerd":
                        cloudflare_dns_name = "vpn.jstockley.com"
                    case "iowa":
                        cloudflare_dns_name = "iowa.vpn.jstockley.com"
                    case "chicago":
                        cloudflare_dns_name = "chicago.vpn.jstockley.com"
                    case _:
                        cloudflare_dns_name = None

                if cloudflare_dns_name is None:
                    logger.error(f"Failed to get DNS zone name {ipv4_address['id']}")
                    continue

                logger.info("Getting DNS zone ID")
                dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)

                logger.info("Getting IPV4 DNS record ID")
                ipv4_record_id = get_dns_record_id(
                    dns_zone_id, cloudflare_dns_name, cloudflare_api_key, False
                )
                logger.info("Updating IPV4 DNS records")
                update_dns_record(
                    ipv4_address["ip_address"],
                    dns_zone_id,
                    ipv4_record_id,
                    cloudflare_dns_name,
                    cloudflare_api_key,
                    False,
                )

        main()

    @task()
    def update_cloudflare_apps(ti: TaskInstance):
        dns_zone_id = ti.xcom_pull(key="dns_zone_id")
        ips_dict: dict = ti.xcom_pull(key="ips")
        apps: list[str] = Variable.get("CLOUDFLARE_APPS").split("|")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            ips = [item["ip_address"] for item in ips_dict if "ip_address" in item]

            for app in apps:
                app_id = get_zero_trust_app_ids(dns_zone_id, app, cloudflare_api_key)
                policy_ids = get_app_policy_ids(dns_zone_id, app_id, cloudflare_api_key)

                delete_app_policies(dns_zone_id, app_id, policy_ids, cloudflare_api_key)
                create_app_policy(dns_zone_id, app_id, ips, cloudflare_api_key)

        main()

    get_all_ips() >> update_cloudflare_dns_record() >> update_cloudflare_apps()


cloudflare_apps()
