import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.apprise.notifications.apprise import AppriseNotifier
from airflow.sdk import Variable, dag, task
from apprise import NotifyType

from plugins.cloudflare.cloudflare_api import (
    get_dns_zone_id,
    get_dns_record_id,
    update_dns_record,
    get_app_policy_id,
    update_app_policy_id,
)


logger = logging.getLogger(__name__)
env = Variable.get("env")


default_args = {
    "owner": "jackstockley",
    "retries": 2 if env == "prod" else 0,
    "retry_delay": timedelta(minutes=1),
}

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"


def __get_all_ips():
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

    return ips


@dag(
    dag_id="Cloudflare-Apps",
    description="Update Cloudflare App allowed IP addresses",
    schedule="*/5 * * * *" if not env == "dev" else None,
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=AppriseNotifier(
        body="The dag {{ dag.dag_id }} failed",
        notify_type=NotifyType.FAILURE,
        apprise_conn_id="nextcloud",
    )
    if env == "prod"
    else None,
)
def cloudflare_apps():
    @task
    def get_all_ips():
        return __get_all_ips()

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

    @task
    def update_cloudflare_policy():
        ips_dict = __get_all_ips()
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")
        account_id = Variable.get("CLOUDFLARE_ACCOUNT_ID")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")

        def main():
            ips = [item["ip_address"] for item in ips_dict if "ip_address" in item]

            policy_id = get_app_policy_id(
                account_id, "Bypass Internal IPs", cloudflare_api_key
            )
            update_app_policy_id(account_id, policy_id, ips, cloudflare_api_key)

        main()

    update_cloudflare_dns_record.expand(ip=get_all_ips()) >> update_cloudflare_policy()


cloudflare_apps()

if __name__ == "__main__":
    cloudflare_apps().test()
