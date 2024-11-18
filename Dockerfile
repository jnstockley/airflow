FROM apache/airflow:slim-2.10.3-python3.12

USER root

RUN apt-get update -yqq &&  \
    ACCEPT_EULA=Y apt-get upgrade -yqq && \
    apt-get install iputils-ping -yqq --no-install-recommends && \
    apt-get clean

USER airflow

ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow/plugins"

ENV PATH="/home/airflow/.local/bin:${PATH}"

RUN chmod -R 770 /opt/airflow

COPY requirements.txt .

RUN pip3 install --upgrade pip

RUN pip3 install -r requirements.txt

COPY conf/webserver_config.py /opt/airflow

COPY plugins /opt/airflow/plugins

COPY dags /opt/airflow/dags
