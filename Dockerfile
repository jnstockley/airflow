ARG AIRFLOW_VERSION=3.3.1

ARG PYTHON_VERSION=3.14

FROM dhi.io/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}-debian-dev AS build

USER root

RUN apt-get update -y && \
    apt-get install --no-install-recommends -y build-essential python3-dev python3-pip libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

USER airflow

RUN python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip && \
    python3 -m pip install --no-cache-dir --break-system-packages --user -r requirements.txt

FROM dhi.io/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}-compat

COPY --from=build --chown=airflow:root /home/airflow/.local/ /home/airflow/.local/

ENV PYTHONPATH="${PYTHONPATH}:/opt/airflow" \
    PATH="/home/airflow/.local/bin:${PATH}" \
    AIRFLOW__CORE__EXECUTOR=LocalExecutor \
    AIRFLOW__CORE__AUTH_MANAGER=airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager \
    AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK=True \
    AIRFLOW__CORE__LOAD_EXAMPLES=False \
    AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True \
    AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=10 \
    AIRFLOW__CORE__EXECUTION_API_SERVER_URL=http://airflow-apiserver:8080/execution/ \
    FORWARDED_ALLOW_IPS=* \
    AIRFLOW__FAB__ENABLE_PROXY_FIX=True \
    AIRFLOW__CORE__DEFAULT_TIMEZONE=America/Chicago \
    AIRFLOW__CORE__DEFAULT_TASK_EXECUTION_TIMEOUT=3600 \
    AIRFLOW__FAB__COOKIE_SECURE=True \
    AIRFLOW__FAB__COOKIE_SAMESITE=Strict \
    TZ=America/Chicago \
    AIRFLOW__CORE__AUTH_MANAGER=webserver_config.AuthentikAuthManager

COPY config/webserver_config.py /opt/airflow

COPY plugins /opt/airflow/plugins

COPY dags /opt/airflow/dags

# Python-based healthcheck: the hardened final image has no shell/curl/jq,
# so the check relies solely on the Python interpreter shipped with Airflow.
COPY config/healthcheck.py /opt/airflow/healthcheck.py

USER airflow

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD ["python3", "/opt/airflow/healthcheck.py"]

