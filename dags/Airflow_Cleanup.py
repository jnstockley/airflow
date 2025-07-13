import logging
import os
import shutil

import math
from airflow.providers.apprise.notifications.apprise import AppriseNotifier

from airflow.sdk import Variable, dag, task
from datetime import datetime, timedelta

from apprise import NotifyType

env = Variable.get("ENV")
host = os.environ["AIRFLOW__API__BASE_URL"]

logger = logging.getLogger(__name__)

default_args = {
    "owner": "jackstockley",
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="Airflow-Cleanup",
    description="Cleanup logs and data folders",
    start_date=datetime(2024, 9, 2),
    schedule="@daily" if not env == "dev" else None,
    default_args=default_args,
    catchup=False,
    tags=["maintenance"],
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=AppriseNotifier(
        body="The dag {{ dag.dag_id }} failed",
        notify_type=NotifyType.FAILURE,
        apprise_conn_id="nextcloud",
    )
    if env == "prod"
    else None,
)
def cleanup():
    @task
    def cleanup_data():
        file_list = []
        for root, dirs, files in os.walk("./data"):
            for file in files:
                file_path = os.path.join(root, file)
                logger.info(f"Found file: {file_path}")
                if (
                    os.path.getmtime(file_path)
                    < (datetime.now() - timedelta(days=7)).timestamp()
                ):
                    file_list.append(os.path.join(root, file))

        for file in file_list:
            if env != "dev":
                os.remove(file)
            logger.info(f"Removed file: {file} since last modified is over a week ago")

    @task
    def check_disk_usage():
        total, used, free = shutil.disk_usage("./data")

        used_percentage = (used / total) * 100

        logger.info(f"Total disk space: {total / math.pow(1024, 3)} GB")

        logger.info(f"Used disk space: {used_percentage}%")

        if used_percentage > 75:
            raise OSError(f"Used disk space is over 75%: {used_percentage}%")

    cleanup_data()
    if "airflow.jstockley" not in host:
        check_disk_usage()


cleanup()

if __name__ == "__main__":
    cleanup().test()
