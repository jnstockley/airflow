import os
import logging
from typing import Optional
from urllib.parse import urlencode

from airflow.api_fastapi.app import get_cookie_path
from airflow.configuration import conf
from airflow.providers.fab.auth_manager.fab_auth_manager import FabAuthManager
from airflow.sdk import Variable
from flask import redirect, session, make_response, request
from flask_appbuilder import expose
from flask_appbuilder.security.manager import AUTH_OAUTH
from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from flask_appbuilder.security.views import AuthOAuthView
from flask_login import logout_user

log = logging.getLogger(__name__)

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
# The user's roles are assigned from Authentik group claims at login.
AUTH_USER_REGISTRATION_ROLE = "Public"
AUTH_ROLES_SYNC_AT_LOGIN = True
CSRF_ENABLED = True

BASE_URL = conf.get("api", "base_url")

AUTHENTIK_APP_NAME = os.environ["AUTHENTIK_APP_NANE"]

# Make sure these roles exist in Airflow before users sign in.
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
            "client_kwargs": {
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
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
    def login(self, provider: Optional[str] = None, register=None):
        # Auto-redirect to the IdP, except after a failed login: the IdP session would bounce the user
        # straight back and loop. Render FAB's login page instead so the flashed error is shown.
        if provider is None and not session.get("_flashes"):
            provider = "authentik"
        return super().login(provider)

    @expose('/start-logout')
    def logout(self):
        params = {"client_id": Variable.get("CLIENT_ID")}
        if session.get("id_token"):
            params["id_token_hint"] = session["id_token"]
        # End the local session before contacting Authentik.
        logout_user()
        session.clear()
        end_session = self.appbuilder.sm.oauth_remotes["authentik"].load_server_metadata()[
            "end_session_endpoint"
        ]
        resp = make_response(redirect(f"{end_session}?{urlencode(params)}"))
        for cookie in request.cookies:
            resp.delete_cookie(cookie, path=get_cookie_path())
        return resp

class AuthentikAuthManager(FabAuthManager):

    def get_url_logout(self) -> str | None:
        log.info("Authentik logout initiated")
        return f"{BASE_URL.rstrip('/')}/auth/start-logout"


class AuthentikSecurityManager(FabAirflowSecurityManagerOverride):
    authoauthview = AuthentikAuthRemoteUserView

    def get_oauth_user_info(self, provider, response):
        if provider != "authentik":
            return {}

        # Authlib validates the ID token during the OIDC authorization-code flow.
        # OIDC Core requires the UserInfo subject to match that validated ID token.
        id_token_claims = response.get("userinfo", {})
        user = self.oauth_remotes[provider].userinfo(timeout=10)
        if not id_token_claims.get("sub") or user.get("sub") != id_token_claims["sub"]:
            log.error("Authentik login rejected: userinfo subject does not match ID token")
            return {}

        groups = map_roles(user.get("groups", []))
        if not groups:
            groups = ["Public"]

        session["id_token"] = response["id_token"]
        return {
            "username": user.get("preferred_username"),
            "email": user.get("email"),
            "first_name": user.get("given_name", ""),
            "last_name": user.get("family_name", ""),
            "role_keys": groups,
        }


SECURITY_MANAGER_CLASS = AuthentikSecurityManager
RATELIMIT_STORAGE_URI = os.getenv("REDIS_URI")
