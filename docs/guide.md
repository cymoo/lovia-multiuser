# 使用指南

安装、配置模型、创建账号、启动、日常使用和部署见 [README](../README.md)。本文是进阶参考。

## 编写 agent_factory

`agent_factory(user, home)` 为每个用户构建 agent，在该用户第一次访问（或服务启动）时调用一次：

```python
def agents(user: User, home: Path) -> Agent:
    return Agent(
        name="assistant",
        model=MODEL,
        workspace=Workspace.local(str(home / "files"), mode="readonly"),
        plugins=[Memory(home / "memory")],
        tools=order_tools(user),  # 绑定到该用户的工具
    )
```

- 工作区和 Memory 放在 `home` 下。
- 工作区只用 `readonly` 或不用；`coding` / `trusted` 会让用户读到其他人的数据（见设计方案"安全边界"）。
- 需要以用户身份访问业务数据的工具，在这里用闭包绑定 `user`，参考 `examples/per_user_tools.py`。模型永远不提供用户 id。
- 也可以返回 `{"name": agent, ...}`，给用户多个 agent，聊天界面会出现 agent 选择框。
- 不要在多个用户之间共享同一个带状态的对象（工具、插件、连接），也不要修改共享 agent 上的"当前用户"。

## 替换认证

**换登录方式**：实现 `authenticate(request) -> user_id | None`。例如由认证代理转发用户 id：

```python
class ProxyHeaderAuth:
    async def authenticate(self, request):
        return request.headers.get("X-Forwarded-User") or None


app = create_multiuser_app(
    agents,
    data_dir="data",
    directory=Accounts("data/accounts.db"),
    auth=ProxyHeaderAuth(),
    login_url="/oauth2/start?rd={next}",
)
```

代理必须剥掉客户端自带的同名请求头，否则任何人都能冒充任何用户。换成 JWT、OIDC 的方式相同。自定义 `auth` 时不再提供 `/login` 页面，`login_url` 指向你的登录入口，`{next}` 会被替换成登录后要回到的页面。

**换用户系统**：实现 `Directory` 的三个异步方法，传给 `directory=`：

| 方法 | 作用 |
| --- | --- |
| `get(user_id) -> User \| None` | 每个请求都会调用，要快；需要缓存时，保证停用能及时生效 |
| `list() -> list[User]` | 管理后台和每 30 秒一次的同步用 |
| `set_disabled(user_id, disabled)` | 管理后台的停用 / 启用按钮用 |

`User` 的 `id` 必须是 slug（小写字母、数字、`_`、`-`，最长 32 位），它会出现在 URL 和目录名里。外部身份（邮箱、工号）请在 `Directory` 里映射成稳定的 slug。自定义 `directory` 时必须同时提供 `auth`。

## create_multiuser_app 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `agent_factory` | 必填 | `(user, home) -> Agent` |
| `data_dir` | 必填 | 数据目录 |
| `directory` | `Accounts(data_dir/accounts.db)` | 用户目录 |
| `auth` | `CookieAuth` | 认证 |
| `login_url` | `/login?next={next}` | 未登录时跳转的地址 |
| `title` | `lovia` | 页面标题 |
| `chat_ui` | `ChatUI()` | 聊天页空白态的标题、说明和示例问题；其中 `assets` 和 `login_url` 由本项目设置 |
| `app_options` | `{}` | 传给每个用户 `create_app()` 的参数 |
| `reconcile_interval` | `30` | 与用户目录同步的间隔（秒） |

`app_options` 常用项（完整列表见 lovia 的 `create_app` 文档）：

| 键 | 说明 |
| --- | --- |
| `max_background_runs` | 每个用户同时运行的对话数上限，默认 8 |
| `budget` | 每次运行的 token、时长、工具调用上限（`RunBudget`） |
| `max_turns` | 每次运行的最大轮数，默认 50 |
| `titles` | 是否用模型生成对话标题，默认开 |
| `followups` | 回复后给出推荐追问，默认关；每次运行多一次模型调用 |
| `approval_timeout` | 工具审批的等待超时（秒） |

`app_options` 不能包含 `db_path`、`store`、`session`、`ui`、`title`、`token`、`auth`，这些由本项目统一设置；也不能包含 `lifespan`，本项目只运行 lovia 自己的 lifespan，传入的不会执行。

## 数据导出与删除

**导出某个用户的数据**：复制 `data/users/<id>/`。`chat.db` 是 SQLite，可以用 lovia 的 `ChatStore.sqlite(path)` 读取。

**删除某个用户**：先停用（让服务关闭其应用），再删除 `data/users/<id>/`。参考实现的 `Accounts` 没有删除命令，账号保持停用即可；审计记录按需保留。

## 不配置模型的演示

`examples/demo.py` 在 `./demo-data` 里创建 `alice`、`bob`、`admin` 三个演示账号，每条消息都返回固定回复，适合在没有模型的环境里检查界面：

```bash
uv run examples/demo.py
```

密码写在脚本里，只用于本地演示。

## 开发

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

测试用 lovia 的 `ScriptedProvider`，不访问网络。约定和容易踩的坑见 [AGENTS.md](../AGENTS.md)。
