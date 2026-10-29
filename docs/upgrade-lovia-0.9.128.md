# 升级到 lovia 0.9.128

本项目的依赖从 lovia 0.9.114 升到了 0.9.128：`pyproject.toml` 写 `lovia[web]>=0.9.128`，`uv.lock` 锁在 0.9.128。
这段区间里只有一处改动影响本项目：lovia 0.9.127 给聊天页的 class 名、设计变量和动画名都加上了前缀，
`templates/chat/index.html` 里用到的旧名字全部失效。项目不会报错、测试也照样通过，但侧栏底部的账号区
和管理员的“只读查看”提示条会失去样式。

如果你基于本项目做过修改，按本文逐条检查；没改过的话，拉取更新后执行：

```bash
uv lock --upgrade-package lovia
uv sync --extra dev
```

## 必须改的

### 聊天页模板只用公开接口（lovia 0.9.127）

lovia 的 class 名改成了 `lv-*`，设计变量改成了 `--lv-*`，旧名字没有保留。[升级到 lovia 0.9.96](upgrade-lovia-0.9.96.md)
里列出的三处内部实现，这次都换成了公开写法：

| 原来的写法 | 现在的写法 |
| --- | --- |
| `var(--border)`、`var(--muted)`、`var(--accent-soft)` 等 | `var(--lv-border)`、`var(--lv-muted)`、`var(--lv-accent-soft)` 等，见 lovia 文档 web-server.md 的“样式”一节 |
| “管理后台”链接借用 `.sidebar-nav-item` 放在 `sidebar_footer` | 放进 `sidebar_nav` block。lovia 会把这里的链接画成和“设置”一样的侧栏项，并配一个图标 |
| “退出登录”按钮借用 `.sidebar-nav-item` | 改用本项目自己的 `.lmu-signout`，颜色取 `--lv-*` 变量 |
| 提示条用 `--warn-soft`、`--warn-border`、`--shadow-sm` | 公开变量里只有 `--lv-warn`，浅色背景和边框用 `color-mix()` 从它调出来；阴影直接写值 |
| `#composer { display: none !important; }` | `[data-part="composer"] { display: none; }` |

lovia 的样式表放在 `@layer lovia` 里，模板里的 `<style>` 不在任何 layer 中，所以总能覆盖内置样式，
不需要 `!important`。

你自己在模板里加的样式，如果用了 lovia 的变量，也要加上 `--lv-` 前缀；如果借用了 lovia 的 class 名，
换成自己的类名，或者用 `data-part` 选择元素。

### 依赖下限

```toml
"lovia[web]>=0.9.128",
```

## 自定义时要注意

- **`lovia.tools` 精简（0.9.117）。** `read_page` 改名为 `web_fetch`，`page_reader()` 并入了
  `web_fetch(...)`；`http_request` 和 `writes_need_approval` 已删除；`make_recall_tool` 改名为
  `recall_tool_result`。只有在 `agent_factory` 里给 agent 加了这些工具时才相关，本项目的示例没有用到。
- **类型信息（0.9.126）。** lovia 现在自带 `py.typed`，mypy 会检查你对 lovia 的调用。比如 `Agent`
  是泛型，严格模式下返回类型要写成 `Agent[None]`。

## 无需改动，但值得知道

- **模板 block 没有变化。** `head`、`sidebar_nav`、`sidebar_footer`、`body_end` 等名字和位置都和 0.9.114 一致。
- **审计过滤不用改。** 页面加载时调用的 `/api` 端点没有变化，`UI_REFRESH` 保持原样。唯一新增的接口
  是 `POST /api/sessions/{id}/fork`（把对话复制成一个新对话），属于写操作：会进审计日志，管理员只读查看时
  会被拒绝（403）。
- **只读查看时的新操作。** 聊天页新增了分支对话、侧栏每行的“⋯”菜单（重命名、置顶、删除），
  以及运行中的“引导/排队”消息。会改数据的操作都是写请求，管理员点击会得到 403 提示，和原来的重命名、
  删除一样；“引导/排队”在输入框里，只读时输入框是隐藏的。
- **退出登录时的清理不用改。** lovia 没有新增 localStorage key，`login.html` 里清理的
  `lovia-draft:*`、`lovia-followups`、`lovia-runs-seen` 仍然完整。
- **`create_app` 的参数没有变化**，`app_options` 和保留参数列表都不用改。

## 验证

- `uv run --extra dev pytest`：41 个测试全部通过。`tests/test_admin.py` 改为检查新的隐藏输入框写法。
- 在浏览器里用 `examples/demo.py` 检查：管理员自己的空间里，“管理后台”和“退出登录”与“设置”样式一致；
  只读查看 alice 时输入框隐藏，提示条在浅色和深色主题下都有正确的配色。
