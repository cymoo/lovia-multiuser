# 使用指南

## 快速体验

不需要模型 API key：

```bash
python examples/demo.py
```

打开 <http://127.0.0.1:8000>，用 `alice` / `bob` / `admin` 登录，密码都是 `demo-password`。每条消息都会收到固定回复，可以点一遍登录、隔离、管理员只读查看、审计和停用。

## 接入真实模型

```bash
lovia-multiuser users add admin --name 管理员 --admin   # 交互式输入密码
lovia-multiuser users add alice --name Alice
LOVIA_MODEL=... python examples/serve.py
```

模型配置见 lovia 的 `model_from_env`。`examples/serve.py` 给每个用户一个 `readonly` 工作区和独立的 Memory。

## 编写 agent_factory

`agent_factory(user, home)` 为每个用户构建 agent，在该用户第一次访问（或服务启动）时调用一次：

```python
def agents(user: User, home: Path) -> Agent:
    return Agent(
        name="assistant",
        model=MODEL,
        workspace=Workspace.local(str(home / "files"), mode="readonly"),
        plugins=[Memory(home / "memory")],
        tools=order_tools(user),   # 绑定到该用户的工具
    )
```

- 工作区和 Memory 放在 `home` 下。
- 工作区只用 `readonly` 或不用；`coding` / `trusted` 会让用户读到其他人的数据（见设计方案"安全边界"）。
- 需要以用户身份访问业务数据的工具，在这里用闭包绑定 `user`，参考 `examples/per_user_tools.py`。
- 也可以返回 `{"name": agent, ...}`，给用户多个 agent。

## 替换认证

**换登录方式**：实现 `authenticate(request) -> user_id | None`。例如由认证代理转发用户 id：

```python
class ProxyHeaderAuth:
    async def authenticate(self, request):
        return request.headers.get("X-Forwarded-User") or None

app = create_multiuser_app(
    agents, data_dir="data",
    directory=Accounts("data/accounts.db"),
    auth=ProxyHeaderAuth(),
    login_url="/oauth2/start?rd={next}",
)
```

代理必须剥掉客户端自带的同名请求头，否则任何人都能冒充任何用户。换成 JWT、OIDC 的方式相同。

**换用户系统**：实现 `Directory` 的三个异步方法 `get`、`list`、`set_disabled`，传给 `directory=`。`get` 每个请求都会调用，要快（需要时自己加短缓存，但要让停用及时生效）。自定义 `directory` 时必须同时提供 `auth`。

## create_multiuser_app 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `agent_factory` | 必填 | `(user, home) -> Agent` |
| `data_dir` | 必填 | 数据目录 |
| `directory` | `Accounts(data_dir/accounts.db)` | 用户目录 |
| `auth` | `CookieAuth` | 认证 |
| `login_url` | `/login?next={next}` | 未登录时跳转的地址 |
| `title` | `lovia` | 页面标题 |
| `chat_ui` | `ChatUI()` | 聊天页空白态文案和示例 |
| `app_options` | `{}` | 传给每个用户 `create_app()` 的参数，如 `max_background_runs`、`budget`、`followups` |
| `reconcile_interval` | `30` | 与目录同步的间隔（秒） |

`app_options` 不能包含 `db_path`、`store`、`session`、`ui`、`title`、`token`、`auth`，这些由本项目统一设置。

## 部署清单

- **TLS**：放在 HTTPS 反向代理后面，并传 `CookieAuth(..., secure=True)`（`examples/serve.py` 用环境变量 `LOVIA_MU_SECURE=1`）。
- **单 worker**：运行状态在进程内存里，不要开多个 uvicorn worker。
- **反向代理**：`/u/*/api/chat/stream`、`/u/*/api/events` 是 SSE，关闭缓冲（nginx `proxy_buffering off`）并调大读超时。
- **部署在域名根路径或子域名下**：暂不支持整体挂在路径前缀下。
- **数据目录**：只允许服务进程的用户读写；`secret` 丢失会让所有人重新登录。
- **备份**：备份整个 `data/`。每个用户的数据在 `users/<id>/` 下，可以单独备份和恢复。

## 运维

```bash
lovia-multiuser users list
lovia-multiuser users disable alice      # 30 秒内停止其后台工作；后台操作则立即生效
lovia-multiuser users enable alice
lovia-multiuser users passwd alice
lovia-multiuser audit --owner alice --limit 100
```

所有命令都接受 `--data DIR`（默认 `./data`）。

**导出某个用户的数据**：复制 `data/users/<id>/`。`chat.db` 是 SQLite，可以用 lovia 的 `ChatStore.sqlite(path)` 读取。

**删除某个用户**：先停用（让服务关闭其 app），再删除 `data/users/<id>/`。参考实现的 `Accounts` 没有删除命令，账号保持停用即可；审计记录按需保留。

## 开发

```bash
uv venv && uv pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

测试用 lovia 的 `ScriptedProvider`，不访问网络。
