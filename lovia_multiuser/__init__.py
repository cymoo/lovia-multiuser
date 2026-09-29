"""Multi-user serving for lovia agents.

Each user gets their own lovia ``create_app()`` at ``/u/<id>/`` — own chat
database, workspace, Memory, scheduler — so users are isolated by
construction. Admins can open any user's space read-only; every such request
is audited.

    from lovia_multiuser import create_multiuser_app

    def agents(user, home):
        return Agent(name="assistant", model=..., ...)

    app = create_multiuser_app(agents, data_dir="data")
"""

from .accounts import Accounts, Directory, User
from .app import AgentFactory, MultiUser, create_multiuser_app
from .audit import AuditEntry, AuditLog
from .auth import Authenticator, CookieAuth
from .tenants import Tenants

__version__ = "0.1.0"

__all__ = [
    "Accounts",
    "AgentFactory",
    "AuditEntry",
    "AuditLog",
    "Authenticator",
    "CookieAuth",
    "Directory",
    "MultiUser",
    "Tenants",
    "User",
    "create_multiuser_app",
]
