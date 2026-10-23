"""Try the multi-user UI without a model API key.

    uv run examples/demo.py
    # open http://127.0.0.1:8000 — alice / bob / admin, password "demo-password"

Seeds three accounts in ./demo-data and answers every message with a canned
reply, so the sign-in, isolation, read-only admin view, audit log, and
account disabling can all be clicked through.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from lovia import Agent
from lovia.testing import ScriptedProvider, text
from lovia.web import serve

from lovia_multiuser import Accounts, User, create_multiuser_app

DATA = Path("demo-data")
PASSWORD = "demo-password"


def agents(user: User, home: Path) -> Agent:
    reply = text(f"（演示模式）{user.name}，收到。配置真实模型见 examples/serve.py。")
    return Agent(name="assistant", model=ScriptedProvider([reply] * 10_000))


async def seed() -> None:
    accounts = Accounts(DATA / "accounts.db")
    existing = {u.id for u in await accounts.list()}
    for user_id, name, admin in (
        ("alice", "Alice", False),
        ("bob", "Bob", False),
        ("admin", "管理员", True),
    ):
        if user_id not in existing:
            await accounts.add(user_id, PASSWORD, name=name, admin=admin)


if __name__ == "__main__":
    asyncio.run(seed())
    app = create_multiuser_app(agents, data_dir=DATA, app_options={"titles": False})
    serve(app, host="127.0.0.1", port=int(os.environ.get("LOVIA_MU_PORT") or "8000"))
