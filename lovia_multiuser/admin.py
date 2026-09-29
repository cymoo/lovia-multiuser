"""Admin console: every user, their chats, cross-user search, audit log,
and disabling accounts. Chats open in the owner's own chat UI, read-only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from lovia.web import ChatMeta

from .accounts import User

if TYPE_CHECKING:
    from .app import MultiUser


@dataclass(frozen=True)
class UserSummary:
    user: User
    live: bool
    chats: int
    last_active: float | None


@dataclass(frozen=True)
class Hit:
    user: User
    chat: ChatMeta


# Sidebar-sized pages: enough for a console, bounded per user.
_PER_USER = 500


def build_admin_router(mu: MultiUser, templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/admin", include_in_schema=False)

    async def require_admin(request: Request) -> User:
        viewer = await mu.viewer(request)
        if viewer is None:
            target = request.url.path + (
                f"?{request.url.query}" if request.url.query else ""
            )
            raise HTTPException(
                303, headers={"location": mu.login_redirect(target).headers["location"]}
            )
        if not viewer.admin:
            raise HTTPException(404)
        return viewer

    def render(request: Request, name: str, viewer: User, **ctx: object) -> Response:
        return templates.TemplateResponse(
            request, f"admin/{name}", {"viewer": viewer, **ctx}
        )

    async def target(user_id: str) -> User:
        user = await mu.directory.get(user_id)
        if user is None:
            raise HTTPException(404)
        return user

    @router.get("")
    async def index(
        request: Request, viewer: User = Depends(require_admin)
    ) -> Response:
        rows, recent = [], []
        for user in await mu.directory.list():
            store = await mu.store(user)
            chats = list(await store.list(limit=_PER_USER)) if store else []
            rows.append(
                UserSummary(
                    user,
                    mu.tenants.is_live(user.id),
                    len(chats),
                    max((c.updated_at for c in chats), default=None),
                )
            )
            recent += [Hit(user, c) for c in chats]
        recent.sort(key=lambda h: h.chat.updated_at, reverse=True)
        return render(
            request,
            "index.html",
            viewer,
            rows=rows,
            recent=recent[:20],
            per_user=_PER_USER,
        )

    @router.get("/users/{user_id}")
    async def user_detail(
        request: Request, user_id: str, viewer: User = Depends(require_admin)
    ) -> Response:
        user = await target(user_id)
        store = await mu.store(user)
        return render(
            request,
            "user.html",
            viewer,
            user=user,
            live=mu.tenants.is_live(user.id),
            chats=await store.list(limit=_PER_USER) if store else [],
            schedules=await store.list_schedules() if store else [],
            audit=await mu.audit.recent(owner=user.id, limit=50),
        )

    @router.post("/users/{user_id}/disable")
    async def disable(user_id: str, viewer: User = Depends(require_admin)) -> Response:
        if user_id == viewer.id:
            raise HTTPException(400, "不能停用自己的账号")
        await target(user_id)
        await mu.directory.set_disabled(user_id, True)
        # Right away, not at the next reconcile: runs stop, schedules stop firing.
        await mu.tenants.evict(user_id)
        await mu.audit.record(viewer.id, "user.disable", owner=user_id)
        return RedirectResponse(f"/admin/users/{user_id}", 303)

    @router.post("/users/{user_id}/enable")
    async def enable(user_id: str, viewer: User = Depends(require_admin)) -> Response:
        await target(user_id)
        await mu.directory.set_disabled(user_id, False)
        user = await target(user_id)
        if mu.has_data(user_id):
            await mu.tenants.get(user)  # live again: their schedules resume
        await mu.audit.record(viewer.id, "user.enable", owner=user_id)
        return RedirectResponse(f"/admin/users/{user_id}", 303)

    @router.get("/search")
    async def search(
        request: Request, q: str = "", viewer: User = Depends(require_admin)
    ) -> Response:
        q = q.strip()
        hits: list[Hit] = []
        if q:
            for user in await mu.directory.list():
                store = await mu.store(user)
                if store is not None:
                    hits += [Hit(user, c) for c in await store.search(q, limit=50)]
            hits.sort(key=lambda h: h.chat.updated_at, reverse=True)
        return render(request, "search.html", viewer, q=q, hits=hits)

    @router.get("/audit")
    async def audit(
        request: Request,
        actor: str = "",
        owner: str = "",
        viewer: User = Depends(require_admin),
    ) -> Response:
        entries = await mu.audit.recent(
            actor=actor or None, owner=owner or None, limit=500
        )
        return render(
            request, "audit.html", viewer, entries=entries, actor=actor, owner=owner
        )

    return router
