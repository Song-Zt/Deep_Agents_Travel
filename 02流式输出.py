import os
from bdb import set_trace
from typing import Literal, List

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from tavily import TavilyClient
from langchain.tools import tool

# 加载.env环境配置，如果在环境变量中配置了，就不会加载.env文件
load_dotenv()

# 创建TavilyClient对象
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# 定义一个联网搜索工具函数
@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """
    使用 Tavily 进行联网搜索
    :param query: 搜索查询
    :param max_results: 最大搜索结果数
    :param topic: 搜索主题
    :param include_raw_content: 是否包含原始内容
    """

    return tavily_client.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )

llm = ChatOpenAI(
    model=os.getenv("deepseek_model"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 创建深度智能体
agent = create_deep_agent(
    model=llm,
    tools=[internet_search],
    system_prompt="你是一个助手，需要使用网络搜索工具来获取信息。请使用中文回答问题。"
)
stream_result = agent.stream(
    {
        "messages": [
            {
                "role": "user",
                "content": "什么是deepagents",
            }
        ]
    }
)

for chunk in stream_result:
    for key, value in chunk.items():
        if not value or "messages" not in value: continue
        messages = value["messages"]
        if (messages and isinstance(messages, List)):
            last_msg = messages[-1]
            if key == 'model':
                if last_msg.tool_calls:
                    for tool_call in last_msg.tool_calls:
                        print(f"智能体决定调用工具{tool_call['name']} 传入参数：{tool_call['args']}")
                elif last_msg.content:
                    print(f"智能体最终执行结果：{last_msg.content}")
            elif key == 'tools':
                print(f"智能体调用{last_msg.name}工具返回结果：{last_msg.content}")

