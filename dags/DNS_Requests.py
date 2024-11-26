import logging
from datetime import timedelta, datetime

import requests
from airflow.decorators import task
from airflow.models import Variable, Param
from airflow.models.dag import dag

logger = logging.getLogger(__name__)

default_args = {
    "owner": "jackstockley",
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
    "email": ["jack@jstockley.com"],
    "email_on_failure": True,
}

env = Variable.get("env")


@dag(
    dag_id="DNS-Requests",
    description="Checks if DNS requests have been made within a certain period of time",
    schedule_interval="@once" if env == "dev" else "0 * * * *",
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["dns", "infrastructure"],
    params={
        "outdated_interval": Param(
            1, type="integer", description="The number of hours since the last request"
        ),
    },
)
def dns_requests():
    @task()
    def check_requests(params: dict):
        dns_host = Variable.get("DNS_HOST")
        api_key = Variable.get("DNS_API_KEY")
        clients: list[str] = Variable.get("DNS_CLIENTS").split("|")
        outdated_interval: int = params["outdated_interval"]
        outdated_time = (
            datetime.now() - timedelta(hours=outdated_interval)
        ).timestamp()

        headers = {"Authorization": f"Basic {api_key}"}

        for client in clients:
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

    check_requests()


dns_requests()
