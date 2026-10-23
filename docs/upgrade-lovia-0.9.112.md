# 升级到 lovia 0.9.112

本项目的依赖从 lovia 0.9.96 升到了 0.9.112：`pyproject.toml` 写 `lovia[web]>=0.9.112`，`uv.lock` 锁在 0.9.112。
lovia 在 1.0 之前不保留兼容层，不过这段区间里没有会让本项目出错的改动，代码一行都不用改。
提高下限只是为了让文档和注释里的新名字对得上。

如果你基于本项目做过修改，按本文逐条检查；没改过的话，拉取更新后执行：

```bash
uv lock --upgrade-package lovia
uv sync --extra dev
```

## 随升级一起做的调整

lovia 0.9.112 把随运行传入的依赖对象统一叫作 `deps`，构造它的钩子 `create_app(run_context=)` 也改名为
`create_app(run_deps=)`。本项目不用这个钩子传身份（原因见下文），只在 `AGENTS.md`、`docs/design.md`
和 `examples/per_user_tools.py` 的说明里提到过它，这几处已经改成新名字。

## 自定义时要注意

### 依赖对象改名（lovia 0.9.112）

如果你在 `agent_factory` 或 `app_options` 里用到下面这些写法，需要跟着改。旧写法会立即抛出
`TypeError` 或 `AttributeError`，不会被悄悄忽略。

| 旧写法 | 新写法 |
| --- | --- |
| `Runner.run(..., context=x)` | `Runner.run(..., deps=x)` |
| `ctx.context`、`RunContext(context=...)` | `ctx.deps`、`RunContext(deps=...)` |
| `app_options={"run_context": fn}` | `app_options={"run_deps": fn}` |
| `lovia.web.RunContextFn` | `lovia.web.RunDepsFn` |

页面的客户端上下文仍叫原来的名字：`window.lovia.provideContext`、请求里的 `context` 和 `trigger.client`。
身份仍然要在 `agent_factory` 里绑定，不要用 `run_deps` 传：定时任务和子任务的运行没有对应的请求
（`trigger.request` 为 `None`），分辨不出是谁在运行。`run_deps` 适合传页面状态这类不涉及身份的信息。

### 页面不再自带 CSP（lovia 0.9.105）

lovia 的聊天页面不再设置 Content-Security-Policy，`templates/chat/index.html` 也没有设，所以目前
页面上没有任何 CSP。如果你在代理或中间件里加一条：

- `script-src` 必须允许内联脚本，页面依赖它们；
- 这条策略会被 lovia 渲染不受信内容时用的沙箱 `srcdoc` iframe 继承。

### 模板里用到的内部实现

`templates/chat/index.html` 仍然用着 lovia 的几处内部实现：`#composer`、`.sidebar-nav-item`、
`--warn-soft`、`--warn-border`、`--shadow-sm`。它们在 0.9.112 里都还在（已对照源码核对），页面显示正常。
不过它们不属于 lovia 的公开接口，迁移方法见
[升级到 lovia 0.9.96](upgrade-lovia-0.9.96.md) 里的对照表。

## 无需改动，但值得知道

- **聊天库加了版本号（lovia 0.9.111）。** 每个用户的 `chat.db` 第一次被新版打开时，会多出一张
  `lovia_schema` 表，记录表结构版本（`chat=1`）。管理员只读查看时打开的是同一个文件，也会参与这一步。
  迁移在写锁事务里完成，不会和用户自己的应用冲突。旧版 lovia 会忽略这张表，所以回退版本不受影响。
- **审计过滤不用改。** 从 0.9.96 到 0.9.112，lovia 的 API 路由没有任何变化，`UI_REFRESH` 保持原样。
- **退出登录时的清理不用改。** lovia 没有新增 localStorage key，`login.html` 清理的
  `lovia-draft:*`、`lovia-followups`、`lovia-runs-seen` 仍然完整。
- **一次回复的中间步骤折叠成一行"活动"（lovia 0.9.102）。** 思考和工具调用会收进一行，可以展开查看。
- **视图（lovia 0.9.106）** 可以让部署者自己的页面替换聊天区域，`lovia web init-ui`（0.9.104）可以生成
  一个界面目录模板，本项目都用不到。阻塞式的 `POST /api/chat` 现在和流式请求走同一个 supervisor（0.9.97）。

## 验证

- `uv run --extra dev pytest`：41 个测试全部通过。
- `uv run --extra dev ruff check .`、`ruff format --check .` 都通过。
- 手动检查（`examples/demo.py`）：
  - 普通用户聊天正常；
  - 管理员查看他人空间时，输入框隐藏、有只读横幅、侧栏有用户菜单，写请求返回 403；
  - 浏览器控制台没有报错；
  - 用户的 `chat.db` 记录为 `chat=1`。

## 回退

把 `pyproject.toml` 的下限改回 `>=0.9.96`，然后执行 `uv lock --upgrade-package lovia==0.9.96`。
新版加到 `chat.db` 里的 `lovia_schema` 表不影响旧版。
