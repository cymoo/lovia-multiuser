"""One lovia ``create_app()`` per user, built on first use.

A *live* tenant runs its app's lifespan: scheduler, background runs, the
``/api/events`` bus. A *dormant* one never enters it, so it only serves reads —
what an admin needs to audit a disabled user without reviving their schedules.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

from fastapi import FastAPI

from .accounts import User


@dataclass
class _Tenant:
    app: FastAPI
    live: bool
    stack: AsyncExitStack = field(default_factory=AsyncExitStack)


class Tenants:
    def __init__(self, build: Callable[[User], FastAPI]) -> None:
        self._build = build
        self._tenants: dict[str, _Tenant] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, user: User) -> FastAPI:
        """``user``'s app: live for an active account, dormant for a disabled
        one. A cached app of the other kind is closed and rebuilt."""
        live = not user.disabled
        async with self._locks.setdefault(user.id, asyncio.Lock()):
            tenant = self._tenants.get(user.id)
            if tenant is not None and tenant.live != live:
                await self._close(user.id)
                tenant = None
            if tenant is None:
                tenant = _Tenant(self._build(user), live)
                if live:
                    # Starlette never runs a mounted app's lifespan: enter it here.
                    deps = tenant.app.state.deps
                    await tenant.stack.enter_async_context(deps.lifespan())
                self._tenants[user.id] = tenant
            return tenant.app

    def is_live(self, user_id: str) -> bool:
        tenant = self._tenants.get(user_id)
        return tenant is not None and tenant.live

    def live_ids(self) -> list[str]:
        return [uid for uid, t in self._tenants.items() if t.live]

    async def evict(self, user_id: str) -> None:
        """Close ``user_id``'s app: live runs wind down (leaving resumable
        checkpoints), its schedules stop firing, open event streams end."""
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            await self._close(user_id)

    async def _close(self, user_id: str) -> None:
        tenant = self._tenants.pop(user_id, None)
        if tenant is not None:
            await tenant.stack.aclose()

    async def aclose(self) -> None:
        for user_id in list(self._tenants):
            await self.evict(user_id)
