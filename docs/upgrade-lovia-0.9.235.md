# 升级到 lovia 0.9.235

本项目的依赖从 lovia 0.9.128 升到了 0.9.235：`pyproject.toml` 写 `lovia[web]>=0.9.235`，`uv.lock` 锁在 0.9.235。
这段区间里没有破坏性改动影响本项目：模板 block、`create_app` 已有的参数和测试都照常工作。需要跟着改的有两处，
都是 lovia 新功能带来的：聊天页加载时多了一个后台请求，会刷满审计日志；浏览器里多了几项存用户数据的 key，
退出登录时要一起清掉。

如果你基于本项目做过修改，按本文逐条检查；没改过的话，拉取更新后执行：

```bash
uv lock --upgrade-package lovia
uv sync --extra dev
```

## 必须改的

### 审计过滤加上 `/api/schedules`（lovia 0.9.201）

定时任务成了侧栏里的一个页面，聊天页每次加载都会请求两次 `GET /api/schedules` 来画侧栏。不过滤的话，管理员
每看一次别人的页面，审计里就多两条无意义的记录。`app.py` 的 `UI_REFRESH` 加上了这个路径，
`tests/test_audit.py` 也跟着检查。打开某个定时任务（`/api/schedules/<id>`）不在过滤之列，照常记录。

### 退出登录时多清几项浏览器存储

lovia 新增的文件面板和文件夹分组会在浏览器里记下路径：

| key | 存在哪里 | 内容 |
| --- | --- | --- |
| `lovia-workspace-collapsed` | localStorage | 侧栏里折叠的文件夹分组（路径） |
| `lovia-workspace` | sessionStorage | 这个标签页选中的文件夹 |
| `lovia-files-tree`、`lovia-files-viewing` | sessionStorage | 文件面板展开的目录和打开的文件 |

sessionStorage 跟着标签页走：同一个标签页退出后换人登录，这些值还在。`login.html` 的退出清理现在会删掉
localStorage 里的这一项，以及 sessionStorage 里所有 `lovia-` 开头的 key；主题、语言、侧栏宽度等偏好照旧保留。

### 依赖下限

```toml
"lovia[web]>=0.9.235",
```

## 自定义时要注意

- **每个用户的 `chat.db` 只能往前升。** 0.9.235 第一次打开时会加列和表（审批授权、归档、定时任务名称、对话
  自己的模型、等待中的运行）。之后旧版 lovia 打开会报 “newer than this lovia knows”。可能回退的话，先备份
  `data_dir` 下各用户的 `chat.db`。
- **`app_options` 里的对象所有用户共用。** lovia 新增的几个 `create_app` 参数不适合放进去：
  - `workspaces=WorkspaceSwitch(...)`（0.9.148）让每个对话自选文件夹和权限模式，默认 `roots="any"`，即主机上
    任意目录，等于让用户读别人的数据。要用的话只能每个用户一个、`roots` 指向自己的 home，`app_options`
    做不到。
  - `config_runtime` 是 `default_app()` 的“设置”页配置接口，读写的是一份全局配置，不是给多用户用的。
  - `question_channel` 必须和 `ask_human` 工具用同一个 `HumanChannel`，而工具是在 `agent_factory` 里按用户
    建的，一个共用的 channel 会把问题发错人。目前本项目不支持 `ask_human`。
- **`lovia[web]` 装的东西多了。** 从 0.9.199 起它包含 `mcp` 包，`uv.lock` 因此多了 `jsonschema`、`pyjwt`
  等依赖。
- **停用账号时挂起运行（0.9.232）。** 关闭一个用户的 app 时，lovia 会把在等审批的运行挂起，重新启用、app 再次
  live 后可以继续回答。原来停用时这些运行直接结束。

## 无需改动，但值得知道

- **模板 block 没有变化。** `head`、`sidebar_nav`、`sidebar_footer`、`body_end` 的名字和含义都和 0.9.128 一致，
  用到的 `--lv-*` 变量和 `[data-part="composer"]` 也都还在。
- **“设置”挪到了侧栏底部**（0.9.204），排在 `sidebar_footer` 的账号区上面；“记忆”成了设置里的一个标签。
  “管理后台”仍在 `sidebar_nav`，和“新对话”“定时任务”画法一样。
- **只读查看时的新操作。** 定时任务页的新建和编辑、归档对话、审批卡片的回答都是写请求，管理员点击会得到 403，
  和原来的重命名、删除一样。
- **`create_app` 已有的参数没有变化**，保留参数列表（`_RESERVED`）不用改。

## 验证

- `uv run --extra dev pytest`：41 个测试全部通过；`ruff check .` 没有问题。
- 在浏览器里用 `examples/demo.py` 检查：
  - 管理员自己的空间里，“管理后台”“设置”“退出登录”样式一致，控制台没有报错；
  - 只读查看 alice 时输入框隐藏，提示条正常；
  - 看一次 bob 的页面，审计只记一条 `GET /`；
  - 退出登录后，上面列出的 localStorage 和 sessionStorage key 都被清空。
