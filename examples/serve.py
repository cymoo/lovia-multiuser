"""Serve a real agent to many users — see README.md for the walkthrough.

    uv run examples/serve.py        # or: python examples/serve.py

Settings come from the environment or the project's ``.env`` (loaded
automatically): LOVIA_MODEL plus the provider's key are required; optional are
LOVIA_MU_DATA (./data), LOVIA_MU_HOST (127.0.0.1), LOVIA_MU_PORT (8000), and
LOVIA_MU_SECURE=1 behind HTTPS. The first start creates an ``admin`` account
and prints its password once.

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
from lovia_multiuser.env import data_dir, load_env

ENV_FILE = load_env()
DATA = data_dir()
MODEL = model_from_env(required=False)


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
    if MODEL is None:
        where = (
            f"已加载 {ENV_FILE}，但其中"
            if ENV_FILE
            else "没有找到 .env 文件，环境变量中也"
        )
        raise SystemExit(
            f"{where}没有 LOVIA_MODEL。\n把 .env.example 复制为 .env，"
            "填入 LOVIA_MODEL 和对应的 API key，再重新运行。"
        )
    enable_logging()
    accounts = Accounts(DATA / "accounts.db")
    password = asyncio.run(accounts.bootstrap_admin())
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

    host = os.environ.get("LOVIA_MU_HOST") or "127.0.0.1"
    port = int(os.environ.get("LOVIA_MU_PORT") or "8000")
    browse = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    # stdout on purpose: the password is shown once, whatever the log level.
    if password:
        print(
            f"\n首次启动，已创建管理员账号：admin，密码：{password}\n"
            "（只显示这一次。修改密码：lovia-multiuser users passwd admin）",
            flush=True,
        )
    print(f"\n模型：{MODEL}　数据目录：{DATA.resolve()}", flush=True)
    print(f"打开 http://{browse}:{port} 登录\n", flush=True)
    # One worker: live runs are held in process memory.
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
