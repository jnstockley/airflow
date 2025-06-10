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
    dag_id="Backups",
    description="Checks if backups have been made within a certain period of time",
    schedule="0 * * * *" if not env == "dev" else None,
    start_date=datetime(2024, 12, 16),
    default_args=default_args,
    catchup=False,
    tags=["backup", "infrastructure"],
    params={
        "outdated_interval": Param(
            2, type="integer", description="The number of hours since the backup sync"
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
def backup():
    @task
    def get_devices():
        devices: list[str] = Variable.get("BACKUP_DEVICES").split("|")

        logger.info("Found devices: %s", devices)
        if len(devices) == 0:
            raise ValueError("No devices found in BACKUP_DEVICES variable")

        return devices

    @task
    def health_check(device: str):
        host = Variable.get(f"BACKUP_{device}_HOST")
        api_key = Variable.get(f"BACKUP_{device}_API_KEY")

        url = f"{host}/rest/noauth/health"
        headers = {"Authorization": f"Bearer {api_key}"}

        response = requests.get(url, headers=headers, verify=False)

        if response.status_code != 200 or response.json() != {"status": "OK"}:
            logger.error(
                f"Response code: {response.status_code}, when it should be 200 -> {response.json()}"
            )
            raise ConnectionError(
                f"Response code: {response.status_code}, when it should be 200 -> "
                f"{response.json()}"
            )

    @task
    def paused(device: str):
        host = Variable.get(f"BACKUP_{device}_HOST")
        api_key = Variable.get(f"BACKUP_{device}_API_KEY")

        url = f"{host}/rest/config/folders"
        headers = {"Authorization": f"Bearer {api_key}"}

        response = requests.get(url, headers=headers, verify=False)

        if response.status_code != 200:
            logger.error(
                f"Response code: {response.status_code}, when it should be 200 -> {response.json()}"
            )
            raise ConnectionError(
                f"Response code: {response.status_code}, when it should be 200 -> "
                f"{response.json()}"
            )

        folders = response.json()

        for folder in folders:
            data = dict(folder)
            assert "paused" in data, (
                f"{host} -> Invalid response message missing `paused`: {folder}"
            )
            assert "label" in data, (
                f"{host} -> Invalid response message missing `label`: {folder}"
            )
            assert not data["paused"], f"{host} -> {data['label']} is paused on {host}"

    @task
    def folder_status(device: str, params: dict):
        outdated_interval: int = params["outdated_interval"]

        host = Variable.get(f"BACKUP_{device}_HOST")
        api_key = Variable.get(f"BACKUP_{device}_API_KEY")

        url = f"{host}/rest/stats/folder"
        headers = {"Authorization": f"Bearer {api_key}"}

        outdated_time = (
            datetime.now() - timedelta(hours=outdated_interval)
        ).timestamp()

        response = requests.get(url, headers=headers, verify=False)

        if response.status_code != 200:
            logger.error(
                f"Response code: {response.status_code}, when it should be 200 -> {response.json()}"
            )
            raise ConnectionError(
                f"Response code: {response.status_code}, when it should be 200 -> "
                f"{response.json()}"
            )

        folders = response.json()

        logger.info(folders)

        for folder, data in folders.items():
            assert "lastScan" in data, (
                f"{host} -> Invalid response message missing `lastScan`: {data}"
            )
            last_scan = datetime.fromisoformat(data["lastScan"]).timestamp()
            assert last_scan >= outdated_time, (
                f"{host} -> {folder} is out of sync on {host}, last synced: {last_scan}"
            )

    # Get the list of devices
    devices = get_devices()

    # Map health_check task to each device
    health_checks = health_check.expand(device=devices)

    # Map paused and folder_status tasks to each device
    # Set dependencies so they run after health_check
    paused_tasks = paused.expand(device=devices)
    folder_status_tasks = folder_status.expand(device=devices)

    # Set up dependencies: devices -> health_check -> (paused & folder_status)
    health_checks >> [paused_tasks, folder_status_tasks]


backup()

if __name__ == "__main__":
    backup().test()
