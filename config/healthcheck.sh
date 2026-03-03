#!/usr/bin/env bash

HOST=localhost
PORT=${AIRFLOW__API__PORT:-8080}

# check that jq is installed
if ! command -v jq &> /dev/null
then
    echo "jq could not be found, please install it to use this healthcheck"
    exit 0
fi

# check that curl is installed
if ! command -v curl &> /dev/null
then
    echo "curl could not be found, please install it to use this healthcheck"
    exit 0
fi

response=$(curl -s "http://${HOST}:${PORT}/api/v2/monitor/health")

# Extract and check each status field
metadatabase_status=$(echo "$response" | jq -r '.metadatabase.status // empty')
scheduler_status=$(echo "$response" | jq -r '.scheduler.status // empty')
triggerer_status=$(echo "$response" | jq -r '.triggerer.status // empty')

if [ "${metadatabase_status:-unknown}" != "healthy" ]; then
    echo "Metadatabase is not healthy: ${metadatabase_status:-unknown}"
    exit 1
fi

if [ "${scheduler_status:-unknown}" != "healthy" ]; then
    echo "Scheduler is not healthy: ${scheduler_status:-unknown}"
    exit 1
fi

if [ "${triggerer_status:-unknown}" != "healthy" ]; then
    echo "Triggerer is not healthy: ${triggerer_status:-unknown}"
    exit 1
fi

echo "All services are healthy"
exit 0
