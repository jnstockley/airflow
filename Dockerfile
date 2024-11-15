FROM apache/airflow:2.10.3-python3.12
ENV PYTHONPATH "${PYTHONPATH}:/opt/airflow/plugins"
USER root
RUN apt-get update -y
RUN apt-get install iputils-ping -y
USER airflow
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY conf/webserver_config.py /opt/airflow
COPY plugins /opt/airflow/plugins
COPY dags /opt/airflow/dags
