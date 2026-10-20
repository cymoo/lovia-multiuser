# 设计方案：lovia 多用户服务

## 1. 背景与目标

lovia 的 `create_app()` 服务的是一个人的数据：`token=` / `auth=` 只决定请求能不能进来，身份不会带过守卫，进来的人共享全部对话、定时任务、事件流、Memory 和工作区（lovia issue #221）。

本项目要做到：

- **自定义认证**：参考实现是账号密码登录；替换成 SSO、代理头、JWT 时不动其余部分。
- **用户只能看到自己的记录**：对话、运行记录、定时任务、附件、Memory、工作区文件、实时事件。
- **管理员能看到所有人的记录**：看得方便，界面友好，且默认只读、全程审计。
- **账号可停用**：立即登出，后台工作停止，记录保留供管理员查看。

不在目标内：给不可信用户 shell；用户之间共享对话；跨用户的全局配额。

## 2. 方案选择

| | A · 每租户一个进程/容器 | **B · 每用户一个 app（本方案）** | C · 一个 app 按行记录 owner | D · 自建业务 API，lovia 只做执行 |
| --- | --- | --- | --- | --- |
| 隔离方式 | 操作系统 | 结构（不共享 store） | 每个入口手写检查 | 每个入口手写检查 |
| 越权面 | 无 | 无 | 约 25 条按 id 访问的路由 | 自建的每个入口 |
| 给用户 shell | 可以（容器） | 不行 | 不行 | 不行 |
| 管理员看全部 | 难 | 进入任意用户空间 + 遍历汇总 | 天然 | 天然 |
| 工作量 | 运维为主 | 约 1100 行 Python，分发与租户管理约 370 行，其余是参考认证、后台和 CLI | 改 lovia 核心 | 重写 lovia.web 的大部分功能 |
| 每用户成本 | 约 74 MB 进程 | 约 0.2–0.6 MB | ≈0 | ≈0 |

选 B 的理由：隔离由结构保证，lovia.web 已有的流式输出、断线重连、审批、定时任务、子任务、文件与记忆面板全部原样可用，lovia 升级后新功能自动获得。管理员视图借助 lovia 的子路径服务能力：进入 `/u/<owner>/` 就是该用户完整的原版界面。

何时换方案：给不可信用户 shell → A（每用户一个容器，URL 结构不变）；需要合并视图、对话共享、全局配额 → C 或 D。B 的数据按用户分文件，迁到 A 是搬目录，迁到 C/D 是遍历各用户的 `chat.db` 写入 owner。

## 3. 架构

```
浏览器（登录 cookie）──▶ 外层 FastAPI：create_multiuser_app()
  /login /logout      CookieAuth（参考实现，可替换）
  /                   已登录 → /u/<我>/；管理员 → /admin
  /admin/...          管理后台：用户、对话、跨用户搜索、审计、停用
  /u/{owner}/...      dispatch：认证 → 授权 → 审计 → owner 的 create_app()
                         alice → create_app(db=users/alice/chat.db, agent=factory(alice))
                         bob   → create_app(db=users/bob/chat.db,   agent=factory(bob))
```

模块：

| 模块 | 职责 |
| --- | --- |
| `app.py` | `create_multiuser_app()`、dispatch、reconcile、首页 |
| `tenants.py` | 每用户一个 app：按需构建、live / dormant、关闭 |
| `auth.py` | `Authenticator` 接口 + 参考实现 `CookieAuth` |
| `accounts.py` | `Directory` 接口 + 参考实现 `Accounts`（SQLite + scrypt） |
| `audit.py` | 审计日志（SQLite） |
| `admin.py` | 管理后台路由 |
| `templates/chat/index.html` | 覆盖 lovia 聊天页：用户菜单、只读横幅 |

数据布局：

```
data/
  accounts.db        用户目录（参考实现）
  audit.db           审计日志
  secret             cookie 签名密钥（0600，首次启动生成）
  users/<id>/
    chat.db          对话、运行记录、定时任务、检查点
    files/           工作区（由 agent_factory 决定）
    memory/          Memory（由 agent_factory 决定）
```

## 4. 请求处理

`/u/{owner}/...` 的每个请求都经过 `app.py` 里的 dispatch，**授权只有这一处**：

