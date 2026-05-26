from __future__ import annotations

from hmac import compare_digest

from flask_httpauth import HTTPBasicAuth

import config

auth = HTTPBasicAuth()


@auth.verify_password
def verify_password(username: str, password: str) -> bool:
    if username != 'admin':
        return False
    expected = config.DASHBOARD_PASSWORD or ''
    candidate = password or ''
    return compare_digest(candidate, expected)
