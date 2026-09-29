"""Swap the reference sign-in for your SSO.

Here an authenticating reverse proxy (oauth2-proxy, nginx ``auth_request``,
a corporate gateway) signs users in and forwards their id in a header. The
app only needs ``authenticate(request) -> user id``; roles and account status
still come from the directory.

Only run this behind that proxy, and make sure the proxy strips any
client-sent copy of the header — otherwise anyone can claim any user.

    LOVIA_MODEL=... python examples/proxy_auth.py
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request
from lovia import Agent, model_from_env
from lovia.web import serve

from lovia_multiuser import Accounts, User, create_multiuser_app

MODEL = model_from_env()


class ProxyHeaderAuth:
    def __init__(self, header: str = "X-Forwarded-User") -> None:
        self.header = header

    async def authenticate(self, request: Request) -> str | None:
        return request.headers.get(self.header) or None


def agents(user: User, home: Path) -> Agent:
    return Agent(name="assistant", model=MODEL)


if __name__ == "__main__":
    app = create_multiuser_app(
        agents,
        data_dir="data",
        # Still the reference directory for roles and disabling; point this at
        # your user system instead by implementing lovia_multiuser.Directory.
        directory=Accounts(Path("data") / "accounts.db"),
        auth=ProxyHeaderAuth(),
        # The proxy's sign-in page; {next} is the page to come back to.
        login_url=os.environ.get("LOGIN_URL", "/oauth2/start?rd={next}"),
    )
    serve(app, host="127.0.0.1", port=8000)
