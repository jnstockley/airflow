import os

from airflow.models import Variable
from flask import redirect
from flask_appbuilder import expose
from flask_appbuilder.security.views import AuthOAuthView
from flask_login import logout_user
from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from typing import Any, Optional
import jwt
from jwt import PyJWKClient

FAB_ADMIN_ROLE = "Admin"
FAB_PUBLIC_ROLE = "Public"  # The 'Public' role is given no permissions

AUTHENTIK_ADMIN_ROLE = "authentik Admins"
PROVIDER_NAME = "Authentik"
AUTHENTIK_APP_NANE = os.getenv("AUTHENTIK_APP_NANE")
JWKS_URL = f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NANE}/jwks/"


def map_roles(team_list: list) -> list:
    team_role_map = {
        AUTHENTIK_ADMIN_ROLE: FAB_ADMIN_ROLE,
    }
    return list(set(team_role_map.get(team, FAB_PUBLIC_ROLE) for team in team_list))


class AuthentikAuthRemoteUserView(AuthOAuthView):
    @expose("/login/")
    @expose("/login/<provider>")
    @expose("/login/<provider>/<register>")
    def login(self, provider: Optional[str] = PROVIDER_NAME, register=None):
        return super().login(provider)

    @expose("/logout/", methods=["GET", "POST"])
    def logout(self):
        logout_user()
        return redirect(
            f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NANE}/end-session/"
        )


class AuthentikRoleAuthorizer(FabAirflowSecurityManagerOverride):
    authoauthview = AuthentikAuthRemoteUserView

    def get_oauth_user_info(self, provider: str, resp: Any) -> dict:
        access_token = resp.get("access_token")
        algos = ["RS256"]
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0"
        }
        jwks_client = PyJWKClient(JWKS_URL, headers=headers)
        signing_key = jwks_client.get_signing_key_from_jwt(access_token)
        audience = resp["userinfo"]["aud"]
        subject = resp["userinfo"]["sub"]
        issuer = resp["userinfo"]["iss"]
        token_data = jwt.decode(
            access_token,
            signing_key.key,
            audience=audience,
            subject=subject,
            issuer=issuer,
            algorithms=algos,
            verify=True,
        )
        roles = map_roles(token_data["groups"])
        full_name = token_data.get("given_name")
        return {
            "username": token_data.get("preferred_username"),
            "first_name": full_name.split(" ")[0],
            "last_name": full_name.split(" ")[1],
            "email": token_data.get("email"),
            "role_keys": roles,
        }
