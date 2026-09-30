"""Serve a real agent to many users — see README.md for the full walkthrough.

    set -a && source .env && set +a            # LOVIA_MODEL + the provider's key
    lovia-multiuser users add admin --admin     # at least one account first
    python examples/serve.py

Settings (environment): LOVIA_MU_DATA (default ./data), HOST (127.0.0.1),
PORT (8000), LOVIA_MU_SECURE=1 behind HTTPS.

Each user's agent is built by ``agents(user, home)``: its workspace and
Memory live under the user's own directory. The workspace is ``readonly`` on
purpose — in one process, a shell or a writable-anywhere workspace would let
a user reach other users' files (see docs/design.md, "安全边界").
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from lovia import Agent, Memory, enable_logging, model_from_env
from lovia.web import SURFACE_NOTE, ChatUI, serve
from lovia.workspace import Workspace

from lovia_multiuser import Accounts, CookieAuth, User, create_multiuser_app
from lovia_multiuser.app import load_secret

DATA = Path(os.environ.get("LOVIA_MU_DATA", "data"))
MODEL = model_from_env()  # raises with a setup hint when LOVIA_MODEL is unset


def agents(user: User, home: Path) -> Agent:
    files = home / "files"
    files.mkdir(exist_ok=True)
    return Agent(
        name="assistant",
        instructions=(
            "You are a helpful assistant. The person you are talking to is "
            f"{user.name}. Reply in their language.\n\n" + SURFACE_NOTE
        ),
        model=MODEL,
        # Uploads land in files/uploads/; the agent reads them but can't write
        # files or run commands.
        workspace=Workspace.local(str(files), mode="readonly"),
        plugins=[Memory(home / "memory")],
    )


def main() -> None:
    enable_logging()
    accounts = Accounts(DATA / "accounts.db")
    if not asyncio.run(accounts.list()):
        raise SystemExit(
            f"no accounts in {DATA}/ yet — create an admin first:\n"
            f"  lovia-multiuser --data {DATA} users add admin --admin"
        )
    # Behind HTTPS, mark the session cookie Secure (LOVIA_MU_SECURE=1).
    auth = CookieAuth(
        accounts, load_secret(DATA), secure=os.environ.get("LOVIA_MU_SECURE") == "1"
    )
    app = create_multiuser_app(
        agents,
        data_dir=DATA,
        directory=accounts,
        auth=auth,
        title="Assistant",
        chat_ui=ChatUI(
            empty_title="有什么可以帮你？",
            empty_description="可以上传文件让我阅读，我也会记住你告诉我的偏好。",
        ),
        app_options={"max_background_runs": 4},
    )
    # One worker: live runs are held in process memory.
    serve(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
