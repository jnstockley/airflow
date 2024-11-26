import logging
from datetime import datetime

import requests

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"

logger = logging.getLogger(__name__)


def get_dns_zone_id(zone_name: str, api_key: str) -> str:
    url = f"{CLOUDFLARE_API}/zones"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" in response.json():
        results = response.json()["result"]
        for result in results:
            if result["name"] == zone_name:
                logger.info("Found DNS zone id")
                return result["id"]

    raise ValueError(
        f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
    )


def get_all_a_record_ips(zone_id: str, api_key: str) -> list[str]:
    ips = []
    url = f"{CLOUDFLARE_API}/zones/{zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" in response.json():
        results = response.json()["result"]
        for result in results:
            if result["type"] == "A":
                ips.append(result["content"])

    if len(ips) == 0:
        raise ValueError(
            f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
        )
    return ips


def get_dns_record_id(zone_id: str, dns_name: str, api_key: str, ipv6: bool) -> str:
    url = f"{CLOUDFLARE_API}/zones/{zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" in response.json():
        results = response.json()["result"]
        for result in results:
            if result["name"] == dns_name and (not ipv6) and result["type"] == "A":
                logging.info("Found IPV4 DNS record ID")
                return result["id"]
            elif result["name"] == dns_name and ipv6 and result["type"] == "AAAA":
                logging.info("Found IPV6 DNS record ID")
                return result["id"]

    raise ValueError(
        f"Failed to get DNS zone. Status code: {response.status_code} -> {response.json()}"
    )


def update_dns_record(
    new_ip: str,
    zone_id: str,
    dns_record_id,
    dns_name: str,
    api_key: str,
    ipv6: bool,
    proxied: bool = False,
):
    url = f"{CLOUDFLARE_API}/zones/{zone_id}/dns_records/{dns_record_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    body = {
        "content": new_ip,
        "name": dns_name,
        "proxied": proxied,
        "type": "AAAA" if ipv6 else "A",
        "comment": f"Updated automatically at {datetime.now()}",
        "ttl": 300,
    }

    response = requests.patch(url, headers=headers, json=body)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to update DNS record. Status code: {response.status_code} -> {response.json()}"
        )

    if "success" not in response.json() or not response.json()["success"]:
        raise ValueError(
            f"Failed to update DNS record. Status code: {response.status_code} -> {response.json()}"
        )

    logger.info(f"Updated DNS record {dns_name}")


def get_zero_trust_app_ids(zone_id: str, app_name: str, api_key: str):
    url = f"{CLOUDFLARE_API}/zones/{zone_id}/access/apps"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to get App ID. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" in response.json():
        results = response.json()["result"]
        for app in results:
            if app["name"] == app_name:
                return app["id"]

    raise ValueError(
        f"Failed to get App ID. Status code: {response.status_code} -> {response.json()}"
    )


def get_app_policy_ids(zone_id: str, app_id: str, api_key: str):
    policy_ids = []

    url = f"{CLOUDFLARE_API}/zones/{zone_id}/access/apps/{app_id}/policies"
    headers = {"Authorization": f"Bearer {api_key}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise ConnectionError(
            f"Failed to get App ID. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" in response.json():
        results = response.json()["result"]
        for policy in results:
            policy_ids.append(policy["id"])

    return policy_ids


def delete_app_policies(zone_id: str, app_id: str, policy_ids: list[str], api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}

    for policy_id in policy_ids:
        url = f"{CLOUDFLARE_API}/zones/{zone_id}/access/apps/{app_id}/policies/{policy_id}"
        response = requests.delete(url, headers=headers)

        if response.status_code != 202:
            raise ConnectionError(
                f"Failed to delete Policy ID. Status code: {response.status_code} -> {response.json()}"
            )


def create_app_policy(zone_id: str, app_id: str, allowed_ips: list[str], api_key: str):
    url = f"{CLOUDFLARE_API}/zones/{zone_id}/access/apps/{app_id}/policies"
    headers = {"Authorization": f"Bearer {api_key}"}

    ips = []

    for allowed_ip in allowed_ips:
        ip = {"ip": {"ip": allowed_ip}}
        ips.append(ip)

    oidc_group = [
        {
            "oidc": {
                "identity_provider_id": "09e99fc9-5411-46bf-a6ce-b6823a12a59e",
                "claim_name": "groups",
                "claim_value": "authentik Admins",
            }
        }
    ]

    bypass_body = {
        "decision": "bypass",
        "name": f"Bypass Internal IPs added at {datetime.now()}",
        "include": ips,
    }

    allow_body = {
        "decision": "allow",
        "name": f"Allow External IPs added at {datetime.now()}",
        "include": [{"login_method": {"id": "09e99fc9-5411-46bf-a6ce-b6823a12a59e"}}],
        "require": oidc_group,
    }

    logger.info("Creating Bypass Policy")

    response = requests.post(url, headers=headers, json=bypass_body)

    if response.status_code != 201:
        raise ConnectionError(
            f"Failed to create App Policy. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" not in response.json():
        raise ValueError(
            f"Failed to create App Policy. Status code: {response.status_code} -> {response.json()}"
        )

    logger.info("Creating Allow Policy")

    response = requests.post(url, headers=headers, json=allow_body)

    if response.status_code != 201:
        raise ConnectionError(
            f"Failed to create App Policy. Status code: {response.status_code} -> {response.json()}"
        )

    if "result" not in response.json():
        raise ValueError(
            f"Failed to create App Policy. Status code: {response.status_code} -> {response.json()}"
        )
