# lovia-multiuser

让一个 [lovia](https://github.com/cymoo/lovia) agent 同时服务多个用户：每个用户只能看到自己的记录，管理员能查看所有人的记录。

- **按结构隔离**：每个用户有自己的 lovia `create_app()`，在 `/u/<id>/` 下，自带独立的对话库、定时任务、事件流、工作区和 Memory。用户之间不共享 store，所以不需要在每条路由里写归属检查。
- **管理员只读查看**：管理后台列出所有用户和对话，支持跨用户搜索；点开任何对话，就在该用户的原版聊天界面中只读查看。
- **审计**：进入他人空间的每个请求（查看、被拒的写操作、越权访问）和账号操作都有记录。
- **账号停用**：立即登出，运行停止，定时任务不再触发；记录保留，管理员仍可查看。
- **认证可替换**：自带账号密码登录作为参考实现；换成 SSO、代理头或 JWT 只需实现一个方法。

lovia.web 已有的流式输出、断线重连、工具审批、定时任务、子任务、文件与记忆面板都原样可用。

## 快速开始

```bash
uv venv && uv pip install -e ".[dev]"
python examples/demo.py      # 无需 API key
```

打开 <http://127.0.0.1:8000>，用 `alice` / `bob` / `admin` 登录，密码 `demo-password`。

接入真实模型：

```bash
lovia-multiuser users add admin --admin
lovia-multiuser users add alice --name Alice
LOVIA_MODEL=... python examples/serve.py
```

## 用法

```python
from lovia import Agent, Memory
from lovia.workspace import Workspace
from lovia_multiuser import create_multiuser_app

def agents(user, home):
    return Agent(
        name="assistant",
        model=MODEL,
        workspace=Workspace.local(str(home / "files"), mode="readonly"),
        plugins=[Memory(home / "memory")],
    )

app = create_multiuser_app(agents, data_dir="data")
```

## 文档

- [设计方案](docs/design.md)：选型、请求处理、权限模型、审计、停用、安全边界、已知限制
- [使用指南](docs/guide.md)：编写 agent、替换认证、参数、部署清单、运维
- 示例：[demo.py](examples/demo.py)、[serve.py](examples/serve.py)、[per_user_tools.py](examples/per_user_tools.py)、[proxy_auth.py](examples/proxy_auth.py)

## 重要限制

同一进程内的隔离只在用户**没有 shell、工作区为 `readonly` 或不用工作区**时成立。需要给不可信用户 shell，请每个用户一个容器。详见[设计方案 · 安全边界](docs/design.md#9-安全边界)。
