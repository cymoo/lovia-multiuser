import asyncio
import io

import pytest

from lovia_multiuser.__main__ import main
from lovia_multiuser.audit import AuditLog


def run(tmp_path, monkeypatch, *argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return main(["--data", str(tmp_path), *argv])


def test_user_management(tmp_path, monkeypatch, capsys):
    assert (
        run(
            tmp_path,
            monkeypatch,
            "users",
            "add",
            "carol",
            "--name",
            "Carol",
            "--admin",
            stdin="password123\n",
        )
        == 0
    )
    assert (
        run(tmp_path, monkeypatch, "users", "add", "dave", stdin="password123\n") == 0
    )
    assert run(tmp_path, monkeypatch, "users", "disable", "dave") == 0
    capsys.readouterr()

    run(tmp_path, monkeypatch, "users", "list")
    assert capsys.readouterr().out.splitlines() == [
        "carol\tCarol\tadmin",
        "dave\tdave\tdisabled",
    ]


def test_bad_input_is_refused(tmp_path, monkeypatch, capsys):
    assert (
        run(tmp_path, monkeypatch, "users", "add", "Bad Id", stdin="password123\n") == 1
    )
    run(tmp_path, monkeypatch, "users", "add", "erin", stdin="password123\n")
    assert (
        run(tmp_path, monkeypatch, "users", "add", "erin", stdin="password123\n") == 1
    )
    assert run(tmp_path, monkeypatch, "users", "disable", "nobody") == 1
    with pytest.raises(SystemExit):
        run(tmp_path, monkeypatch, "users", "add", "frank", stdin="short\n")


def test_audit_prints_recent_entries(tmp_path, monkeypatch, capsys):
    log = AuditLog(tmp_path / "audit.db")
    asyncio.run(
        log.record(
            "root", "http", owner="alice", detail="GET /api/sessions", status=200
        )
    )
    run(tmp_path, monkeypatch, "audit", "--owner", "alice")
    line = capsys.readouterr().out.strip()
    assert line.endswith("root\talice\thttp\t200\tGET /api/sessions")
