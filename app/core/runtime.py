# 导入 json 模块，用于解析大模型返回的工具参数以及将工具执行结果序列化为 JSON 字符串
import json
# 从 typing 模块导入 Any 类型，用于在类型提示中表示任意数据类型
from typing import Any

# 导入封装好的大语言模型客户端
from app.core.llm import LLMClient
# 导入前面定义的工具注册表类
from app.tools.registry import ToolRegistry


class AgentRuntime:
    """
    Agent 运行时类。
    负责驱动大模型与工具之间的交互循环（ReAct 模式）。
    它会不断向大模型发送消息，如果大模型决定调用工具，则执行工具并将结果反馈给大模型，
    直到大模型给出最终的文本回复或达到最大执行步数。
    """

    def __init__(self, llm: LLMClient, tools: ToolRegistry, max_steps: int = 5) -> None:
        """
        初始化 Agent 运行时环境。
        
        参数:
            llm (LLMClient): 大语言模型客户端实例。
            tools (ToolRegistry): 工具注册表实例，包含所有可用工具。
            max_steps (int): 最大执行步数，防止大模型陷入无限调用工具的死循环，默认为 5。
        """
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    async def run(self, messages: list[dict[str, Any]]) -> str:
        """
        异步运行 Agent 的核心交互循环。
        
        参数:
            messages (list[dict[str, Any]]): 初始的对话消息列表（符合 OpenAI 消息格式）。
            
        返回:
            str: 大模型最终生成的文本回复。
            
        异常:
            RuntimeError: 当达到最大步数仍未得到最终回复时抛出。
        """
        # 开启一个最多执行 max_steps 次的循环，每次循环代表一次与大模型的交互（或一轮工具调用）
        for _ in range(self.max_steps):
            # 向大模型发送当前消息历史，并附带可用工具的定义（通过 openai_tools() 获取）
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools.openai_tools(),
            )

            # 提取大模型返回的第一条消息
            msg = response.choices[0].message
            # 获取大模型请求调用的工具列表，如果没有则默认为空列表
            tool_calls = msg.tool_calls or []

            # 如果大模型决定调用工具
            if tool_calls:
                # 1. 将大模型包含 tool_calls 的完整消息追加到消息历史中
                # 这是 OpenAI API 规范要求的，必须让模型知道自己之前发起了工具调用
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",  # 大模型在调用工具时可能附带的文本说明
                        "tool_calls": [
                            {
                                "id": tc.id,           # 工具调用的唯一 ID
                                "type": "function",    # 调用类型固定为 function
                                "function": {
                                    "name": tc.function.name,       # 工具名称
                                    "arguments": tc.function.arguments,  # 工具参数（JSON 字符串）
                                },
                            }
                            for tc in tool_calls  # 遍历所有请求的工具调用
                        ],
                    }
                )

                # 2. 逐个执行大模型请求的工具调用
                for tc in tool_calls:
                    tool_name = tc.function.name          # 获取要调用的工具名称
                    raw_args = tc.function.arguments or "{}"  # 获取参数字符串，如果为空则使用空 JSON 对象

                    # 尝试将 JSON 字符串解析为 Python 字典
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        # 如果 JSON 解析失败（大模型生成了非法的参数），则回退为空字典
                        args = {}

                    # 防御性检查：确保解析后的参数确实是一个字典
                    if not isinstance(args, dict):
                        args = {}

                    # 从工具注册表中获取对应的工具实例
                    tool = self.tools.get(tool_name)
                    # 异步执行该工具，并将解析后的参数字典解包传入
                    result = await tool.run(**args)

                    # 3. 将工具的执行结果追加到消息历史中
                    # role 为 "tool"，并通过 tool_call_id 与前面的请求关联
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),  # 将结果序列化为 JSON 字符串，且保留中文字符
                        }
                    )

                # 当前轮次的工具调用全部处理完毕，使用 continue 进入下一次循环
                # 将带有工具执行结果的消息历史重新发送给大模型，让其基于结果生成最终回复
                continue

            # 如果大模型没有请求调用工具，说明它已经给出了最终的文本回复，直接返回
            return msg.content or ""

        # 如果循环结束（达到最大步数）仍未返回，说明 Agent 陷入了无限工具调用的死循环
        raise RuntimeError(f"Agent 超过最大步数 {self.max_steps}，仍未得到最终回复")