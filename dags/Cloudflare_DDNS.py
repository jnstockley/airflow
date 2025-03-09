import logging
from datetime import timedelta, datetime

import requests
from airflow.decorators import task
from airflow.models import Variable
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
    dag_id="Cloudflare-DDNS",
    description="Update the Cloudflare DNS record",
    schedule="@once" if env == "dev" else "*/5 * * * *",
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
)
def cloudflare_ddns():
    @task()
    def update_ip_address():
        endpoint = Variable.get("API_ENDPOINT")
        identifier = Variable.get("DDNS_IDENTIFIER")
        api_key = Variable.get("API_KEY")

        params = {"identifier": identifier}
        headers = {"x-api-key": api_key}
        response = requests.post(endpoint, params=params, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to update IP address. Status code: {response.status_code} -> "
                f"{response.json()}"
            )
            raise ConnectionError(
                f"Failed to update IP address. Status code: {response.status_code} -> "
                f"{response.json()}"
            )

    update_ip_address()


cloudflare_ddns()

if __name__ == "__main__":
    cloudflare_ddns().test()
