import logging
import os
import shutil

import math

from airflow.decorators import task
from airflow.models import Variable
from airflow.models.dag import dag
from datetime import datetime, timedelta

env = Variable.get("ENV")
host = os.environ["AIRFLOW__WEBSERVER__BASE_URL"]

logger = logging.getLogger(__name__)

default_args = {
    "owner": "jackstockley",
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
    "email": ["jack@jstockley.com"],
    "email_on_failure": True,
}


@dag(
    dag_id="Airflow-Cleanup",
    description="Cleanup logs and data folders",
    start_date=datetime(2024, 9, 2),
    schedule="@once" if env == "dev" else "@daily",
    default_args=default_args,
    catchup=False,
    tags=["maintenance"],
    dagrun_timeout=timedelta(seconds=60),
)
def cleanup():
    @task()
    def cleanup_logs():
        file_list = []
        for root, dirs, files in os.walk("./logs"):
            for file in files:
                file_path = os.path.join(root, file)
                logger.info(f"Found file: {file_path}")
                if (
                    os.path.getmtime(file_path)
                    < (datetime.now() - timedelta(days=1)).timestamp()
                ):
                    file_list.append(os.path.join(root, file))

        for file in file_list:
            if env != "dev":
                os.remove(file)
            logger.info(f"Removed file: {file} since last modified is over a month ago")

    @task()
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

    @task()
    def check_disk_usage():
        total, used, free = shutil.disk_usage("./data")

        used_percentage = (used / total) * 100

        logger.info(f"Total disk space: {total / math.pow(1024, 3)} GB")

        logger.info(f"Used disk space: {used_percentage}%")

        if used_percentage > 75:
            raise OSError(f"Used disk space is over 75%: {used_percentage}%")

    cleanup_logs()
    cleanup_data()
    if "airflow" not in host:
        check_disk_usage()


cleanup()

if __name__ == '__main__':
    cleanup().test()
