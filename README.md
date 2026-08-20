# NBA Chat
访问 <https://nbachat.top>

NBA Chat 是一个基于 FastAPI、LangGraph 和 Qwen 的 NBA ReAct Agent Demo。
它可以根据用户问题自主选择 NBA 数据工具、联网搜索工具和分析模型，并支持多轮对话、缓存复用、流式输出和登录。

## 功能

- 历史比赛：通过 `nba_api` 查询赛果、比分、比赛时间、球员 Box Score 和 Play-by-Play。
- 当前资讯：需要实时信息时使用 Tavily。
- ReAct Agent：模型负责理解任务、选择工具、检查证据并生成答案。
- 多轮上下文：缓存当前进程中的工具结果，支持用“这场”“G1”等表达复用已查询比赛。
- 事实与分析分离：客观数据优先使用快速模型；主观分析使用分析模型。
- 流式响应：前端可以逐步显示模型输出，并支持停止生成。
- 账号系统：支持注册、登录、退出和按用户隔离的对话上下文。

## 本地运行

在项目根目录执行：

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填写至少一个模型 API Key：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
MODEL_NAME=qwen3.7-plus
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

启动服务：

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

浏览器访问：<http://127.0.0.1:8000>

## 账号与登录

页面支持用户自行注册。系统仍保留以下 Demo 账号，便于快速体验：

| 用户名 | 密码 |
| --- | --- |
| `nbachat` | `nbachat` |
| `tester_hlx` | `tester_hlx` |
| `tester_wk` | `tester_wk` |
| `tester_lyk` | `tester_lyk` |

密码使用 PBKDF2-SHA256 加盐哈希保存在 SQLite 中，浏览器只保存 `HttpOnly` 会话 Cookie，不保存密码。

本地单元测试直接调用 Agent 内部逻辑，不需要登录。浏览器测试、API 测试和 live 测试需要先登录。

## 测试

运行不访问真实模型和 NBA API 的快速测试：

```powershell
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
```

运行 live 测试前设置：

```powershell
$env:RUN_LIVE_TESTS="true"
.\\.venv\\Scripts\\python.exe -m unittest tests.test_live_agent tests.test_schedule_game_time -v
```

Live 测试会消耗模型和第三方 API 配额，并可能受网络、代理或 NBA CDN 限制影响。

## 环境变量

常用配置包括：

| 变量 | 用途 |
| --- | --- |
| `DASHSCOPE_API_KEY` | Qwen 模型 API Key |
| `MODEL_NAME` | 主分析模型，默认 `qwen3.7-plus` |
| `MODEL_BASE_URL` | OpenAI 兼容模型服务地址 |
| `NATIVE_MAX_COMPLETION_TOKENS` | ReAct Agent 单次模型输出上限 |
| `TAVILY_API_KEY` | 当前资讯联网搜索，可选 |
| `LANGSMITH_TRACING` | 是否启用 LangSmith 追踪 |
| `LANGSMITH_PROJECT` | LangSmith 项目名称 |
| `REACT_MAX_STEPS` | 单次 ReAct 最大工具步骤数 |
| `LANGGRAPH_RECURSION_LIMIT` | LangGraph 递归安全上限 |
| `SQLITE_PATH` | 用户和登录会话的 SQLite 数据库路径 |
| `AUTH_REQUIRED` | 是否要求登录，默认 `true` |
| `REGISTRATION_ENABLED` | 是否允许注册，默认 `true` |
| `SESSION_MAX_AGE` | 登录会话有效期（秒），默认 7 天 |
| `SESSION_COOKIE_SECURE` | Cookie 是否仅通过 HTTPS 发送；`auto` 会根据请求协议判断 |

不要把 `.env`、真实 API Key 或本地 SQLite 数据库提交到 Git。

## Render 部署

仓库根目录包含 `render.yaml`，可以使用 Render Blueprint 部署：

1. 将代码推送到 GitHub。
2. 在 Render 中创建 Blueprint，选择该 GitHub 仓库。
3. 确认使用 `render.yaml` 中的 Python Web Service。
4. 在 Render 环境变量中填写 `DASHSCOPE_API_KEY`。
5. 如果需要当前资讯，再填写 `TAVILY_API_KEY`。
6. 如果需要 LangSmith，再填写 `LANGSMITH_API_KEY` 并将 `LANGSMITH_TRACING` 改为 `true`。

服务使用以下启动命令：

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

健康检查地址为 `/api/health`。

Render Free 实例可能休眠或重启。当前缓存和 LangGraph 会话状态保存在进程内，重启后会清空；SQLite 适合当前单实例 Demo，扩展为多实例服务时应迁移到 PostgreSQL 等共享数据库。

## 许可证与声明

本项目源代码采用 [MIT License](LICENSE)。本项目与 NBA、NBA 各球队及其关联机构无隶属、授权或合作关系。NBA 相关名称、商标、数据和内容归各自权利人所有。
