import os
from typing import Optional

import jwt
import logging

from airflow.models import Variable
from flask import redirect, session
from flask_appbuilder import expose
from flask_appbuilder.security.manager import AUTH_OAUTH
from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from flask_appbuilder.security.views import AuthOAuthView
from flask_login import logout_user
from jwt import PyJWKClient

log = logging.getLogger(__name__)

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_ROLES_SYNC_AT_LOGIN = True
AUTH_USER_REGISTRATION_ROLE = "Public"

AUTHENTIK_APP_NAME = os.environ["AUTHENTIK_APP_NANE"]

# Make sure you create these role on Keycloak
AUTH_ROLES_MAPPING = {
    "Viewer": ["Viewer"],
    "Admin": ["Admin"],
    "User": ["User"],
    "Public": ["Public"],
    "Op": ["Op"],
}

OAUTH_PROVIDERS = [
    {
        "name": "authentik",
        "icon": "fa-key",
        "token_key": "access_token",
        "remote_app": {
            "client_id": Variable.get("CLIENT_ID"),
            "client_secret": Variable.get("CLIENT_SECRET"),
            "server_metadata_url": f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NAME}/.well-known/openid-configuration",
            "api_base_url": f"{Variable.get('ISSUER')}/",
            "client_kwargs": {"scope": "openid profile email"},
            "access_token_url": f"{Variable.get('ISSUER')}/application/o/token/",
            "authorize_url": f"{Variable.get('ISSUER')}/application/o/authorize/",
            "request_token_url": None,
        },
    }
]


def map_roles(team_list: list) -> list:
    team_role_map = {
        "authentik Admins": "Admin",
    }
    return list(set(team_role_map.get(team, "Viewer") for team in team_list))


class AuthentikAuthRemoteUserView(AuthOAuthView):
    @expose("/login/")
    @expose("/login/<provider>")
    @expose("/login/<provider>/<register>")
    def login(self, provider: Optional[str] = "authentik", register=None):
        return super().login(provider)

    @expose("/logout/", methods=["GET", "POST"])
    def logout(self):
        logout_user()
        session.clear()
        return redirect(
            f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NAME}/end-session/"
        )


class AuthentikSecurityManager(FabAirflowSecurityManagerOverride):
    authoauthview = AuthentikAuthRemoteUserView

    def get_oauth_user_info(self, provider, response):
        if provider == "authentik":
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0"
            }
            token = response["access_token"]
            jwks_client = PyJWKClient(f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NAME}/jwks/", headers=headers)
            public_key = jwks_client.get_signing_key_from_jwt(token)
            audience = response["userinfo"]["aud"]
            subject = response["userinfo"]["sub"]
            issuer = response["userinfo"]["iss"]
            me = jwt.decode(
                token,
                public_key.key,
                audience=audience,
                subject=subject,
                issuer=issuer,
                algorithms=["RS256"],
                verify=True,
            )

            # Extract roles from resource access
            groups = map_roles(me["groups"])

            log.info("groups: {0}".format(groups))

            if not groups:
                groups = ["Viewer"]

            userinfo = {
                "username": me.get("preferred_username"),
                "email": me.get("email"),
                "first_name": me.get("given_name").split(" ")[0],
                "last_name": me.get("given_name").split(" ")[1],
                "role_keys": groups,
            }

            log.info("user info: {0}".format(userinfo))

            return userinfo
        else:
            return {}


SECURITY_MANAGER_CLASS = AuthentikSecurityManager
RATELIMIT_STORAGE_URI = os.getenv("REDIS_URI")
