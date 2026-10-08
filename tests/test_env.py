import asyncio
import os
from pathlib import Path

import pytest

from lovia_multiuser import Accounts
from lovia_multiuser.__main__ import main
from lovia_multiuser.env import data_dir, load_env


@pytest.fixture
def clean_env(monkeypatch):
    """Variables a test's .env may set, restored (unset) afterwards."""
    for name in ("LMU_TEST_A", "LMU_TEST_B", "LOVIA_MU_DATA"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def test_load_env_finds_the_file_in_a_parent_and_real_env_wins(
    tmp_path, monkeypatch, clean_env
):
    (tmp_path / ".env").write_text("LMU_TEST_A=from-file\nLMU_TEST_B=from-file\n")
    sub = tmp_path / "examples"
    sub.mkdir()
    monkeypatch.chdir(sub)
    monkeypatch.setenv("LMU_TEST_B", "from-env")

    assert load_env() == tmp_path / ".env"
    assert os.environ["LMU_TEST_A"] == "from-file"
    assert os.environ["LMU_TEST_B"] == "from-env"


def test_load_env_without_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_env() is None


def test_data_dir_defaults_to_data(monkeypatch, clean_env):
    assert data_dir() == Path("data")
    monkeypatch.setenv("LOVIA_MU_DATA", "/srv/lovia")
    assert data_dir() == Path("/srv/lovia")


def test_bootstrap_admin_only_on_an_empty_directory(tmp_path):
    accounts = Accounts(tmp_path / "accounts.db")

    async def scenario():
        password = await accounts.bootstrap_admin()
        assert password and len(password) >= 12
        admin = await accounts.verify("admin", password)
        assert admin is not None and admin.admin
        assert await accounts.bootstrap_admin() is None  # never twice

    asyncio.run(scenario())


def test_cli_reads_the_data_dir_from_env_file(tmp_path, monkeypatch, capsys, clean_env):
    (tmp_path / ".env").write_text("LOVIA_MU_DATA=store\n")
    monkeypatch.chdir(tmp_path)
    asyncio.run(Accounts(tmp_path / "store" / "accounts.db").add("zoe", "password123"))

    assert main(["users", "list"]) == 0
    assert capsys.readouterr().out.startswith("zoe\t")
