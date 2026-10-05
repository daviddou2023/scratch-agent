from openai import AsyncOpenAI # 专门用于异步编程（asyncio）的客户端，非常适合在 Agent 架构中处理高并发请求
from app.core.config import settings
from app.observability.tracer import Tracer


class LLMClient:
    # 定义大语言模型客户端封装类，将底层的 API 调用逻辑进行抽象和统一管理。
    def __init__(self, tracer: Tracer | None = None) -> None:
        if not settings.openai_api_key:
            raise ValueError("缺少 OPENAI_API_KEY")
        
        # 实例化异步客户端对象，并注入鉴权信息
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None
        )

        self.model = settings.openai_model
        self.tracer = tracer

    async def chat(self, messages, tools=None, step: int = 0):

        # 定义异步对话方法
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

        # 启用了tracer，在发送请求之前记录LLM请求事件
        if self.tracer:
            self.tracer.log_llm_request(step, messages, tools or [])

        response = await self.client.chat.completions.create(**kwargs)
        # 【链路追踪】如果启用了 Tracer，在收到响应后记录 LLM 响应事件
        if self.tracer:
            # 提取响应中的第一条消息
            msg = response.choices[0].message
            
            # 提取 Token 用量统计信息
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,       # 输入消耗的 Token 数
                    "completion_tokens": response.usage.completion_tokens, # 输出消耗的 Token 数
                    "total_tokens": response.usage.total_tokens,         # 总消耗 Token 数
                }
            
            # 提取并格式化大模型请求调用的工具列表
            tool_calls = []
            for tc in (msg.tool_calls or []):
                tool_calls.append(
                    {
                        "id": tc.id,                    # 工具调用的唯一 ID
                        "name": tc.function.name,       # 工具名称
                        "arguments": tc.function.arguments,  # 工具参数（JSON 字符串）
                    }
                )
            
            # 记录 LLM 响应事件，包含文本内容、工具调用列表和 Token 用量
            self.tracer.log_llm_response(step, msg.content or "", tool_calls, usage)

        # 返回完整的 API 响应对象，供上层（如 AgentRuntime）继续处理
        return response