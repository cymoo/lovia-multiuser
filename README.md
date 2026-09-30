# lovia-multiuser

让一个 [lovia](https://github.com/cymoo/lovia) agent 同时服务多个用户：每个用户只能看到自己的记录，管理员能查看所有人的记录。

- **按结构隔离**：每个用户有自己的 lovia 应用，挂在 `/u/<id>/` 下，自带独立的对话库、定时任务、事件流、工作区和记忆。用户之间不共享数据存储，不需要在每条路由里写归属检查。
- **管理员只读查看**：管理后台列出所有用户和对话，支持跨用户搜索；点开任何对话，就在该用户的原版聊天界面里只读查看。
- **审计**：进入他人空间的请求（查看、被拒的写操作、越权访问）和账号操作都有记录。
- **账号停用**：立即登出，运行停止，定时任务不再触发；记录保留，管理员仍可查看。
- **认证可替换**：自带账号密码登录作为参考实现，换成 SSO、代理头或 JWT 只需实现一个方法。

lovia 聊天界面已有的功能都原样可用：流式输出、断线重连、工具审批、定时任务、子任务、文件与记忆面板。

## 环境要求

- Python 3.10 或更高
- 一个模型服务：OpenAI、Anthropic，或任何 OpenAI 兼容服务（DeepSeek、Ollama、vLLM 等）
- 推荐用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境，pip 也可以

## 1. 安装

```bash
git clone https://github.com/cymoo/lovia-multiuser.git
cd lovia-multiuser
uv venv
source .venv/bin/activate
uv pip install -e .
```

用 pip：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

安装后可以使用 `lovia-multiuser` 命令（等价于 `python -m lovia_multiuser`）。以下命令都在项目根目录、已激活虚拟环境的终端里执行。

## 2. 配置模型

```bash
cp .env.example .env
```

编辑 `.env`，保留一组模型配置：

| 模型服务 | 配置 |
| --- | --- |
| OpenAI | `LOVIA_MODEL=openai:gpt-5.5`<br>`OPENAI_API_KEY=sk-...` |
| Anthropic | `LOVIA_MODEL=anthropic:claude-sonnet-5-5`<br>`ANTHROPIC_API_KEY=sk-ant-...` |
| DeepSeek（OpenAI 兼容） | `LOVIA_MODEL=deepseek-chat`<br>`OPENAI_BASE_URL=https://api.deepseek.com`<br>`OPENAI_API_KEY=sk-...` |
| 本机 Ollama | `LOVIA_MODEL=qwen3`<br>`OPENAI_BASE_URL=http://localhost:11434/v1`<br>`OPENAI_API_KEY=ollama` |

`LOVIA_MODEL` 带 `openai:` 或 `anthropic:` 前缀时走对应官方协议；不带前缀时走 OpenAI 兼容协议，发往 `OPENAI_BASE_URL`。更多写法见 lovia 的 [Provider 文档](https://github.com/cymoo/lovia/blob/main/docs/zh/providers.md)。

把 `.env` 加载到当前终端（每开一个新终端都要执行一次）：

```bash
set -a && source .env && set +a
```

`.env` 已被 git 忽略，不会提交密钥。

## 3. 创建账号

先创建至少一个管理员，再创建普通用户：

```bash
lovia-multiuser users add admin --name 管理员 --admin
lovia-multiuser users add alice --name Alice
lovia-multiuser users list
```

- 每条命令会要求输入两次密码，至少 8 位。
- 用户 id 用于登录和 URL，只能是小写字母、数字、`_`、`-`，最长 32 位；`--name` 是显示名，可以用中文。
- 数据默认存在 `./data/`。用 `--data 目录` 可以换位置，但要和启动时的 `LOVIA_MU_DATA` 保持一致。

## 4. 启动服务

```bash
python examples/serve.py
```

浏览器打开 <http://127.0.0.1:8000> 并登录。

启动时可以通过环境变量调整（也可以写进 `.env`）：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LOVIA_MU_DATA` | `data` | 数据目录：账号、审计日志、签名密钥、每个用户的数据 |
| `HOST` | `127.0.0.1` | 监听地址；让局域网访问用 `0.0.0.0` |
| `PORT` | `8000` | 端口 |
| `LOVIA_MU_SECURE` | 未设置 | 部署在 HTTPS 后面时设为 `1`，登录 cookie 只通过 HTTPS 发送 |

常见启动错误：

- `no model configured in the environment`：没有设置 `LOVIA_MODEL`，检查第 2 步是否在当前终端执行过。
- `no accounts in data/ yet`：还没有账号，先做第 3 步。

## 5. 使用

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

## 6. 定制 agent

每个用户的 agent 由 `examples/serve.py` 里的 `agents(user, home)` 构建，`home` 是该用户的私有目录 `data/users/<id>/`。可以直接修改它，或复制到自己的项目里：

```python
def agents(user: User, home: Path) -> Agent:
    return Agent(
        name="assistant",
        instructions=f"You are a helpful assistant. The person you are talking to is {user.name}.",
        model=model_from_env(),
        tools=[...],                                   # 你的工具
        workspace=Workspace.local(str(home / "files"), mode="readonly"),
        plugins=[Memory(home / "memory")],
    )
```

- 工作区和记忆放在 `home` 下，用户之间就互相看不到。
- 工作区只能用 `readonly` 或不用，原因见下面的"安全边界"。
- 需要以当前用户身份查询业务数据的工具，在这里绑定 `user`，参考 [examples/per_user_tools.py](examples/per_user_tools.py)。
- 服务级参数（每个用户的并发上限、预算、推荐追问等）通过 `create_multiuser_app(app_options=...)` 传给每个用户的 lovia 应用，见[使用指南](docs/guide.md#create_multiuser_app-参数)。

## 7. 接入自己的认证

自带的账号密码登录是参考实现。要换成公司的 SSO，实现一个方法即可：

```python
class ProxyHeaderAuth:
    async def authenticate(self, request) -> str | None:
        return request.headers.get("X-Forwarded-User") or None
```

完整示例见 [examples/proxy_auth.py](examples/proxy_auth.py)；替换用户系统（角色、停用状态）见[使用指南 · 替换认证](docs/guide.md#替换认证)。

## 8. 日常运维

| 命令 | 作用 |
| --- | --- |
| `lovia-multiuser users list` | 列出用户 |
| `lovia-multiuser users add <id> [--name 名字] [--admin]` | 新建用户 |
| `lovia-multiuser users passwd <id>` | 重设密码 |
| `lovia-multiuser users disable <id>` | 停用账号 |
| `lovia-multiuser users enable <id>` | 启用账号 |
| `lovia-multiuser audit [--actor id] [--owner id] [--limit N]` | 查看审计记录 |

所有命令都接受 `--data 目录`。用命令行停用或启用，运行中的服务会在 30 秒内同步；在管理后台操作则立即生效。

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

## 9. 部署上线

- **HTTPS**：放在 nginx 等反向代理后面，设置 `LOVIA_MU_SECURE=1`。
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

## 10. 模型调用成本

每条消息除了回复本身，还可能产生额外的模型调用：

- 新对话生成标题：每个对话一次。不需要时传 `app_options={"generate_titles": False}`。
- 记忆整理：每轮对话结束后一次。改成 `Memory(..., auto_curate=False)` 只保留模型主动记下的内容，或者去掉 `Memory` 插件。

## 安全边界

同一进程内的隔离，只在用户**没有 shell、工作区为 `readonly` 或不用工作区**时成立。lovia 的本地工作区是策略闸门，不是沙箱：开放 shell 或 `coding` / `trusted` 模式，用户就可能读到其他人的数据。需要给不可信用户 shell，请每个用户一个容器。详见[设计方案 · 安全边界](docs/design.md#9-安全边界)。

## 开发

```bash
uv pip install -e ".[dev]"
pytest                                   # 测试不调用真实模型
ruff check . && ruff format --check .
```

## 文档

- [设计方案](docs/design.md)：选型、请求处理、权限模型、审计、停用、安全边界、已知限制
- [使用指南](docs/guide.md)：编写 agent、替换认证、全部参数、数据导出与删除
- 示例：[serve.py](examples/serve.py)、[per_user_tools.py](examples/per_user_tools.py)、[proxy_auth.py](examples/proxy_auth.py)
