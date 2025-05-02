import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.smtp.notifications.smtp import SmtpNotifier
from airflow.sdk import Variable, Param, dag, task

logger = logging.getLogger(__name__)

env = Variable.get("env")

default_args = {
    "owner": "jackstockley",
    "retries": 2,
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
    on_failure_callback=SmtpNotifier(
        to="jack@jstockley.com",
        smtp_conn_id="SMTP"
    )
)
def backup():
    iowa_home_host = Variable.get("BACKUP_IOWA_HOME_HOST")
    iowa_home_api_key = Variable.get("BACKUP_IOWA_HOME_API_KEY")

    #chicago_home_host = Variable.get("BACKUP_CHICAGO_HOME_HOST")
    #chicago_home_api_key = Variable.get("BACKUP_CHICAGO_HOME_API_KEY")

    backup_server_host = Variable.get("BACKUP_BACKUP_SERVER_HOST")
    backup_server_api_key = Variable.get("BACKUP_BACKUP_SERVER_API_KEY")

    synology_host = Variable.get("BACKUP_SYNOLOGY_HOST")
    synology_api_key = Variable.get("BACKUP_SYNOLOGY_API_KEY")

    racknerd_host = Variable.get("BACKUP_RACKNERD_HOST")
    racknerd_api_key = Variable.get("BACKUP_RACKNERD_API_KEY")

    @task
    def paused():
        def heath_check(host: str, api_key: str):
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

        def check_paused(host: str, api_key: str):
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
                assert not data["paused"], (
                    f"{host} -> {data['label']} is paused on {host}"
                )

        def main():
            logger.info("Checking Iowa Home Paused Status")
            heath_check(iowa_home_host, iowa_home_api_key)
            check_paused(iowa_home_host, iowa_home_api_key)

            #logger.info("Checking Chicago Home Paused Status")
            #heath_check(chicago_home_host, chicago_home_api_key)
            #check_paused(chicago_home_host, chicago_home_api_key)

            logger.info("Checking Backup Server Paused Status")
            heath_check(backup_server_host, backup_server_api_key)
            check_paused(backup_server_host, backup_server_api_key)

            logger.info("Checking Synology Paused Status")
            heath_check(synology_host, synology_api_key)
            check_paused(synology_host, synology_api_key)

            logger.info("Checking Racknerd Paused Status")
            heath_check(racknerd_host, racknerd_api_key)
            check_paused(racknerd_host, racknerd_api_key)

        main()

    @task
    def status(params: dict):
        outdated_interval: int = params["outdated_interval"]

        def check_status(host: str, api_key: str):
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
            for folder, data in folders.items():
                assert "lastScan" in data, (
                    f"{host} -> Invalid response message missing `lastScan`: {data}"
                )
                last_scan = datetime.fromisoformat(data["lastScan"]).timestamp()
                assert last_scan >= outdated_time, (
                    f"{host} -> {folder} is out of sync on {host}, "
                    f"last synced: {last_scan}"
                )

        def main():
            logger.info("Checking Iowa Home Outdated Status")
            check_status(iowa_home_host, iowa_home_api_key)

            #logger.info("Checking Chicago Home Outdated Status")
            #check_status(chicago_home_host, chicago_home_api_key)

            logger.info("Checking Backup Server Outdated Status")
            check_status(backup_server_host, backup_server_api_key)

            logger.info("Checking Synology Outdated Status")
            check_status(synology_host, synology_api_key)

            logger.info("Checking Racknerd Outdated Status")
            check_status(racknerd_host, racknerd_api_key)

        main()

    paused() >> status()


backup()

if __name__ == "__main__":
    backup().test()
