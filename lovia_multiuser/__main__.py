"""lovia-multiuser: manage the reference user directory and read the audit log.

    lovia-multiuser users add alice --name Alice [--admin]
    lovia-multiuser users list | passwd ID | disable ID | enable ID
    lovia-multiuser audit [--actor ID] [--owner ID] [--limit N]

The data directory is --data, else LOVIA_MU_DATA (read from the project's
.env too), else ./data. Serving is code — the agents are yours: see
examples/serve.py.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import time
from pathlib import Path

from .accounts import Accounts
from .audit import AuditLog
from .env import data_dir, load_env

MIN_PASSWORD = 8


def _read_password(user_id: str) -> str:
    if sys.stdin.isatty():
        password = getpass.getpass(f"{user_id} 的密码: ")
        if getpass.getpass("再输入一次: ") != password:
            raise SystemExit("两次输入不一致")
    else:  # scripted: first line of stdin
        password = sys.stdin.readline().rstrip("\n")
    if len(password) < MIN_PASSWORD:
        raise SystemExit(f"密码至少 {MIN_PASSWORD} 位")
    return password


async def _run(args: argparse.Namespace) -> None:
    data = Path(args.data) if args.data else data_dir()
    if args.command == "audit":
        entries = await AuditLog(data / "audit.db").recent(
            actor=args.actor, owner=args.owner, limit=args.limit
        )
        for e in entries:
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.ts))
            fields = (
                when,
                e.actor,
                e.owner or "-",
                e.action,
                e.status or "-",
                e.detail,
            )
            print("\t".join(map(str, fields)))
        return

    accounts = Accounts(data / "accounts.db")
    if args.action == "list":
        for u in await accounts.list():
            flags = ",".join(
                f for f, on in (("admin", u.admin), ("disabled", u.disabled)) if on
            )
            print(f"{u.id}\t{u.name}\t{flags}")
    elif args.action == "add":
        user = await accounts.add(
            args.id, _read_password(args.id), name=args.name, admin=args.admin
        )
        print(f"已创建 {user.id}{'（管理员）' if user.admin else ''}")
    elif args.action == "passwd":
        await accounts.set_password(args.id, _read_password(args.id))
        print(f"已更新 {args.id} 的密码")
    else:
        await accounts.set_disabled(args.id, args.action == "disable")
        print(
            f"已{'停用' if args.action == 'disable' else '启用'} {args.id}。"
            "运行中的服务会在下一次同步（默认 30 秒内）停止或启动该用户的应用。"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lovia-multiuser", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--data", help="data directory (default: $LOVIA_MU_DATA, else ./data)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    users = commands.add_parser("users", help="manage users").add_subparsers(
        dest="action", required=True
    )
    users.add_parser("list")
    add = users.add_parser("add")
    add.add_argument("id")
    add.add_argument("--name")
    add.add_argument("--admin", action="store_true")
    for action in ("passwd", "disable", "enable"):
        users.add_parser(action).add_argument("id")

    audit = commands.add_parser("audit", help="print recent audit entries")
    audit.add_argument("--actor")
    audit.add_argument("--owner")
    audit.add_argument("--limit", type=int, default=50)

    args = parser.parse_args(argv)
    load_env()
    try:
        asyncio.run(_run(args))
    except (KeyError, ValueError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
