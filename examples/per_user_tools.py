"""Tools that act as the signed-in user.

Each user's agent is built with tools already bound to that user — this holds
for scheduled and subagent runs too, which lovia's ``run_context=`` hook gets
no request for. The model never supplies the user id, so it cannot ask for
someone else's data.

    uv run examples/per_user_tools.py      # model settings from .env
"""

from __future__ import annotations

from pathlib import Path

from lovia import Agent, model_from_env, tool
from lovia.web import serve

from lovia_multiuser import User, create_multiuser_app
from lovia_multiuser.env import data_dir, load_env

# Stand-in for your business database.
ORDERS = {
    "alice": [{"id": "A-1001", "item": "键盘", "status": "已发货"}],
    "bob": [{"id": "B-2001", "item": "显示器", "status": "待付款"}],
}

load_env()
MODEL = model_from_env()


def order_tools(user: User) -> list:
    @tool
    async def my_orders() -> list[dict]:
        """List the current user's orders."""
        return ORDERS.get(user.id, [])

    @tool
    async def order_status(order_id: str) -> str:
        """Look up one of the current user's orders by id."""
        for order in ORDERS.get(user.id, []):
            if order["id"] == order_id:
                return order["status"]
        # Someone else's order looks exactly like a missing one.
        return "没有这个订单"

    return [my_orders, order_status]


def agents(user: User, home: Path) -> Agent:
    return Agent(
        name="support",
        instructions=f"You help {user.name} with their orders.",
        model=MODEL,
        tools=order_tools(user),
    )


if __name__ == "__main__":
    serve(create_multiuser_app(agents, data_dir=data_dir()), port=8000)
