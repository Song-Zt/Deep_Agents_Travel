import os
from dataclasses import dataclass

from dotenv import load_dotenv


# 加载项目根目录中的 .env
load_dotenv()


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str


def get_llm_config() -> LLMConfig:
    """
    读取并检查 LLM 配置。
    """

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL", "qwen-plus")

    if not api_key:
        raise ValueError(
            "未配置 OPENAI_API_KEY，请检查项目根目录下的 .env 文件"
        )

    if not base_url:
        raise ValueError("LLM_BASE_URL 不能为空")

    if not model:
        raise ValueError("LLM_MODEL 不能为空")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model
    )