1. `auth.authenticate(request)` 得到用户 id；`directory.get(id)` 得到角色和状态。每个请求都查目录，所以停用、改角色立即生效。
2. 未登录：API 返回 401（`code: signed_out`），lovia UI 据此跳到 `login_url`；页面请求直接 303 到登录页，带上 `next`。
3. 访问他人空间：非管理员一律 404，且和"用户不存在"的响应完全一样，不泄露用户是否存在；管理员只允许 `GET` / `HEAD`，写操作 403（`code: read_only`）。
4. 把 `viewer` 和 `owner` 放到 `request.state`，供聊天页模板使用。
5. 转发给 owner 的 app。

| 情况 | 结果 | 审计 |
| --- | --- | --- |
| 本人访问自己的空间 | 放行 | 否 |
| 未登录 | 401 / 303 登录 | 否（无操作者） |
| 非管理员访问他人空间 | 404 | 是 |
| 管理员读取他人数据 | 放行 | 是（UI 后台刷新除外） |
| 管理员在他人空间写操作 | 403 | 是 |

一个实现细节：lovia 页面用 `url_for('static')` 生成资源地址，Starlette 按 `scope["router"]` 和 `scope["app_root_path"]` 解析，默认是外层 app 的，找不到 `static`。dispatch 把两者指向该用户的 app 和 `/u/<owner>` 前缀。这依赖 Starlette 的内部字段，由 `test_the_chat_page_and_its_assets_live_under_the_prefix` 守住。

## 5. 身份与扩展点

三个替换点，其余代码不用动：

| 替换点 | 作用 | 参考实现 | 生产中换成 |
| --- | --- | --- | --- |
| `Authenticator.authenticate(request) -> user_id` | 谁在请求 | `CookieAuth`：登录表单 + HMAC 签名 cookie | SSO、代理头、JWT（见 `examples/proxy_auth.py`） |
| `Directory.get / list / set_disabled` | 用户是否存在、是否管理员、是否停用 | `Accounts`：SQLite + scrypt | 业务用户系统、LDAP、IdP API |
| `agent_factory(user, home) -> Agent` | 每个用户的 agent | 由使用方提供 | — |

用户 id 限定为 `[a-z0-9][a-z0-9_-]{0,31}`，因为它同时出现在 URL 和目录名里；显示名任意。接入外部身份系统时，用稳定的内部 id，不要用会变的邮箱或显示名。

**工具以用户身份访问业务数据**：身份在构建 agent 时绑定（工具通过闭包拿到当前用户），模型永远不提供用户 id（见 `examples/per_user_tools.py`）。lovia 0.9.95 起有 `create_app(run_context=)`，但定时任务和子任务的运行没有对应的请求（`trigger.request` 为 `None`），靠它分辨不出是谁的运行，所以不用它传身份。绝不修改共享 agent 上的"当前用户"。

## 6. 管理员

- **后台**（`/admin`）：用户列表（状态、对话数、最近活动）、最近活跃的对话、跨用户搜索（标题和 id）、用户详情（对话、定时任务、相关审计）、审计日志、停用 / 启用。
- **查看记录**：后台里每个对话都链接到 `/u/<owner>/?session=<id>`，在该用户的原版界面中打开。
- **只读**：他人空间里的写请求一律 403；聊天页隐藏输入框，底部横幅显示"只读查看 X 的记录 · 返回管理后台"。重命名、删除等按钮仍可见，点击会得到 403 提示（lovia 没有只读模式开关，按 DOM 隐藏更多元素会和 lovia 的页面结构耦合）。
- 管理员也是普通用户，有自己的 `/u/<id>/`；不能停用自己。
- 浏览后台不会给没有数据的用户创建目录或数据库。

## 7. 审计

记录两类事件，存在 `data/audit.db`：

- `http`：进入他人空间的请求，含方法、路径、查询串和响应状态。包括管理员查看、被拒的写操作、越权访问（404）。
- `user.disable` / `user.enable`：账号操作。

不记录：本人在自己空间的请求、静态资源（`/static/` 和 `ChatUI.assets` 所在的 `/ui/`）、lovia UI 每次打开页面都会重复的后台刷新（`/api/info`、`/api/agents`、`/api/events`、`/api/sessions` 列表、`/api/runs`、`/api/runs/history`）成功的请求。不过滤的话，管理员打开一次页面约有 14 条记录，真正打开了哪个对话会被淹没。被拒绝的请求始终记录。

