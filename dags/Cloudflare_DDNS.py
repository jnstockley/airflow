import logging
import re
from datetime import timedelta, datetime

import requests
from airflow.decorators import task
from airflow.models import Variable, TaskInstance
from airflow.models.dag import dag

from cloudflare.cloudflare_api import (
    get_dns_zone_id,
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
    dag_id="Cloudflare-DDNS",
    description="Update the Cloudflare DNS record",
    schedule_interval="@once" if env == "dev" else "*/5 * * * *",
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
)
def cloudflare_ddns():
    @task()
    def get_ipv4_address(ti: TaskInstance):
        logger.info("Getting IPv4 address")
        pattern = re.compile(
            r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        )

        response = requests.get("https://api.ipify.org?format=json")

        if response.status_code != 200:
            logger.error(
                f"Failed to get IPv4 address. Status code: {response.status_code} -> "
                f"{response.json()}"
            )
            raise ConnectionError(
                f"Failed to get IPv4 address. Status code: {response.status_code} -> "
                f"{response.json()}"
            )

        ip_address = response.json()["ip"]

        if pattern.match(ip_address):
            logger.info("Validated IPv4 address")
            ti.xcom_push(key="ipv4_address", value=ip_address)
            return

        logger.error("Invalid IPv4 address")
        raise ValueError("Invalid IPv4 address")

    @task()
    def get_ipv6_address(ti: TaskInstance):
        logger.info("Getting IPv6 address")
        pattern = re.compile(
            r"(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,7}:|"
            r"([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|"
            r"([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|"
            r"([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|"
            r"[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|"
            r":((:[0-9a-fA-F]{1,4}){1,7}|:)|"
            r"fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|"
            r"::(ffff(:0{1,4}){0,1}:){0,1}"
            r"((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}"
            r"(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|"
            r"([0-9a-fA-F]{1,4}:){1,4}:"
            r"((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}"
            r"(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))"
        )

        try:
            response = requests.get("https://api6.ipify.org?format=json")

            if response.status_code != 200:
                logger.error(
                    f"Failed to get IPv6 address. Status code: {response.status_code} -> "
                    f"{response.json()}"
                )
                raise ConnectionError(
                    f"Failed to get IPv6 address. Status code: {response.status_code} -> "
                    f"{response.json()}"
                )

            ip_address = response.json()["ip"]

            if pattern.match(ip_address):
                logger.info("Validated IPv6 address")
                ti.xcom_push(key="ipv6_address", value=ip_address)
                return

            logger.error("Invalid IPv6 address")
            raise ValueError("Invalid IPv6 address")

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Failed to get IPv6 address. {e}")

    @task()
    def update_cloudflare_dns_record(ti: TaskInstance):
        ipv4_address = ti.xcom_pull(key="ipv4_address")
        ipv6_address = ti.xcom_pull(key="ipv6_address")

        dns_zone_name = Variable.get("CLOUDFLARE_ZONE_NAME")
        cloudflare_api_key = Variable.get("CLOUDFLARE_API_KEY")
        cloudflare_dns_name = Variable.get("CLOUDFLARE_DNS_NAME")

        def main():
            logger.info("Getting DNS zone ID")
            dns_zone_id = get_dns_zone_id(dns_zone_name, cloudflare_api_key)

            logger.info("Getting IPV4 DNS record ID")
            ipv4_record_id = get_dns_record_id(
                dns_zone_id, cloudflare_dns_name, cloudflare_api_key, False
            )
            ipv6_record_id = None

            if ipv6_address is not None:
                logger.info("Getting IPV6 DNS record ID")
                ipv6_record_id = get_dns_record_id(
                    dns_zone_id, cloudflare_dns_name, cloudflare_api_key, True
                )

            logger.info("Updating IPV4 DNS records")
            update_dns_record(
                ipv4_address,
                dns_zone_id,
                ipv4_record_id,
                cloudflare_dns_name,
                cloudflare_api_key,
                False,
            )

            if ipv6_record_id is not None:
                logger.info("Updating IPV6 DNS records")
                update_dns_record(
                    ipv6_address,
                    dns_zone_id,
                    ipv6_record_id,
                    cloudflare_dns_name,
                    cloudflare_api_key,
                    True,
                )

        main()

    [get_ipv4_address(), get_ipv6_address()] >> update_cloudflare_dns_record()


cloudflare_ddns()
