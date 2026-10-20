"""The multi-user app: sign-in, per-user dispatch, admin console.

Every user's full lovia chat UI + API lives at ``/u/<owner>/``, served by
that user's own ``create_app()`` (see :mod:`.tenants`). One rule decides
access: the viewer *is* the owner, or is an admin — and an admin in someone
else's space is read-only and audited.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from lovia import Agent
from lovia.web import ChatStore, ChatUI, create_app
from starlette.types import Message, Receive, Scope, Send

from .accounts import Accounts, Directory, User, valid_user_id
from .admin import build_admin_router
from .audit import AuditLog
from .auth import Authenticator, CookieAuth
from .tenants import Tenants

log = logging.getLogger(__name__)

AgentFactory = Callable[[User, Path], "Agent[Any] | Mapping[str, Agent[Any]]"]
"""``(user, home) -> agent(s)`` — build each user's agents. ``home`` is the
user's private directory: root their workspace and Memory under it, and bind
per-user tools (credentials, the user id) here, never on a shared agent."""

TEMPLATES = Path(__file__).parent / "templates"
SAFE_METHODS = frozenset({"GET", "HEAD"})
# Reads the chat UI repeats on every page view to draw its chrome (sidebar,
# run badges, event stream). Auditing them would bury what an admin actually
# opened — the page, a chat, a file, Memory — so only their denials are kept.
UI_REFRESH = frozenset(
    {
        "/api/info",
        "/api/agents",
        "/api/events",
        "/api/sessions",
        "/api/runs",
        "/api/runs/history",
    }
)
# create_app() options this app owns for every tenant. ``lifespan`` too: Tenants
# enters lovia's own lifespan, so one passed here would silently never run.
_RESERVED = frozenset(
    {"db_path", "store", "session", "ui", "title", "token", "auth", "lifespan"}
)


def templates() -> Jinja2Templates:
    tpl = Jinja2Templates(directory=TEMPLATES)
    tpl.env.filters["ts"] = lambda v: (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(v)) if v else "—"
    )
    return tpl


def error(status: int, code: str, message: str) -> JSONResponse:
    """lovia's error shape, so the chat UI shows ``message`` in its toast."""
    return JSONResponse(
        {"detail": {"code": code, "message": message}}, status_code=status
    )


def load_secret(data_dir: Path) -> str:
    """The cookie-signing secret, generated into ``data_dir/secret`` once."""
    path = data_dir / "secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(secrets.token_urlsafe(32))
    return path.read_text().strip()


@dataclass
class MultiUser:
    """State shared by the routes; ``app.state.multiuser``."""

    directory: Directory
    auth: Authenticator
    tenants: Tenants
    audit: AuditLog
    data_dir: Path
    login_url: str

    def home(self, user_id: str) -> Path:
        # The id becomes a path segment: a custom Directory handing out
        # "a/../b" must fail here, not escape the data directory.
        if not valid_user_id(user_id):
            raise ValueError(
                f"user id {user_id!r} is not a slug (see accounts.USER_ID)"
            )
        return self.data_dir / "users" / user_id

    def has_data(self, user_id: str) -> bool:
        return (self.home(user_id) / "chat.db").exists()

    def login_redirect(self, target: str) -> RedirectResponse:
        return RedirectResponse(
            self.login_url.replace("{next}", quote(target, safe="")), 303
        )

    async def viewer(self, request: Request) -> User | None:
        """The signed-in, active user making ``request``."""
        user_id = await self.auth.authenticate(request)
        if user_id is None:
            return None
        user = await self.directory.get(user_id)
        return None if user is None or user.disabled else user

    async def store(self, user: User) -> ChatStore | None:
        """``user``'s chat store; ``None`` while they have no data, so browsing
        the admin console never creates any."""
        if not self.has_data(user.id):
            return None
        return (await self.tenants.get(user)).state.deps.store

    async def reconcile(self) -> None:
        """Converge the live apps on the directory: close those of disabled or
        removed users, start those of active users with data (a schedule fires
        only while its owner's app is live). Catches changes made outside this
        process, e.g. ``lovia-multiuser users disable``."""
        users = {u.id: u for u in await self.directory.list()}
        for user_id in self.tenants.live_ids():
            user = users.get(user_id)
            if user is None or user.disabled:
                await self.tenants.evict(user_id)
        for user in users.values():
            if not user.disabled and self.has_data(user.id):
                await self.tenants.get(user)


