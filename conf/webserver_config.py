import logging
import os

import flask
from airflow import configuration as conf
from airflow.models import Variable
from airflow.www.security import AirflowSecurityManager
from flask import make_response, redirect, session
from flask_appbuilder.security.manager import AUTH_OID
from flask_appbuilder.security.views import AuthOIDView
from flask_appbuilder.views import expose
from flask_login import login_user
from flask_oidc import OpenIDConnect

logger = logging.getLogger(__name__)


# Extending AuthOIDView
class AuthOIDCView(AuthOIDView):

    @expose("/login/", methods=["GET", "POST"])
    def login(self, flag=True):

        sm = self.appbuilder.sm

        @self.appbuilder.sm.oid.require_login
        def handle_login():

            oidc_profile: dict = session["oidc_auth_profile"]

            user = sm.auth_user_oid(oidc_profile["email"])

            if "authentik Admins" in oidc_profile["groups"]:
                if user is None:
                    username = oidc_profile["preferred_username"]

                    email = oidc_profile["email"]

                    full_name = oidc_profile["given_name"]

                    first_name = full_name.split(" ")[0]
                    last_name = full_name.split(" ")[1]

                    role = "Admin"

                    user = sm.add_user(
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        role=sm.find_role(role),
                    )

                if "_flashes" in session.keys():
                    session.pop("_flashes")

                # Check if user is marked as active or inactive
                if not user:
                    return redirect("/unauthorized/")

                login_user(user, remember=False)
                return redirect(self.appbuilder.get_url_for_index)

            return redirect("/unauthorized/")

        return handle_login()

    @expose("/unauthorized/", methods=["GET"])
    def unauthorized(self):
        return make_response("Unauthorized")

    @expose("/logout/", methods=["GET", "POST"])
    def logout(self):
        oidc = self.appbuilder.sm.oid
        if len(session) == 0:
            return redirect("/login/")
        self.revoke_token()
        oidc.logout()
        super(AuthOIDCView, self).logout()
        response = make_response("You have been signed out")
        return response

    def revoke_token(self):
        """Revokes the provided access token. Sends a POST request to the token revocation endpoint"""
        import aiohttp
        import asyncio

        config = session
        access_token = ""
        if "oidc_auth_token" in config.keys():
            access_token = config["oidc_auth_token"]["access_token"]
        payload = {"token": access_token, "token_type_hint": "refresh_token"}

        auth = aiohttp.BasicAuth(
            self.appbuilder.app.config.get("OIDC_CLIENT_ID"),
            self.appbuilder.app.config.get("OIDC_CLIENT_SECRET"),
        )

        # Sends an asynchronous POST request to revoke the token
        async def revoke():
            async with aiohttp.ClientSession() as auth_session:
                async with auth_session.post(
                    self.appbuilder.app.config.get("OIDC_LOGOUT_URI"),
                    data=payload,
                    auth=auth,
                ) as response:
                    logging.info(f"Revoke response {response.status}")

        flask.session.clear()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(revoke())


class OIDCSecurityManager(AirflowSecurityManager):
    """
    Custom security manager class that allows using the OpenID Connection authentication method.
    """

    def __init__(self, appbuilder):
        super(OIDCSecurityManager, self).__init__(appbuilder)
        if self.auth_type == AUTH_OID:
            self.oid = OpenIDConnect(self.appbuilder.get_app)
            self.authoidview = AuthOIDCView


basedir = os.path.abspath(os.path.dirname(__file__))

SECURITY_MANAGER_CLASS = OIDCSecurityManager
# The SQLAlchemy connection string.
SQLALCHEMY_DATABASE_URI = conf.conf.get("database", "SQL_ALCHEMY_CONN")

# Flask-WTF flag for CSRF
CSRF_ENABLED = True

AUTH_TYPE = AUTH_OID
OIDC_COOKIE_SECURE = True
OIDC_ID_TOKEN_COOKIE_SECURE = True
OIDC_USER_INFO_ENABLED = True
CUSTOM_SECURITY_MANAGER = OIDCSecurityManager

url = conf.conf.get("webserver", "BASE_URL")

OIDC_CLIENT_SECRETS = {
    "web": {
        "issuer": f"{Variable.get("ISSUER")}",
        "client_id": Variable.get("CLIENT_ID"),
        "client_secret": Variable.get("CLIENT_SECRET"),
        "auth_uri": f'{Variable.get("ISSUER")}/authorize/',
        "redirect_urls": [url],
        "token_uri": f'{Variable.get("ISSUER")}/token/',
        "userinfo_uri": f'{Variable.get("ISSUER")}/userinfo/',
    }
}

OIDC_APPCONFIG = OIDC_CLIENT_SECRETS

# Ensure that the logout/revoke URL is specified in the client secrets file
OIDC_URL = OIDC_APPCONFIG.get("web", {}).get("issuer")
if not OIDC_URL:
    raise ValueError("Invalid OIDC client configuration, Iowa OIDC URI not specified.")

OIDC_LOGOUT_URI = f"{OIDC_URL}/airflow/end-session/"

OIDC_SCOPES = ["openid", "profile", "email"]

# Allow user self registration
AUTH_USER_REGISTRATION = False

OPENID_PROVIDERS = [{"name": "Authentik", "url": f"{OIDC_URL}/authorize/"}]
