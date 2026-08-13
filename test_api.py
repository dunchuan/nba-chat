import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"


def mask_secret(value: str) -> str:
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def main() -> int:
    if not ENV_FILE.exists():
        print(f"[失败] 找不到环境变量文件：{ENV_FILE}")
        return 1

    load_dotenv(dotenv_path=ENV_FILE, override=True)

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    base_url = os.getenv(
        "MODEL_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ).strip()
    model_name = os.getenv("MODEL_NAME", "qwen3.7-plus").strip()

    print(f"环境文件：{ENV_FILE}")
    print(f"Base URL：{base_url}")
    print(f"模型：{model_name}")

    if not api_key:
        print("[失败] DASHSCOPE_API_KEY 未配置或为空。")
        return 1

    print(f"API Key：{mask_secret(api_key)}（已读取）")
    print("正在发送最小测试请求……")

    try:
        client = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            timeout=20,
            max_retries=0,
        )
        response = client.invoke("请只回复：API 测试成功")
    except Exception as exc:
        print(f"[失败] 模型调用失败：{type(exc).__name__}: {exc}")
        return 2

    print(f"[成功] 模型响应：{response.content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