查询：后台"审计"页（按操作者、对象用户筛选），或 `lovia-multiuser audit`。

限制：本地 SQLite，不防篡改，没有保留策略。有合规要求时转发到日志平台或 SIEM。

## 8. 账号停用

停用后：

1. **立即登出**：每个请求都查目录，已停用的用户视为未登录。
2. **后台工作停止**：关闭该用户的 app（`Tenants.evict`），运行中的任务协作式停止并保留可恢复的检查点，定时任务不再触发，打开的事件流断开。
3. **记录保留**：管理员仍可只读查看。此时该用户的 app 以 **dormant** 方式构建，不进入 lifespan，所以没有调度器，也不会因为管理员查看而恢复后台工作。

`Tenants` 维护两种状态：

| 状态 | lifespan | 用途 |
| --- | --- | --- |
| live | 已进入：调度器、运行管理、事件总线 | 正常用户 |
| dormant | 未进入：只能读 | 管理员查看已停用用户 |

`get(user)` 发现缓存的 app 状态与账号状态不一致时，关闭后重建。

**reconcile**：启动时和之后每 30 秒，让 live 的 app 与目录一致：关闭已停用或已删除用户的 app，启动有数据的正常用户的 app（定时任务只在 app live 时触发）。这样通过 CLI 或其他进程修改目录，也会在 30 秒内生效。后台操作停用时立即关闭，不等同步。

注意：重新启用后，停用期间错过的定时任务会补触发一次（lovia 调度器把过期的触发合并为一次）。

## 9. 安全边界

- **工作区是策略闸门，不是沙箱**（lovia `workspace/policy.py`）。同一进程内，只有下面两种情况隔离才成立：

  | 工作区模式 | 根目录外读取 | shell | 本方案 |
  | --- | --- | --- | --- |
  | 无工作区 | — | — | 可以 |
  | `readonly` | 拒绝 | 禁用 | 可以 |
  | `coding` | 需审批（审批人是用户自己） | 需审批 | 不可以 |
  | `trusted` | 允许 | 允许 | 不可以 |

  能执行任意代码的自定义工具同样会打破隔离。需要这些能力时，用方案 A。
- **CSRF**：会话 cookie 是 `SameSite=Lax`，跨站的非 GET 请求不带 cookie；lovia 和本项目的写操作都不用 GET。
- **开放重定向**：`next` 只接受本站路径。
- **登录**：scrypt 哈希；用户不存在时也跑一次哈希，响应时间一致；密码错和用户不存在返回同一条提示。
- **cookie**：`HttpOnly`；部署在 TLS 后面时传 `CookieAuth(..., secure=True)`；签名密钥文件权限 0600。
- **同源 localStorage**：所有用户共用一个源，lovia UI 的草稿存在 localStorage。退出登录时清除草稿，保留主题、语言等偏好。

## 10. 已知限制与后续

| 限制 | 影响 | 后续方向 |
| --- | --- | --- |
| 没有全局并发上限 | 总并发 = 用户数 × `max_background_runs` | 在模型网关限流；或推动 lovia 提供可共享的限流器 |
| 只能单 worker | 运行状态在进程内存里 | 按用户分片：反向代理把 `/u/<id>` 哈希到不同进程；管理后台需改为直接读各用户的 `chat.db` |
| 搜索只匹配标题和 id | 不能按消息正文搜 | 定期把各用户数据汇总到只读报表库 |
| 管理员看不到进行中的流式输出 | 重连接口是 POST，且可能恢复运行 | 运行结束后可看完整记录 |
| 管理员界面仍显示删除、重命名等按钮 | 点击得到 403 提示 | 推动 lovia 的 `ChatUI` 提供只读模式 |
| 无登录限流、找回密码、改密后吊销会话 | 参考实现的认证较简陋 | 替换为正式的身份系统 |
| 用户删除与数据导出没有命令 | 需手工操作（见使用指南） | 按需加 CLI |
| 不支持整体挂在路径前缀下 | 页面里的 `/admin`、`/login`、`/u/` 是绝对路径 | 用子域名部署；或增加 `base_path` 参数 |
| 每个用户一个调度轮询；reconcile 每 30 秒列一次全部用户 | 用户上万时开销明显 | 调大 `scheduler_poll` 和 `reconcile_interval`；或改用方案 C |
| 只有一个管理员角色 | 不能区分审计员和运维 | `User` 增加角色字段 |