def _dispatcher(mu: MultiUser) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    async def dispatch(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # lovia serves no websockets
            return await send({"type": "websocket.close", "code": 1003})
        request = Request(scope, receive)
        owner_id: str = scope["path_params"]["owner"]
        sub = scope["path"].removeprefix(scope["root_path"]) or "/"
        viewer = await mu.viewer(request)
        if viewer is None:
            if sub.startswith("/api/"):
                response: Response = error(401, "signed_out", "请重新登录")
            else:
                query = scope.get("query_string", b"").decode()
                response = mu.login_redirect(
                    scope["path"] + (f"?{query}" if query else "")
                )
            return await response(scope, receive, send)

        foreign = viewer.id != owner_id
        owner: User | None = viewer
        if foreign:
            # A non-admin never learns whether another owner exists: 404 either way.
            owner = await mu.directory.get(owner_id) if viewer.admin else None
        # lovia's bundled assets, and ours (ChatUI.assets, served under /ui).
        audited = foreign and not sub.startswith(("/static/", "/ui/"))
        query = scope.get("query_string", b"").decode()
        detail = f"{scope['method']} {sub}" + (f"?{query}" if query else "")

        async def record(status: int) -> None:
            await mu.audit.record(
                viewer.id, "http", owner=owner_id, detail=detail, status=status
            )

        async def deny(status: int, code: str, message: str) -> None:
            if audited:
                await record(status)
            await error(status, code, message)(scope, receive, send)

        if owner is None:
            return await deny(404, "not_found", "not found")
        if foreign and scope["method"] not in SAFE_METHODS:
            return await deny(
                403, "read_only", "管理员只能查看其他用户的记录，不能修改"
            )

        state = scope.setdefault("state", {})
        state["viewer"], state["owner"] = viewer, owner
        app = await mu.tenants.get(owner)
        # Starlette's url_for resolves against scope["router"] under
        # scope["app_root_path"] — both the outer app's by default, which has no
        # "static" route. Point them at the tenant, under /u/<owner>.
        scope["router"], scope["app_root_path"] = app.router, scope["root_path"]

        if audited and sub not in UI_REFRESH:
            inner_send = send

            async def send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    await record(message["status"])
                await inner_send(message)

        await app(scope, receive, send)

    return dispatch


async def _every(seconds: float, job: Callable[[], Awaitable[None]]) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await job()
        except Exception:  # keep reconciling after a transient failure
            log.exception("reconcile failed")


def create_multiuser_app(
    agent_factory: AgentFactory,
    *,
    data_dir: str | Path,
    directory: Directory | None = None,
    auth: Authenticator | None = None,
    login_url: str = "/login?next={next}",
    title: str = "lovia",
    chat_ui: ChatUI | None = None,
    app_options: Mapping[str, Any] | None = None,
    reconcile_interval: float = 30.0,
) -> FastAPI:
    """Build the multi-user app.

    ``directory`` (default: :class:`Accounts` in ``data_dir/accounts.db``)
    says who exists, who is an admin, who is disabled; ``auth`` (default: the
    reference :class:`CookieAuth` sign-in) says who is asking. ``login_url``
    is where a signed-out browser goes — ``{next}`` becomes the page to return
    to. ``chat_ui`` customizes the chat page's blank state; ``app_options``
    are passed to every user's ``create_app()`` (``max_background_runs``,
    ``budget``, ``followups``, …).
    """
    data = Path(data_dir)
    options = dict(app_options or {})
    if reserved := sorted(_RESERVED & set(options)):
        raise ValueError(f"app_options may not set {reserved}; this app owns them")
    if directory is None:
        directory = Accounts(data / "accounts.db")
    if auth is None:
        if not isinstance(directory, Accounts):
            raise ValueError("a custom directory= needs its own auth= as well")
        auth = CookieAuth(directory, load_secret(data))

    ui = replace(chat_ui or ChatUI(), assets=TEMPLATES / "chat", login_url=login_url)

    def build(user: User) -> FastAPI:
        home = mu.home(user.id)
        home.mkdir(parents=True, exist_ok=True)
        return create_app(
            agent_factory(user, home),
            db_path=home / "chat.db",
            title=title,
            ui=ui,
            **options,
        )

    mu = MultiUser(
        directory=directory,
        auth=auth,
        tenants=Tenants(build),
        audit=AuditLog(data / "audit.db"),
        data_dir=data,
        login_url=login_url,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        await mu.reconcile()
        task = asyncio.create_task(_every(reconcile_interval, mu.reconcile))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await mu.tenants.aclose()

    app = FastAPI(title=title, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.multiuser = mu
    tpl = templates()

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def home(request: Request) -> Response:
        viewer = await mu.viewer(request)
        if viewer is None:
            return mu.login_redirect("/")
        return RedirectResponse("/admin" if viewer.admin else f"/u/{viewer.id}/", 303)

    if hasattr(auth, "router"):  # the reference sign-in brings its own pages
        app.include_router(auth.router(tpl))
    app.include_router(build_admin_router(mu, tpl))
    app.mount("/u/{owner}", _dispatcher(mu))
    return app
