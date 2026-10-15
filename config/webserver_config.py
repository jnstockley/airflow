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
# Airflow's built-in Public role has no permissions and is the registration fallback until
# an allowlisted Authentik group assigns Viewer or Admin at login.
AUTH_USER_REGISTRATION_ROLE = "Public"
AUTH_ROLES_SYNC_AT_LOGIN = True
CSRF_ENABLED = True

BASE_URL = conf.get("api", "base_url")

AUTHENTIK_APP_NAME = os.environ["AUTHENTIK_APP_NAME"]
# This is the Authentik instance URL (for example, https://auth.example.com), not the
# application-specific issuer value published in OIDC discovery metadata.
AUTHENTIK_BASE_URL = Variable.get("AUTHENTIK_BASE_URL").rstrip("/")

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
            "server_metadata_url": (
                f"{AUTHENTIK_BASE_URL}/application/o/{AUTHENTIK_APP_NAME}/.well-known/openid-configuration"
            ),
            "client_kwargs": {
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        },
    }
]


def map_roles(team_list: object) -> list[str]:
    team_role_map = {
        "authentik Admins": "Admin",
        "Airflow Access": "Viewer",
    }
    if not isinstance(team_list, (list, tuple, set)):
        return []

    roles = {
        team_role_map[team]
        for team in team_list
        if isinstance(team, str) and team in team_role_map
    }
    # Admin membership takes precedence, and sorting keeps the result deterministic.
    if "Admin" in roles:
        return ["Admin"]
    return sorted(roles)


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
        params = {
            "client_id": Variable.get("CLIENT_ID"),
            "post_logout_redirect_uri": f"{BASE_URL.rstrip('/')}/auth/logout-complete",
        }
        if session.get("id_token"):
            params["id_token_hint"] = session["id_token"]

        # Prefer the discovered endpoint, but keep logout functional if discovery is temporarily
        # unavailable. Authentik defines this application-specific endpoint by its slug.
        try:
            end_session = self.appbuilder.sm.oauth_remotes["authentik"].load_server_metadata()[
                "end_session_endpoint"
            ]
        except Exception as err:
            log.warning("Could not load Authentik OIDC metadata during logout: %s", err)
            end_session = (
                f"{AUTHENTIK_BASE_URL}/application/o/{AUTHENTIK_APP_NAME}/end-session/"
            )

        # End the local session regardless of whether Authentik metadata was available.
        logout_user()
        session.clear()
        resp = make_response(redirect(f"{end_session}?{urlencode(params)}"))
        for cookie in request.cookies:
            resp.delete_cookie(cookie, path=get_cookie_path())
        return resp

    @expose('/logout-complete')
    def logout_complete(self):
        """Return the browser to Airflow after Authentik completes RP-initiated logout."""
        return redirect(BASE_URL)

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
        subject = id_token_claims.get("sub")
        if not isinstance(subject, str) or not subject or user.get("sub") != subject:
            log.error("Authentik login rejected: userinfo subject does not match ID token")
            return {}

        email = user.get("email")
        if not isinstance(email, str) or not email.strip():
            log.error("Authentik login rejected: UserInfo has no usable email claim")
            return {}
        email = email.strip()

        # The validated subject is the Airflow identity. Authentik is configured to make
        # this subject the user's username.
        username = subject
        legacy_username = f"authentik_{subject}"
        username_user = self.find_user(username=username)
        email_user = self.find_user(email=email)
        if username_user and email_user and username_user != email_user:
            log.error(
                "Authentik login rejected: email is already assigned to a different Airflow user"
            )
            return {}
        if email_user and not username_user:
            if email_user.username != legacy_username:
                log.error(
                    "Authentik login rejected: email is already assigned to a different Airflow user"
                )
                return {}
            # Migrate the account created by the previous authentik_<sub> mapping on first login.
            email_user.username = username
            self.get_session.commit()

        groups = map_roles(user.get("groups", []))
        if not groups:
            groups = ["Public"]

        session["id_token"] = response["id_token"]
        first_name = user.get("given_name") or ""
        last_name = user.get("family_name") or ""
        if not isinstance(first_name, str):
            first_name = ""
        if not isinstance(last_name, str):
            last_name = ""
        # Some Authentik property mappings provide the full name as given_name. If family_name
        # is absent, treat the final word as the surname while preserving multi-word given names.
        if not last_name.strip():
            name_parts = first_name.rsplit(maxsplit=1)
            if len(name_parts) == 2:
                first_name, last_name = name_parts
        return {
            "username": username,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role_keys": groups,
        }


SECURITY_MANAGER_CLASS = AuthentikSecurityManager
RATELIMIT_STORAGE_URI = os.getenv("REDIS_URI")
