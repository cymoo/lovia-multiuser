# 升级到 lovia 0.9.114

本项目的依赖从 lovia 0.9.112 升到了 0.9.114：`pyproject.toml` 写 `lovia[web]>=0.9.114`，`uv.lock` 锁在 0.9.114。
lovia 在 1.0 之前不保留兼容层，这段区间里有一处改动会让本项目直接起不来：`create_app` 的
`generate_titles` 参数改名成了 `titles`，而本项目在 demo 和测试里都通过 `app_options` 传了它。

如果你基于本项目做过修改，按本文逐条检查；没改过的话，拉取更新后执行：

```bash
uv lock --upgrade-package lovia
uv sync --extra dev
```

## 必须改的

### `generate_titles` 改为 `titles`（lovia 0.9.114）

新名字和 `/api/info` 里这个功能的叫法一致，也和 `title_model`、`followups` 对得上。

```python
# examples/demo.py、tests/conftest.py
app_options={"titles": False}
```

`app_options` 会原样交给每个用户的 `create_app`，所以旧名字会让每个用户的应用都在构造时抛出
`TypeError`。你自己的部署代码里如果传了 `generate_titles`，也要一并改掉。README 和
`docs/guide.md` 里的参数说明已经同步。

### 依赖下限

```toml
"lovia[web]>=0.9.114",
```

## 自定义时要注意

- **`RunTrigger.client` 改为 `client_context`（0.9.114）。** 只有在 `app_options` 里传了
  `run_deps` 钩子时才相关。本项目不用这个钩子传身份（原因见 `docs/design.md`）。
- **`window.lovia.api` 已删除（0.9.114）。** 如果你在 `templates/chat/` 里加了扩展脚本：
  - 请求接口改用 `lovia.fetch(path)`；
  - 需要拼 URL（`<img src>`、链接）时，用新增的 `lovia.url(path)`。它会自动加上租户的路径前缀，
    比如在 alice 的空间里，`lovia.url('/x')` 返回 `/u/alice/x`。
  
  本项目自带的模板没有用到 `lovia.api`。
- **注销方式统一（0.9.114）。** 所有 `register*` 和 `provideContext` 都返回一个撤销函数；
  传 `null` 注销的写法已经去掉。本项目的模板没有注册这些东西。

## 无需改动，但值得知道

- **每次运行都有 `run_id`（0.9.113）。** 没开 checkpoint 的运行，`RunContext.run_id` 也不再是 `None`。
  本项目没有读取它。
- **审计过滤不用改。** 从 0.9.112 到 0.9.114，lovia 的 API 路由没有变化，`UI_REFRESH` 保持原样。
- **退出登录时的清理不用改。** lovia 没有新增 localStorage key。
- **模板里的内部实现都还在。** `#composer`、`.sidebar-nav-item`、`--warn-soft`、`--warn-border`、
  `--shadow-sm` 在 0.9.114 里都还存在。迁移到公开接口的方法见
  [升级到 lovia 0.9.96](upgrade-lovia-0.9.96.md)。

## 验证

- `uv run --extra dev pytest`：41 个测试全部通过。如果只升级 lovia、不改 `tests/conftest.py`，会有 18 个失败。
- `ruff check .`、`ruff format --check .`：通过。
- 手动检查（`examples/demo.py`）：
  - 普通用户聊天正常；
  - 页面上 `lovia.url('/x')` 返回 `/u/alice/x`，`lovia.api` 已不存在；
  - 管理员查看他人空间时，输入框隐藏、有只读横幅、侧栏有用户菜单，写请求返回 403；
  - 除了验证写请求时那一条预期内的 403，浏览器控制台没有其他报错。

## 回退

把 `pyproject.toml` 的下限改回 `>=0.9.112`，执行 `uv lock --upgrade-package lovia==0.9.112`，
再把 `app_options` 里的 `titles` 改回 `generate_titles`。
