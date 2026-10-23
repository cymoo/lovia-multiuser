from __future__ import annotations

import asyncio
import functools
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lovia import Agent
from lovia.testing import ScriptedProvider, text

from lovia_multiuser import Accounts, MultiUser, User, create_multiuser_app
from lovia_multiuser.auth import COOKIE

PASSWORD = "correct horse"


def agents(user: User, home: Path) -> Agent[Any]:
    # A fresh script per build: ScriptedProvider pops a shared queue.
    return Agent(
        name="bot", model=ScriptedProvider([text(f"reply for {user.id}")] * 50)
    )


@dataclass
class Browser:
    """One signed-in user on the shared TestClient.

    Every role shares one client — one event loop — because the tenants'
    background tasks live on the loop that started them."""

    client: TestClient
    cookie: str | None

    def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        self.client.cookies.clear()
        if self.cookie:
            self.client.cookies.set(COOKIE, self.cookie)
        kw.setdefault("follow_redirects", False)
        return self.client.request(method, url, **kw)

    def get(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("POST", url, **kw)

    def delete(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("DELETE", url, **kw)

    def chat(self, owner: str, message: str) -> str:
        r = self.post(f"/u/{owner}/api/chat", json={"message": message})
        assert r.status_code == 200, r.text
        return r.json()["session_id"]


@dataclass
class Env:
    app: FastAPI
    client: TestClient
    data: Path

    @property
    def mu(self) -> MultiUser:
        return self.app.state.multiuser

    def as_(self, user_id: str) -> Browser:
        return Browser(self.client, self.mu.auth.issue(user_id))

    def anon(self) -> Browser:
        return Browser(self.client, None)

    def run(self, fn: Any, *args: Any, **kw: Any) -> Any:
        """Await ``fn(*args, **kw)`` on the app's event loop."""
        return self.client.portal.call(functools.partial(fn, *args, **kw))


@pytest.fixture
def data(tmp_path: Path) -> Path:
    accounts = Accounts(tmp_path / "accounts.db")

    async def seed() -> None:
        await accounts.add("alice", PASSWORD, name="Alice")
        await accounts.add("bob", PASSWORD, name="Bob")
        await accounts.add("root", PASSWORD, name="Root", admin=True)

    asyncio.run(seed())
    return tmp_path


@pytest.fixture
def env(data: Path) -> Iterator[Env]:
    app = create_multiuser_app(
        agents,
        data_dir=data,
        app_options={"titles": False, "scheduler_poll": 0.05},
    )
    with TestClient(app) as client:
        yield Env(app, client, data)


def session_ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [s["id"] for s in response.json()]
