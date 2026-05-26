from __future__ import annotations

from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()


@auth.verify_password
def verify_password(username: str, password: str) -> bool:
    del username, password
    # Access is restricted at network level (VPN), so app auth is transparent.
    return True
