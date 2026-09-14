from openai import AsyncOpenAI # 专门用于异步编程（asyncio）的客户端，非常适合在 Agent 架构中处理高并发请求
from app.core.config import settings

class LLMClient:
    # 定义大语言模型客户端封装类，将底层的 API 调用逻辑进行抽象和统一管理。
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("缺少 OPENAI_API_KEY")
        
        # 实例化异步客户端对象，并注入鉴权信息
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None
        )

        self.model = settings.openai_model
    async def chat(self, messages, tools=None):

        # 定义异步对话方法。
        # - messages: 对话历史消息列表（遵循 OpenAI 的 role/content 格式）。
        # - tools: 可选参数，用于传入工具定义列表（Function Calling 机制）。

        
        # 构建发送给大模型 API 的基础参数字典：
        # - model: 指定使用的模型版本。
        # - messages: 传入上下文消息。
        # - temperature: 设为 0，表示关闭随机性，让模型输出最确定、最严谨的结果。
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto" # 启用了大模型的函数调用能力，允许模型根据对话内容自主决定是否调用外部工具

        # 使用 `await` 异步发起 API 请求，创建聊天补全任务。
        # **kwargs 语法会将上面构建的字典自动解包为函数的关键字参数。
        # 最终返回大模型的响应对象（包含生成的文本或工具调用指令）
        return await self.client.chat.completions.create(**kwargs)