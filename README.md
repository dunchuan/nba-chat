# Pocket Agent Demo

一个可部署为单一公开链接的 FastAPI + LangGraph AI Agent Demo。FastAPI 同时提供前端静态页面与后端 API，LangGraph 使用 `InMemorySaver` 保存当前 Python 进程内的多轮会话状态。

## 本地运行

```powershell
cd ai-agent-demo
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中填入阿里云百炼的 `DASHSCOPE_API_KEY`，然后启动：

```powershell
uvicorn app.main:app --reload
```

访问 <http://127.0.0.1:8000>。

## 部署到 Render

1. 将此目录推送到 GitHub 仓库。
2. 在 Render 创建 Blueprint，并选择这个仓库。
3. 添加 `DASHSCOPE_API_KEY` 环境变量。
4. 部署完成后访问 Render 提供的 `onrender.com` 地址。

免费实例休眠或重启后，`InMemorySaver` 中的 Agent 状态会丢失；浏览器里显示的聊天记录仍保存在 `localStorage`。正式持久化应改用 PostgreSQL checkpointer。

## 模型配置

默认使用阿里云百炼的 OpenAI 兼容接口和 `qwen3.7-plus` 模型：

```env
DASHSCOPE_API_KEY=sk-你的密钥
MODEL_NAME=qwen3.7-plus
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

模型名和接口地址均可通过环境变量覆盖，API Key 只保存在后端，不会发送到浏览器。

## 许可证与权利声明

本项目源代码采用 [MIT License](LICENSE) 开源。

本项目与 NBA、NBA 各球队及其关联机构无隶属、授权或合作关系。NBA 相关名称、商标、数据和内容归各自权利人所有；MIT License 仅适用于本仓库中由项目作者提供的源代码，不授予任何第三方商标、赛事内容或数据的使用权。
