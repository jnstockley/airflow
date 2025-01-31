import os

from airflow.configuration import conf
from airflow.models import Variable
from cryptography.fernet import Fernet
from flask_appbuilder.security.manager import AUTH_OAUTH

from oidc_authorizer import (
    AuthentikRoleAuthorizer,
    PROVIDER_NAME,
    JWKS_URL,
    AUTHENTIK_APP_NANE,
)

SECURITY_MANAGER_CLASS = AuthentikRoleAuthorizer

# The secret key used to encrypt session cookies
SECRET_KEY = conf.get("webserver", "SECRET_KEY")

# The authentication type
AUTH_TYPE = AUTH_OAUTH

fernet = Fernet(conf.get("core", "FERNET_KEY"))
url = conf.get("webserver", "BASE_URL")

# The OAuth providers configuration
OAUTH_PROVIDERS = [
    {
        "name": PROVIDER_NAME,
        "token_key": "access_token",
        "remote_app": {
            "client_id": Variable.get("CLIENT_ID"),
            "client_secret": Variable.get("CLIENT_SECRET"),
            "api_base_url": f"{Variable.get('ISSUER')}/",
            "server_metadata_url": f"{Variable.get('ISSUER')}/application/o/{AUTHENTIK_APP_NANE}/.well-known/"
            f"openid-configuration",
            "client_kwargs": {
                "scope": "openid profile email",
            },
            "authorize_url": f"{Variable.get('ISSUER')}/application/o/authorize/",
            "access_token_url": f"{Variable.get('ISSUER')}/application/o/token/",
            "request_token_url": None,
            "userinfo_url": f"{Variable.get('ISSUER')}/application/o/userinfo/",
            "jwks_uri": JWKS_URL,
        },
    }
]

# The user self registration
AUTH_USER_REGISTRATION = False

RATELIMIT_STORAGE_URI = os.getenv("REDIS_URI")
