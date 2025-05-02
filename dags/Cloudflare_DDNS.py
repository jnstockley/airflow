import logging
from datetime import timedelta, datetime

import requests
from airflow.providers.smtp.notifications.smtp import SmtpNotifier
from airflow.sdk import Variable, dag, task


logger = logging.getLogger(__name__)

env = Variable.get("env")


default_args = {
    "owner": "jackstockley",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}


@dag(
    dag_id="Cloudflare-DDNS",
    description="Update the Cloudflare DNS record",
    schedule="*/5 * * * *" if not env == "dev" else None,
    start_date=datetime(2024, 3, 4),
    default_args=default_args,
    catchup=False,
    tags=["cloudflare", "infrastructure"],
    dagrun_timeout=timedelta(seconds=60),
    on_failure_callback=SmtpNotifier(
        to="jack@jstockley.com",
        smtp_conn_id="SMTP"
    )
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
