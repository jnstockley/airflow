FROM apache/airflow:slim-2.10.4 AS build

USER root

RUN apt-get update -yqq &&  \
    ACCEPT_EULA=Y apt-get upgrade -yqq && \
    apt-get install iputils-ping -yqq --no-install-recommends && \
    apt-get clean

USER airflow

#ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow/plugins"

#ENV PATH="/home/airflow/.local/bin:${PATH}"

#RUN chmod -R 770 /opt/airflow

COPY requirements.txt .

RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

FROM apache/airflow:slim-2.10.4

COPY --from=build home/airflow/.local/ /home/airflow/.local/

ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow/plugins"

ENV PATH="/root/.local/bin:${PATH}"

COPY conf/webserver_config.py /opt/airflow

COPY plugins /opt/airflow/plugins

COPY dags /opt/airflow/dags

USER root

RUN chmod -R 770 /opt/airflow

USER airflow
