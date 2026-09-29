# AGENTS.md

Onboarding for AI coding assistants. The design and its reasons live in
[docs/design.md](docs/design.md) — read the relevant section before changing
a subsystem.

## What this is

**lovia-multiuser** serves a [lovia](https://github.com/cymoo/lovia) agent to
many users from one process. Each user gets their own lovia `create_app()` at
`/u/<id>/` (own chat DB, scheduler, event bus, workspace, Memory); admins can
open any user's space read-only; every such access is audited. The sign-in is
a reference implementation, meant to be replaced by the business's own.

## Setup & commands

```bash
uv venv && uv pip install -e ".[dev]"
```

| Task | Command |
| --- | --- |
| Test (all) | `pytest` |
| Test (one) | `pytest tests/test_admin.py::test_search_spans_every_user` |
| Lint / format | `ruff check .` / `ruff format .` |
| Try the UI (no API key) | `python examples/demo.py` |
| Manage users | `lovia-multiuser --data data users ...` |

## Architecture

| Module | Role |
| --- | --- |
| `app.py` | `create_multiuser_app()`, the `/u/{owner}` dispatcher, reconcile, `/` |
| `tenants.py` | one `create_app()` per user; *live* (lifespan entered) or *dormant* |
| `auth.py` | `Authenticator` seam + reference `CookieAuth` (login form, signed cookie) |
| `accounts.py` | `Directory` seam + reference `Accounts` (SQLite, scrypt) |
| `audit.py` | append-only audit log (SQLite) |
| `admin.py` + `templates/admin/` | admin console |
| `templates/chat/index.html` | overrides lovia's chat page (user menu, read-only banner) |

Three seams, everything else stays: `Authenticator` (who is asking),
`Directory` (exists / admin / disabled), `agent_factory(user, home)`.

## Invariants — things that will bite you

- **Authorization lives in one place: the dispatcher in `app.py`.** Never add
  per-route owner checks inside a tenant, and never take the owner from a
  request body — isolation comes from users not sharing a store.
- **A foreign owner must look exactly like a missing one** to a non-admin:
  same 404, same body. Don't look the owner up before knowing the viewer is an admin.
- **Admins are read-only in someone else's space**: `SAFE_METHODS` only.
- **Audit**: every request into another user's space is recorded, except
  static assets and successful `UI_REFRESH` reads; denials are always recorded.
  A new chrome endpoint the lovia UI polls on page load belongs in `UI_REFRESH`.
- **The directory is read on every request** — that's what makes disabling
  instant. Don't cache user state without an invalidation story.
- **Never enter a disabled user's lifespan.** Starlette doesn't run a mounted
  app's lifespan, so `Tenants` does — only for active users. A dormant app has
  no scheduler, so an admin reading it doesn't revive the user's schedules.
- **Browsing the console must not create data**: go through `MultiUser.store()`,
  which returns `None` for users without a `chat.db`.
- **`url_for` under `/u/<owner>`** relies on Starlette internals
  (`scope["router"]`, `scope["app_root_path"]`);
  `test_the_chat_page_and_its_assets_live_under_the_prefix` guards it.
- **Workspaces are `readonly` or absent.** The local workspace is a policy gate,
  not a sandbox; shell or `coding`/`trusted` lets one user reach another's files.
- **Per-user identity reaches tools by binding in `agent_factory`** (lovia.web
  passes no `context=` to runs). Never mutate a shared `Agent`.

## Tests

- One `TestClient` per test, shared by every role (`env.as_("alice")`,
  `env.anon()`): tenants' background tasks live on the loop that started them,
  so a second client (second loop) hangs.
- Await app coroutines with `env.run(fn, *args)` (runs on the app's loop).
- Agents use `lovia.testing.ScriptedProvider` — no network. Titles are off in
  the fixture (they would consume scripted replies).

## Conventions

- Code, comments, and this file in English; UI text and `docs/` in Chinese.
- `ruff` governs format + lint. Conventional Commits (`feat`, `fix`, `docs`, …).
- Keep it small: this is a reference to be reshaped by the business, not a
  framework. Prefer a documented seam over a new option.

## Don't

- Don't grant shell or a writable-anywhere workspace in `examples/` or docs.
- Don't add a hard dependency beyond `lovia[web]` and `uvicorn`.
- Don't fork lovia's chat UI; customize through `ChatUI(templates=...)` blocks
  (`head`, `sidebar_footer`, `body_end`) only.
