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
    dag_id="Speedtest",
    description="Checks if backups have been made within a certain period of time",
    schedule_interval="@once" if env == "dev" else "0 */6 * * *",
    start_date=datetime(2024, 12, 16),
    default_args=default_args,
    catchup=False,
    tags=["speedtest", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
)
def speedtest():
    iowa_host = Variable.get("SPEEDTEST_IOWA_HOST")
    iowa_api_key = Variable.get("SPEEDTEST_IOWA_API_KEY")
    iowa_upload_limit = float(Variable.get("SPEEDTEST_IOWA_UPLOAD_LIMIT"))
    iowa_download_limit = float(Variable.get("SPEEDTEST_IOWA_DOWNLOAD_LIMIT"))

    chicago_host = Variable.get("SPEEDTEST_CHICAGO_HOST")
    chicago_api_key = Variable.get("SPEEDTEST_CHICAGO_API_KEY")
    chicago_upload_limit = float(Variable.get("SPEEDTEST_CHICAGO_UPLOAD_LIMIT"))
    chicago_download_limit = float(Variable.get("SPEEDTEST_CHICAGO_DOWNLOAD_LIMIT"))

    @task()
    def speed():
        def speed_check(
            host: str, api_key: str, upload_limit: float, download_limit: float
        ):
            url = f"{host}/api/states"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logger.error(
                    f"{host} -> Response code: {response.status_code}, when it should be 200"
                )
                raise ConnectionError(f"Unable to connect to host: {host}")

            download: float = 0.0
            upload: float = 0.0

            for entity in response.json():
                if entity["entity_id"] == "sensor.speedtest_upload":
                    try:
                        upload = float(entity["state"])
                    except Exception as e:
                        logger.error(
                            f"{host} -> Unable to convert upload speed to float: {entity['state']}"
                        )
                        logger.error(e)
                if entity["entity_id"] == "sensor.speedtest_download":
                    try:
                        download = float(entity["state"])
                    except Exception as e:
                        logger.error(
                            f"{host} -> Unable to convert download speed to float: {entity['state']}"
                        )
                        logger.error(e)

            assert upload >= upload_limit, (
                f"{host} -> Upload speed below limit: {upload} for location: {host}"
            )
            assert download >= download_limit, (
                f"{host} -> Download speed below limit: {download} for location: {host}"
            )

        def main():
            logger.info("Checking Iowa Home Speedtest")
            speed_check(iowa_host, iowa_api_key, iowa_upload_limit, iowa_download_limit)

            logger.info("Checking Chicago Home Speedtest")
            speed_check(
                chicago_host,
                chicago_api_key,
                chicago_upload_limit,
                chicago_download_limit,
            )

        main()

    speed()


speedtest()
