# lovia-multiuser

让一个 [lovia](https://github.com/cymoo/lovia) agent 同时服务多个用户：每个用户只能看到自己的记录，管理员能查看所有人的记录。

- **按结构隔离**：每个用户有自己的 lovia 应用，挂在 `/u/<id>/` 下，自带独立的对话库、定时任务、事件流、工作区和记忆。用户之间不共享数据存储，不需要在每条路由里写归属检查。
- **管理员只读查看**：管理后台列出所有用户和对话，支持跨用户搜索；点开任何对话，就在该用户的原版聊天界面里只读查看。
- **审计**：进入他人空间的请求（查看、被拒的写操作、越权访问）和账号操作都有记录。
- **账号停用**：立即登出，运行停止，定时任务不再触发；记录保留，管理员仍可查看。
- **认证可替换**：自带账号密码登录作为参考实现，换成 SSO、代理头或 JWT 只需实现一个方法。

lovia 聊天界面已有的功能都原样可用：流式输出、断线重连、工具审批、定时任务、子任务、文件与记忆面板。

## 快速开始

需要一个模型服务的 API key：OpenAI、Anthropic，或 DeepSeek、Ollama 等 OpenAI 兼容服务。

推荐用 [uv](https://docs.astral.sh/uv/) 运行：它会自动准备 Python、创建虚拟环境、安装依赖，不需要手动激活环境，Windows、macOS、Linux 的命令完全相同。安装 uv：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 1. 获取代码

```bash
git clone https://github.com/cymoo/lovia-multiuser.git
cd lovia-multiuser
```

### 2. 配置模型

把 `.env.example` 复制为 `.env`：

```bash
# macOS / Linux
cp .env.example .env
# Windows
copy .env.example .env
```

打开 `.env`，保留一组模型配置，填上自己的 key：

| 模型服务 | `.env` 内容 |
| --- | --- |
| OpenAI | `LOVIA_MODEL=openai:gpt-5.5`<br>`OPENAI_API_KEY=sk-...` |
| Anthropic | `LOVIA_MODEL=anthropic:claude-sonnet-5-5`<br>`ANTHROPIC_API_KEY=sk-ant-...` |
| DeepSeek | `LOVIA_MODEL=deepseek-chat`<br>`OPENAI_BASE_URL=https://api.deepseek.com`<br>`OPENAI_API_KEY=sk-...` |
| 本机 Ollama | `LOVIA_MODEL=qwen3`<br>`OPENAI_BASE_URL=http://localhost:11434/v1`<br>`OPENAI_API_KEY=ollama` |

`LOVIA_MODEL` 带 `openai:` 或 `anthropic:` 前缀时走对应的官方协议；不带前缀时走 OpenAI 兼容协议，发往 `OPENAI_BASE_URL`。更多写法见 lovia 的 [Provider 文档](https://github.com/cymoo/lovia/blob/main/docs/zh/providers.md)。

`.env` 在启动时自动加载，不需要手动导出到终端；终端里已经设置的同名环境变量优先。`.env` 已被 git 忽略，不会提交密钥。

### 3. 启动

```bash
uv run examples/serve.py
```

首次运行会先安装依赖，稍等片刻。启动后终端显示：

```
首次启动，已创建管理员账号：admin，密码：xxxxxxxxxxxxxxxx
（只显示这一次。修改密码：lovia-multiuser users passwd admin）

模型：openai:gpt-5.5　数据目录：/…/lovia-multiuser/data
打开 http://127.0.0.1:8000 登录
```

浏览器打开 <http://127.0.0.1:8000>，用 `admin` 和这个密码登录。密码只显示一次，忘了可以用 `uv run lovia-multiuser users passwd admin` 重设。按 `Ctrl+C` 停止服务。

### 不用 uv

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -e .
python examples/serve.py
```

之后文中的 `uv run <命令>`，在已激活虚拟环境的终端里直接运行 `<命令>` 即可，例如 `lovia-multiuser users list`。

## 添加用户

```bash
uv run lovia-multiuser users add alice --name Alice
uv run lovia-multiuser users add bob --name Bob
uv run lovia-multiuser users list
```

- 每条命令会要求输入两次密码，至少 8 位。
- 用户 id 用于登录和 URL，只能是小写字母、数字、`_`、`-`，最长 32 位；`--name` 是显示名，可以用中文。
- 加 `--admin` 创建管理员。
- 服务运行中也可以添加，新用户马上就能登录。

## 配置项

全部通过环境变量设置，写在 `.env` 里即可：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LOVIA_MODEL` | 必填 | 模型，见上面的表格 |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | 按模型必填 | 模型服务的 key |
| `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` | 官方地址 | 兼容服务或代理的地址 |
| `LOVIA_MU_DATA` | `data` | 数据目录：账号、审计日志、签名密钥、每个用户的数据 |
| `LOVIA_MU_HOST` | `127.0.0.1` | 监听地址；让局域网访问用 `0.0.0.0` |
| `LOVIA_MU_PORT` | `8000` | 端口 |
| `LOVIA_MU_SECURE` | 未设置 | 部署在 HTTPS 后面时设为 `1`，登录 cookie 只通过 HTTPS 发送 |

请求超时、代理、自定义证书等网络设置，见 lovia 的 [Provider 文档 · 网络](https://github.com/cymoo/lovia/blob/main/docs/zh/providers.md#网络超时代理tls)。

启动服务和运行命令都在项目根目录执行：`.env` 从当前目录开始查找，数据目录默认也相对于当前目录。

**常见问题**

- **提示"没有找到 .env 文件"或"没有 LOVIA_MODEL"**：检查项目根目录下有没有 `.env`，里面的 `LOVIA_MODEL` 是否取消了注释。
- **能打开页面，但发消息后报认证错误**：API key 不对，或者 `LOVIA_MODEL` 和 key 不是同一家服务。
- **端口被占用**：在 `.env` 里设置 `LOVIA_MU_PORT=8001`。
- **Windows 提示找不到 `uv`**：安装 uv 后重新打开终端。

## 使用

### 普通用户

- 登录后进入自己的空间 `/u/<id>/`，看到的只有自己的对话、定时任务、记忆和文件。
- 可以在输入框上传文件，agent 能读取；示例配置下 agent 不能写文件，也不能执行命令。
- "记忆"面板显示 agent 记住的偏好，可以查看和编辑。
- 侧边栏底部显示当前用户，点"退出登录"会同时清掉浏览器里保存的未发送草稿。

### 管理员

登录后进入管理后台 `/admin`：

- **用户**：所有用户的状态、对话数、最近活动，以及所有人最近活跃的对话。
- **用户详情**：该用户的全部对话、定时任务和相关审计记录；可以停用或启用账号。
- **搜索**：按对话标题或 id 搜索所有用户的对话。
- **审计**：按操作者或对象用户筛选审计记录。

点开任何对话，会在该用户的聊天界面里打开：输入框隐藏，底部显示"只读查看 X 的记录"。管理员在别人空间里的任何修改都会被拒绝（403）并记入审计。

管理员也有自己的对话空间，点后台顶部的"我的对话"进入；在聊天界面里点侧边栏的"管理后台"返回。

**停用账号**后，该用户立即被登出，正在进行的运行停止，定时任务不再触发，记录保留供管理员查看。重新启用后恢复。

## 定制 agent

每个用户的 agent 由 `examples/serve.py` 里的 `agents(user, home)` 构建，`home` 是该用户的私有目录 `data/users/<id>/`。可以直接修改它，或复制到自己的项目里：

```python
def agents(user: User, home: Path) -> Agent:
    return Agent(
        name="assistant",
        instructions=f"You are a helpful assistant. The person you are talking to is {user.name}.",
        model=MODEL,
        tools=[...],  # 你的工具
        workspace=Workspace.local(str(home / "files"), mode="readonly"),
        plugins=[Memory(home / "memory")],
    )
```

- 工作区和记忆放在 `home` 下，用户之间就互相看不到。
- 工作区只能用 `readonly` 或不用，原因见下面的"安全边界"。
- 需要以当前用户身份查询业务数据的工具，在这里绑定 `user`，参考 [examples/per_user_tools.py](examples/per_user_tools.py)。
- 服务级参数（每个用户的并发上限、预算、推荐追问等）通过 `create_multiuser_app(app_options=...)` 传给每个用户的 lovia 应用，见[使用指南](docs/guide.md#create_multiuser_app-参数)。

## 接入自己的认证

自带的账号密码登录是参考实现。要换成公司的 SSO，实现一个方法即可：

```python
class ProxyHeaderAuth:
    async def authenticate(self, request) -> str | None:
        return request.headers.get("X-Forwarded-User") or None
```

完整示例见 [examples/proxy_auth.py](examples/proxy_auth.py)；替换用户系统（角色、停用状态）见[使用指南 · 替换认证](docs/guide.md#替换认证)。

## 日常运维

| 命令 | 作用 |
| --- | --- |
| `uv run lovia-multiuser users list` | 列出用户 |
| `uv run lovia-multiuser users add <id> [--name 名字] [--admin]` | 新建用户 |
| `uv run lovia-multiuser users passwd <id>` | 重设密码 |
| `uv run lovia-multiuser users disable <id>` | 停用账号 |
| `uv run lovia-multiuser users enable <id>` | 启用账号 |
| `uv run lovia-multiuser audit [--actor id] [--owner id] [--limit N]` | 查看审计记录 |

命令使用和服务相同的数据目录（`.env` 里的 `LOVIA_MU_DATA`，或 `--data 目录`）。用命令行停用或启用，运行中的服务会在 30 秒内同步；在管理后台操作则立即生效。

数据目录结构（整体备份 `data/` 即可）：

```
data/
  accounts.db        账号
  audit.db           审计日志
  secret             登录 cookie 的签名密钥，丢失后所有人需重新登录
  users/<id>/
    chat.db          对话、运行记录、定时任务
    files/           工作区，上传的文件在 files/uploads/
    memory/          记忆
```

## 部署上线

- **HTTPS**：放在 nginx 等反向代理后面，在 `.env` 里设置 `LOVIA_MU_SECURE=1`。
- **单进程**：运行中的对话保存在进程内存里，不要开多个 worker。
- **部署在域名根路径或子域名下**：暂不支持挂在 `/chat/` 这样的路径前缀下。
- **流式输出**：反向代理要关闭缓冲并调大超时，否则回复会卡住或中断。

nginx 示例：

```nginx
server {
    listen 443 ssl;
    server_name chat.example.com;
    # ssl_certificate ...;

    client_max_body_size 30m;            # 文件上传，lovia 默认单个上限 25 MB

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;             # SSE 流式输出
        proxy_read_timeout 3600s;
    }
}
```

## 模型调用成本

每条消息除了回复本身，还可能产生额外的模型调用：

- 新对话生成标题：每个对话一次。不需要时传 `app_options={"generate_titles": False}`。
- 记忆整理：每轮对话结束后一次。改成 `Memory(..., auto_curate=False)` 只保留模型主动记下的内容，或者去掉 `Memory` 插件。

## 安全边界

同一进程内的隔离，只在用户**没有 shell、工作区为 `readonly` 或不用工作区**时成立。lovia 的本地工作区是策略闸门，不是沙箱：开放 shell 或 `coding` / `trusted` 模式，用户就可能读到其他人的数据。需要给不可信用户 shell，请每个用户一个容器。详见[设计方案 · 安全边界](docs/design.md#9-安全边界)。

## 开发

```bash
uv run --extra dev pytest                # 测试不调用真实模型
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

## 文档

- [设计方案](docs/design.md)：选型、请求处理、权限模型、审计、停用、安全边界、已知限制
- [使用指南](docs/guide.md)：编写 agent、替换认证、全部参数、数据导出与删除
- [升级到 lovia 0.9.112](docs/upgrade-lovia-0.9.112.md)：从 0.9.96 升级时要改什么
- [升级到 lovia 0.9.96](docs/upgrade-lovia-0.9.96.md)：从 0.9.75 升级时要改什么
- 示例：[serve.py](examples/serve.py)、[per_user_tools.py](examples/per_user_tools.py)、[proxy_auth.py](examples/proxy_auth.py)
