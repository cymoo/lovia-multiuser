"""Authentication: who is making this request.

:class:`Authenticator` is the seam — anything with ``authenticate(request)``
returning a user id. :class:`CookieAuth` is the reference: a password form and
an HMAC-signed session cookie. Replace it with your SSO (a trusted proxy
header, OIDC, a JWT) and keep everything else.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Protocol

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .accounts import Accounts

COOKIE = "lmu_session"


class Authenticator(Protocol):
    async def authenticate(self, request: Request) -> str | None:
        """The signed-in user's id, or ``None``. Roles and account status come
        from the :class:`~lovia_multiuser.accounts.Directory`, not from here."""
        ...


def safe_next(target: str | None) -> str:
    """``target`` if it is a path on this site, else ``/`` — no open redirect."""
    if target and target.startswith("/") and not target.startswith(("//", "/\\")):
        return target
    return "/"


class CookieAuth:
    """Reference sign-in: password form + signed ``<id>.<issued>.<sig>`` cookie.

    The cookie is ``HttpOnly`` and ``SameSite=Lax``: the bundled chat UI's
    ``EventSource`` and image requests carry it (they cannot send headers),
    and cross-site POSTs don't — the CSRF defence for every write here.
    """

    def __init__(
        self,
        accounts: Accounts,
        secret: str,
        *,
        max_age: int = 7 * 86400,
        secure: bool = False,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("secret must be at least 16 characters")
        self.accounts = accounts
        self._key = secret.encode()
        self.max_age = max_age
        self.secure = secure

    def _sign(self, payload: str) -> str:
        mac = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def issue(self, user_id: str, *, now: float | None = None) -> str:
        payload = f"{user_id}.{int(time.time() if now is None else now)}"
        return f"{payload}.{self._sign(payload)}"

    async def authenticate(self, request: Request) -> str | None:
        try:
            user_id, issued, sig = request.cookies.get(COOKIE, "").rsplit(".", 2)
            age = time.time() - int(issued)
        except ValueError:
            return None
        if not hmac.compare_digest(sig, self._sign(f"{user_id}.{issued}")):
            return None
        return user_id if 0 <= age <= self.max_age else None

    def router(self, templates: Jinja2Templates) -> APIRouter:
        router = APIRouter()

        def page(request: Request, status: int = 200, **ctx: object) -> Response:
            ctx.setdefault("next", safe_next(request.query_params.get("next")))
            return templates.TemplateResponse(
                request, "login.html", {"error": None, **ctx}, status_code=status
            )

        @router.get("/login", include_in_schema=False)
        async def login_form(request: Request) -> Response:
            return page(request, bye="bye" in request.query_params)

        @router.post("/login", include_in_schema=False)
        async def login(
            request: Request,
            user_id: str = Form(...),
            password: str = Form(...),
            next: str = Form("/"),
        ) -> Response:
            user = await self.accounts.verify(user_id.strip().lower(), password)
            if user is None:
                return page(
                    request, 401, error="用户名或密码错误", next=safe_next(next)
                )
            if user.disabled:
                return page(request, 403, error="该账号已停用", next=safe_next(next))
            response = RedirectResponse(safe_next(next), status_code=303)
            response.set_cookie(
                COOKIE,
                self.issue(user.id),
                max_age=self.max_age,
                httponly=True,
                samesite="lax",
                secure=self.secure,
            )
            return response

        @router.post("/logout", include_in_schema=False)
        async def logout() -> Response:
            response = RedirectResponse("/login?bye=1", status_code=303)
            response.delete_cookie(COOKIE)
            return response

        return router
