import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.apprise.notifications.apprise import AppriseNotifier
from airflow.sdk import Variable, Param, dag, task
from apprise import NotifyType

logger = logging.getLogger(__name__)

env = Variable.get("env")

default_args = {
    "owner": "jackstockley",
    "retries": 2 if env == "prod" else 0,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="DNS-Requests",
    description="Checks if DNS requests have been made within a certain period of time",
    schedule="0 * * * *" if not env == "dev" else None,
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["dns", "infrastructure"],
    params={
        "outdated_interval": Param(
            1, type="integer", description="The number of hours since the last request"
        ),
    },
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=AppriseNotifier(
        body="The dag {{ dag.dag_id }} failed",
        notify_type=NotifyType.FAILURE,
        apprise_conn_id="nextcloud",
    )
    if env == "prod"
    else None,
)
def dns_requests():
    @task
    def check_protection():
        dns_host = Variable.get("DNS_HOST")
        api_key = Variable.get("DNS_API_KEY")

        headers = {"Authorization": f"Basic {api_key}"}
        url = f"{dns_host}status"

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Response code: {response.status_code}, when it should be 200 ->"
                f" {response.json()}"
            )
            raise ConnectionError(
                f"Response code: {response.status_code}, when it should be 200 -> "
                f"{response.json()}"
            )

        if (
            "protection_enabled" not in response.json()
            or "protection_disabled_duration" not in response.json()
            or "running" not in response.json()
        ):
            logger.error(
                f"Invalid response message, missing `protection_enabled` or "
                f"`protection_disabled_duration` or `running`: {response.json()}"
            )
            raise ValueError(
                f"Invalid response message, missing `protection_enabled` or "
                f"`protection_disabled_duration` or `running`: {response.json()}"
            )

        running: bool = response.json()["running"]
        protection_enabled: bool = response.json()["protection_enabled"]
        protection_disabled_duration: int = response.json()[
            "protection_disabled_duration"
        ]
        logger.info(
            f"Running: {running}, Protection Enabled: {protection_enabled}, Protection Disabled Duration: {protection_disabled_duration}"
        )
        if not running:
            logger.error("DNS service is not running")
            raise ValueError("DNS service is not running")

        if not protection_enabled and protection_disabled_duration == 0:
            logger.error(
                "Protection is disabled and is not being disabled automatically"
            )
            raise ValueError(
                "Protection is disabled and is not being disabled automatically"
            )

    @task
    def check_requests(client: str, params: dict):
        dns_host = Variable.get("DNS_HOST")
        api_key = Variable.get("DNS_API_KEY")
        outdated_interval: int = params["outdated_interval"]
        outdated_time = (
            datetime.now() - timedelta(hours=outdated_interval)
        ).timestamp()

        headers = {"Authorization": f"Basic {api_key}"}

        url = f"{dns_host}querylog?search={client}&limit=1"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Response code: {response.status_code}, when it should be 200 ->"
                f" {response.json()}"
            )
            raise ConnectionError(
                f"Response code: {response.status_code}, when it should be 200 -> "
                f"{response.json()}"
            )

        if "oldest" not in response.json():
            logger.error(
                f"Invalid response message, missing `oldest`: {response.json()}"
            )
            raise ValueError(
                f"Invalid response message, missing `oldest`: {response.json()}"
            )

        last_request = datetime.fromisoformat(response.json()["oldest"]).timestamp()
        logger.info(
            f"{client} -> Last request received for {client}: {response.json()['oldest']}"
        )

        if last_request < outdated_time:
            logger.error(f"Last request received for {client}: {last_request}")
            raise ValueError(f"Last request received for {client}: {last_request}")

    clients: list[str] = Variable.get("DNS_CLIENTS").split("|")
    check_protection() >> check_requests.expand(client=clients)


dns_requests()

if __name__ == "__main__":
    dns_requests().test()
