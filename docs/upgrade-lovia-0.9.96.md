# 升级到 lovia 0.9.96

本项目的依赖从 lovia 0.9.75 升到了 0.9.96（`pyproject.toml` 写 `lovia[web]>=0.9.96`，`uv.lock` 锁在 0.9.96）。lovia 在 1.0 之前不保留兼容层，这段区间里有一处会让本项目直接无法启动的改动，另有几处行为变化。下面按“必须改”“自定义时要注意”“无需改动”分开说明。

如果你基于本项目做过修改，按本文逐条检查；没改过的话，拉取更新后执行 `uv sync` 即可。

## 必须改的

### `ChatUI(templates=)` 改为 `ChatUI(assets=)`（lovia 0.9.92）

lovia 删除了 `ChatUI` 的 `templates` 参数，换成 `assets`：一个“界面目录”，覆盖页面用的 `index.html` 放在这里，扩展脚本、样式、logo、favicon 也都相对它解析。旧写法会在 `create_multiuser_app()` 里抛出 `TypeError: ChatUI.__init__() got an unexpected keyword argument 'templates'`，服务启动不了。

```python
# lovia_multiuser/app.py
ui = replace(chat_ui or ChatUI(), assets=TEMPLATES / "chat", login_url=login_url)
```

`templates/chat/index.html` 本身不用改：它仍然 `{% extends "lovia/index.html" %}`，用到的 `head`、`sidebar_footer`、`body_end` 三个 block 都还在。

`assets` 目录里除了 `*.html` 和以点开头的文件，其余文件都会公开在 `/u/<owner>/ui/` 下。`templates/chat/` 目前只有 `index.html`，没有文件会被公开。

### 依赖版本

```toml
dependencies = ["lovia[web]>=0.9.96", ...]
```

然后执行：

```bash
uv lock --upgrade-package lovia
uv sync --extra dev
```

只改代码不改下限，`pip install` 仍可能装到旧版 lovia，而旧版不认识 `assets=`。

## 随升级一起做的调整

这两处不改也能运行，但新版 lovia 会让原来的规则悄悄失效，所以一并改了：

- **`/ui/` 下的资源不记审计**：`ChatUI.assets` 里的文件通过 `/u/<owner>/ui/…` 加载。原来 dispatcher 只豁免 `/static/`，以后要是往 `templates/chat/` 里放样式或脚本，管理员每打开一次页面都会多出几条审计记录。现在 `/static/` 和 `/ui/` 都豁免（`tests/test_audit.py` 覆盖）。
- **`app_options` 不能再包含 `lifespan`**：lovia 0.9.79 新增了 `create_app(lifespan=)`，但 `Tenants` 只进入 lovia 自己的 lifespan，从 `app_options` 传进来的不会执行。现在它和 `db_path`、`ui` 等一样，传入会直接报错。

## 自定义时要注意

### `chat_ui` 的 `assets` 归本项目所有

`create_multiuser_app(chat_ui=...)` 里的 `assets` 和 `login_url` 会被本项目覆盖。这意味着：

- `ChatUI(scripts=["ext.js"])` 这种相对文件名会解析到本项目的 `templates/chat/` 下。要加自己的脚本或样式，可以把文件放进 `templates/chat/`，也可以写成应用路径（`"/brand/x.css"`）或完整 URL。
- 空白态文案（`empty_title`、`empty_description`、`empty_examples`）、`default_lang`、`messages` 照常生效。界面文字是中文，可以考虑设置 `ChatUI(default_lang="zh")`。

### 页面结构：只依赖 lovia 公开的部分

lovia 0.9.91 起明确了页面的公开接口：模板 block、`data-part` 属性、设计变量、`data-i18n` key、`window.lovia`。CSS 类名、元素 id 都属于内部实现，可能随版本变化。

`templates/chat/index.html` 目前还用着几个内部实现，在 0.9.96 里都还有效：

| 现在的写法 | 公开的替代 |
| --- | --- |
| `#composer { display: none !important; }` | `[data-part="composer"] { display: none; }` |
| 按钮借用 `.sidebar-nav-item` 样式 | 换成自己的类名 |
| `--warn-soft`、`--warn-border`、`--shadow-sm` | 公开变量里只有 `--warn`、`--border`、`--muted`、`--accent-soft`、`--accent-text` 等，见 lovia 文档 web-server.md 的“样式”一节 |

另外，lovia 的样式表现在放在 `@layer lovia` 里，不在任何 layer 里的样式（比如模板里的 `<style>`）总会压过内置样式，不再需要 `!important`。

模板还新增了几个可用的 block：`sidebar_header`、`sidebar_nav`、`topbar_actions`、`composer_actions`、`welcome`。

## 无需改动，但值得知道

- **`create_app(run_context=)`（0.9.95）**：lovia 现在可以把一个按运行构造的 context 交给工具。本项目仍然在 `agent_factory` 里绑定用户身份，不用这个钩子传身份，原因是定时任务和子任务的运行没有对应请求（`trigger.request` 为 `None`），分辨不出是谁在运行。这个钩子可以放进 `app_options`，用来传页面状态之类的非身份信息。
- **数据库自动加列**：每个用户的 `chat.db` 第一次被新版打开时，会给 `chat_sessions`、`chat_schedules` 各加一个可空列（`active_context_json`、`context_json`）。旧版 lovia 查询时都写明了列名，回退版本不受影响。
- **消息操作（0.9.96）**：消息旁新增的操作（如回退到某条消息）都是写请求，管理员只读查看时点击会得到 403 提示，和重命名、删除按钮的现状一样。
- **审计过滤不用改**：从 0.9.75 到 0.9.96，lovia 页面加载时调用的 `/api` 端点没有变化，`UI_REFRESH` 保持原样。
- **退出登录时清理的草稿**：lovia 没有新增按用户区分的 localStorage key，`login.html` 里清理的 `lovia-draft:*`、`lovia-followups`、`lovia-runs-seen` 仍然完整。
- **`Plugin.setup(self, ctx)`（0.9.90）**：插件的 `setup` 多了一个 `RunContext` 参数。本项目没有自定义插件；如果你的 `agent_factory` 里用了自己写的插件，记得同步修改签名。

## 验证

- `uv run --extra dev pytest`：41 个测试全部通过
- `uv run --extra dev ruff check .`、`ruff format --check .`：通过
- 手动检查（`examples/demo.py`）：普通用户聊天正常；管理员查看他人空间时，输入框隐藏、底部有只读横幅、侧栏有用户菜单，浏览器控制台没有报错

## 回退

把 `pyproject.toml` 的下限改回 `>=0.9.75`，执行 `uv lock --upgrade-package lovia==0.9.75`，并把 `app.py` 里的 `assets=` 改回 `templates=`。新版加到 `chat.db` 里的列不影响旧版。
