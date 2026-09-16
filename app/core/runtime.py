# 导入 json 模块，用于解析大模型返回的工具参数以及将工具执行结果序列化为 JSON 字符串
import json
# 导入 time 模块，用于计算工具执行的实际耗时
import time
# 从 typing 模块导入 Any 类型，用于在类型提示中表示任意数据类型
from typing import Any

# 导入封装好的大语言模型客户端
from app.core.llm import LLMClient
# 导入前面编写的链路追踪器，用于记录运行过程中的各种事件
from app.observability.tracer import Tracer
# 导入工具注册表类
from app.tools.registry import ToolRegistry


class AgentRuntime:
    """
    Agent 运行时类。
    负责驱动大模型与工具之间的交互循环（ReAct 模式）。
    集成了 Tracer，能够详细记录每一步的 LLM 交互、工具调用、异常错误等全链路信息。
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        tracer: Tracer,
        max_steps: int = 5,
    ) -> None:
        """
        初始化 Agent 运行时环境。
        
        参数:
            llm (LLMClient): 大语言模型客户端实例。
            tools (ToolRegistry): 工具注册表实例，包含所有可用工具。
            tracer (Tracer): 链路追踪器实例，用于记录运行日志。
            max_steps (int): 最大执行步数，防止大模型陷入无限调用工具的死循环，默认为 5。
        """
        self.llm = llm
        self.tools = tools
        self.tracer = tracer
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
        # 开启一个从 1 到 max_steps 的循环，每次循环代表一次与大模型的交互步数
        for step in range(1, self.max_steps + 1):
            # --- 1. 调用大模型 ---
            try:
                # 向大模型发送当前消息历史、可用工具定义以及当前步数
                response = await self.llm.chat(
                    messages=messages,
                    tools=self.tools.openai_tools(),
                    step=step,
                )
            except Exception as e:
                # 如果调用大模型发生异常，记录错误日志并向上抛出
                self.tracer.log_error(step, "llm_call", str(e))
                raise

            # 提取大模型返回的第一条消息及工具调用列表
            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            # --- 2. 处理工具调用 ---
            if tool_calls:
                # 将大模型包含 tool_calls 的完整消息追加到消息历史中
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                # 逐个执行大模型请求的工具调用
                for tc in tool_calls:
                    tool_name = tc.function.name          # 获取要调用的工具名称
                    raw_args = tc.function.arguments or "{}"  # 获取参数字符串

                    # 尝试解析工具参数
                    try:
                        args = json.loads(raw_args)
                        # 防御性检查：确保解析后的参数确实是一个字典
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError as e:
                        # 如果 JSON 解析失败，记录错误日志，并将参数回退为空字典
                        self.tracer.log_error(
                            step, "tool_args_parse", str(e), {"raw": raw_args}
                        )
                        args = {}

                    # 【链路追踪】记录工具调用的发起事件
                    self.tracer.log_tool_call(step, tool_name, args)

                    # 尝试从注册表中获取工具实例
                    try:
                        tool = self.tools.get(tool_name)
                    except KeyError as e:
                        # 如果工具不存在，记录错误日志，并向消息历史中追加一条错误反馈
                        self.tracer.log_error(step, "tool_lookup", str(e), {"tool": tool_name})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(
                                    {
                                        "status": "error",
                                        "error": {
                                            "code": "TOOL_NOT_FOUND",
                                            "message": f"工具不存在：{tool_name}",
                                        },
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        )
                        # 跳过当前工具，继续处理下一个工具调用
                        continue

                    # 记录工具开始执行的时间
                    t0 = time.time()
                    # 尝试执行工具
                    try:
                        result = await tool.run(**args)
                        # 将 Pydantic 模型转换为字典，并排除值为 None 的字段
                        response_dict = result.model_dump(exclude_none=True)
                    except Exception as e:
                        # 如果工具执行过程中抛出异常，计算耗时，记录错误日志
                        time_ms = int((time.time() - t0) * 1000)
                        self.tracer.log_error(
                            step, "tool_run", str(e), {"tool": tool_name, "args": args}
                        )
                        # 构造工具执行失败的响应字典
                        response_dict = {
                            "status": "error",
                            "error": {
                                "code": "TOOL_EXCEPTION",
                                "message": str(e),
                            },
                        }
                        # 【链路追踪】记录工具执行结果（包含异常）
                        self.tracer.log_tool_result(step, tool_name, response_dict, time_ms)
                        # 将错误结果追加到消息历史中，让大模型知道工具执行失败了
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(response_dict, ensure_ascii=False),
                            }
                        )
                        # 跳过当前工具，继续处理下一个
                        continue

                    # 如果工具正常执行完毕，计算耗时
                    time_ms = int((time.time() - t0) * 1000)
                    # 【链路追踪】记录工具成功执行的结果
                    self.tracer.log_tool_result(step, tool_name, response_dict, time_ms)

                    # 将工具的成功执行结果追加到消息历史中
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(response_dict, ensure_ascii=False),
                        }
                    )

                # 当前轮次的所有工具调用处理完毕，使用 continue 进入下一次循环
                # 将带有工具执行结果的消息历史重新发送给大模型
                continue

            # --- 3. 获取最终回复 ---
            # 如果大模型没有请求调用工具，说明它已经给出了最终的文本回复
            content = msg.content or ""
            # 【链路追踪】记录 Agent 的最终回复
            self.tracer.log_final(content)
            # 直接返回最终文本
            return content

        # 如果循环结束（达到最大步数）仍未返回，说明 Agent 陷入了死循环
        # 【链路追踪】记录运行时超时错误
        self.tracer.log_error(self.max_steps, "runtime", "超过最大步数，未得到最终回复")
        raise RuntimeError(f"Agent 超过最大步数 {self.max_steps}，仍未得到最终回复")