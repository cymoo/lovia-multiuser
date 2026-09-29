"""Serve a real agent to many users.

    lovia-multiuser users add admin --admin     # first admin (prompts for a password)
    lovia-multiuser users add alice --name Alice
    LOVIA_MODEL=... python examples/serve.py    # see lovia's model_from_env

Each user's agent is built by ``agents(user, home)``: its workspace and
Memory live under the user's own directory. The workspace is ``readonly`` on
purpose — in one process, a shell or a writable-anywhere workspace would let
a user reach other users' files (see docs/design.md, "安全边界").
"""

from __future__ import annotations

import os
from pathlib import Path

from lovia import Agent, Memory, model_from_env
from lovia.web import SURFACE_NOTE, ChatUI, serve
from lovia.workspace import Workspace

from lovia_multiuser import Accounts, CookieAuth, User, create_multiuser_app
from lovia_multiuser.app import load_secret

DATA = Path(os.environ.get("LOVIA_MU_DATA", "data"))
MODEL = model_from_env()


def agents(user: User, home: Path) -> Agent:
    files = home / "files"
    files.mkdir(exist_ok=True)
    return Agent(
        name="assistant",
        instructions=(
            f"You are a helpful assistant for {user.name}. Reply in the user's "
            "language.\n\n" + SURFACE_NOTE
        ),
        model=MODEL,
        workspace=Workspace.local(str(files), mode="readonly"),
        plugins=[Memory(home / "memory")],
    )


def main() -> None:
    accounts = Accounts(DATA / "accounts.db")
    # Behind TLS, mark the session cookie Secure (LOVIA_MU_SECURE=1).
    auth = CookieAuth(
        accounts, load_secret(DATA), secure=os.environ.get("LOVIA_MU_SECURE") == "1"
    )
    app = create_multiuser_app(
        agents,
        data_dir=DATA,
        directory=accounts,
        auth=auth,
        title="Assistant",
        chat_ui=ChatUI(empty_title="有什么可以帮你？"),
        app_options={"max_background_runs": 4},
    )
    # One worker: live runs are held in process memory.
    serve(app, host=os.environ.get("HOST", "127.0.0.1"), port=8000)


if __name__ == "__main__":
    main()
