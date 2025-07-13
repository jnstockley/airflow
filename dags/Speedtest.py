import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.apprise.notifications.apprise import AppriseNotifier
from airflow.sdk import Variable, dag, task
from apprise import NotifyType

logger = logging.getLogger(__name__)

env = Variable.get("env")

default_args = {
    "owner": "jackstockley",
    "retries": 2 if env == "prod" else 0,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="Speedtest",
    description="Checks if backups have been made within a certain period of time",
    schedule="0 */6 * * *" if not env == "dev" else None,
    start_date=datetime(2024, 12, 16),
    default_args=default_args,
    catchup=False,
    tags=["speedtest", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=AppriseNotifier(
        body="The dag {{ dag.dag_id }} failed",
        notify_type=NotifyType.FAILURE,
        apprise_conn_id="nextcloud",
    )
    if env == "prod"
    else None,
)
def speedtest():
    @task
    def get_devices():
        devices: list[str] = Variable.get("SPEEDTEST_DEVICES").split("|")

        logger.info("Found devices: %s", devices)
        if len(devices) == 0:
            raise ValueError("No devices found in SPEEDTEST_DEVICES variable")

        return devices

    @task
    def speed_test(device: str):
        host = Variable.get(f"SPEEDTEST_{device}_HOST")
        api_key = Variable.get(f"SPEEDTEST_{device}_API_KEY")
        upload_limit: float = float(
            Variable.get(f"SPEEDTEST_{device}_UPLOAD_LIMIT", default=0.0)
        )
        download_limit: float = float(
            Variable.get(f"SPEEDTEST_{device}_DOWNLOAD_LIMIT", default=0.0)
        )

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

    devices = get_devices()
    speed_test.expand(device=devices)


speedtest()

if __name__ == "__main__":
    speedtest().test()
