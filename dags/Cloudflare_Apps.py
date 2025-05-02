import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.smtp.notifications.smtp import SmtpNotifier
from airflow.sdk import Variable, dag, task

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
env = Variable.get("env")


default_args = {
    "owner": "jackstockley",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


@dag(
    dag_id="Cloudflare-Apps",
    description="Update Cloudflare App allowed IP addresses",
    schedule="*/5 * * * *" if not env == "dev" else None,
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=SmtpNotifier(
        to="jack@jstockley.com",
        smtp_conn_id="SMTP"
    )
)
def cloudflare_apps():
    @task
    def get_all_ips(ti=None):
        api_key = Variable.get("API_KEY")

        logger.info("Getting IPs from API")
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
        ips = response.json()

        ti.xcom_push(key="ips_dict", value=ips)

        return ips

    @task
    def dns_zone_id(ti=None):
        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")
        logger.info("Getting DNS zone ID")

        dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)
        ti.xcom_push(key="dns_zone_id", value=dns_zone_id)

    @task
    def update_cloudflare_dns_record(ip: dict):
        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            match ip["id"]:
                case "racknerd":
                    cloudflare_dns_name = "vpn.jstockley.com"
                case "iowa":
                    cloudflare_dns_name = "iowa.vpn.jstockley.com"
                case "chicago":
                    cloudflare_dns_name = "chicago.vpn.jstockley.com"
                case _:
                    cloudflare_dns_name = None

            if cloudflare_dns_name is None:
                logger.error(f"Failed to get DNS zone name {ip['id']}")

            logger.info("Getting DNS zone ID")
            dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)

            logger.info("Getting IPV4 DNS record ID")
            ipv4_record_id = get_dns_record_id(
                dns_zone_id, cloudflare_dns_name, cloudflare_api_key, False
            )
            logger.info("Updating IPV4 DNS records")
            update_dns_record(
                ip["ip_address"],
                dns_zone_id,
                ipv4_record_id,
                cloudflare_dns_name,
                cloudflare_api_key,
                False,
            )

        main()

    @task()
    def update_cloudflare_apps(app_name: str, ti=None):
        ips_dict: dict = ti.xcom_pull(key="ips_dict")
        dns_zone_id = ti.xcom_pull(key="dns_zone_id")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            ips = [item["ip_address"] for item in ips_dict if "ip_address" in item]

            app_id = get_zero_trust_app_ids(dns_zone_id, app_name, cloudflare_api_key)
            policy_ids = get_app_policy_ids(dns_zone_id, app_id, cloudflare_api_key)

            delete_app_policies(dns_zone_id, app_id, policy_ids, cloudflare_api_key)
            create_app_policy(dns_zone_id, app_id, ips, cloudflare_api_key)

        main()

    apps = Variable.get("CLOUDFLARE_APPS").split("|")

    ips = get_all_ips()
    cloudflare_dns_zone_id = dns_zone_id()
    update_dns_tasks = update_cloudflare_dns_record.expand(ip=ips)
    #update_app_tasks = update_cloudflare_apps.expand(app_name=apps)

    # Set dependencies
    ips >> update_dns_tasks
    [ips, cloudflare_dns_zone_id] #>> update_app_tasks


cloudflare_apps()

if __name__ == "__main__":
    cloudflare_apps().test()
