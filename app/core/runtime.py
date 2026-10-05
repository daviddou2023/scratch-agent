"""Runtime（阶段三版）。

变化：
1. 不再直接接收 messages，而是接收 ContextBuilder。
   - 之前版本直接维护 messages 列表，现在由 ContextBuilder 统一管理
2. 每轮从 ContextBuilder 取完整 messages。
   - 每次循环开始时，从 ContextBuilder 获取当前完整的消息列表
3. 工具结果通过 ContextBuilder 写回 L3。
   - 工具执行结果不再直接追加到 messages，而是通过 ContextBuilder 的 append_tool_result 方法写回
4. 自动触发 Summary 压缩。
   - 当上下文长度超过阈值时，自动调用 Summarizer 进行压缩
5. 大输出走截断 + 落盘。
   - 工具返回的大数据会被截断，并保存到磁盘文件，只保留引用路径
"""

# 导入 json，用于解析工具参数和序列化结果
import json
# 导入 time，用于计算工具执行耗时
import time
# 导入 Any 类型，用于灵活的工具调用参数类型标注
from typing import Any

# 导入配置，包含上下文长度阈值、压缩比例等设置
from app.core.config import settings
# 导入 ContextBuilder，负责构建和管理 LLM 上下文
from app.core.context_builder import ContextBuilder
# 导入错误码，用于标准化的错误响应
from app.core.errors import ErrorCode
# 导入 LLMClient，负责与 LLM API 通信
from app.core.llm import LLMClient
# 导入 ToolResponse，工具执行结果的标准 schema
from app.core.schemas import ToolResponse
# 导入 Summarizer，负责上下文摘要压缩
from app.core.summarizer import Summarizer
# 导入 maybe_truncate，负责大输出截断和落盘
from app.core.truncation import maybe_truncate
# 导入 Tracer，负责记录执行过程中的关键事件
from app.observability.tracer import Tracer
# 导入 ToolRegistry，负责工具的注册和查找
from app.tools.registry import ToolRegistry


# ==================== Agent 运行时 ====================

TODO_STEP_BY_TOOL = {
    "fetch_video_metrics": 0,
    "fetch_comments": 1,
    "clean_comments": 2,
    "analyze_comments": 3,
    "generate_report": 4,
    "generate_suggestions": 5,
}


class AgentRuntime:
    """
    Agent 运行时（阶段三版）。
    
    负责协调整个 ReAct 循环：
    1. 从 ContextBuilder 获取当前上下文
    2. 调用 LLM 获取响应
    3. 如果有工具调用，执行工具并将结果写回 ContextBuilder
    4. 如果没有工具调用，返回最终结果
    5. 自动触发上下文压缩
    """
    
    def __init__(
        self,
        llm: LLMClient,           # LLM 客户端
        tools: ToolRegistry,      # 工具注册表
        tracer: Tracer,           # 执行追踪器
        context: ContextBuilder,  # 上下文构建器
        summarizer: Summarizer,   # 摘要压缩器
        max_steps: int = 10,      # 最大执行步数，防止无限循环
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.tracer = tracer
        self.context = context
        self.summarizer = summarizer
        self.max_steps = max_steps

    async def run(self, user_input: str) -> str:
        """
        执行 Agent 主循环。
        
        参数:
            user_input (str): 用户的初始输入。
        
        返回:
            str: Agent 的最终输出内容。
        
        异常:
            RuntimeError: 当超过最大步数时抛出。
        """
        # 将用户输入追加到上下文（L3 层）
        self.context.append({"role": "user", "content": user_input})

        # 开始 ReAct 循环，最多执行 max_steps 步
        for step in range(1, self.max_steps + 1):
            # ==================== 压缩检查 ====================
            # 检查当前上下文长度是否超过阈值，如果超过则触发压缩
            if self.context.should_compress(
                settings.context_max_tokens,      # 上下文最大 token 数
                settings.context_compress_ratio,  # 压缩目标比例（例如 0.5 表示压缩到一半）
            ):
                # 调用 Summarizer 对 L3 层进行摘要压缩
                summary = await self.summarizer.summarize(
                    self.context.l3,    # 当前 L3 层的完整消息列表
                    goal=user_input,    # 用户原始目标，用于指导摘要生成
                )
                # 应用摘要：清空 L3，将摘要写入 L1
                self.context.apply_summary(summary)
                # 记录压缩事件到 Tracer
                self.tracer.log_context(
                    step,
                    {"action": "compress", "summary_len": len(summary)},
                )

            # ==================== 构建消息 ====================
            # 从 ContextBuilder 获取当前完整的 messages 列表
            # 这会自动合并 L1（摘要）、L2（Todo）、L3（详细对话）
            messages = self.context.get_messages()

            # 记录上下文状态到 Tracer
            self.tracer.log_context(
                step,
                {
                    "action": "build_messages",           # 动作：构建消息
                    "message_count": len(messages),        # 消息数量
                    "has_summary": bool(self.context.summary),  # 是否有摘要
                    "todo_recap": self.context.todo.recap() if self.context.todo else "",  # Todo 列表摘要
                },
            )

            # ==================== 调用 LLM ====================
            try:
                # 调用 LLM，传入当前 messages 和可用工具列表
                response = await self.llm.chat(
                    messages=messages,
                    tools=self.tools.openai_tools(),  # 将工具转换为 OpenAI 格式
                    step=step,                        # 步骤编号，用于 Tracer
                )
            except Exception as e:
                # 如果 LLM 调用失败，记录错误并向上抛出
                self.tracer.log_error(step, "llm_call", str(e))
                raise

            # 提取 LLM 响应中的第一条消息
            msg = response.choices[0].message
            # 提取工具调用列表（如果没有则为空列表）
            tool_calls = msg.tool_calls or []

            # ==================== 处理响应 ====================
            if tool_calls:
                # 情况 1：LLM 请求调用工具
                
                # 构建 assistant 消息，包含 tool_calls 信息
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",  # LLM 可能同时返回文本内容
                    "tool_calls": [
                        {
                            "id": tc.id,  # 工具调用 ID
                            "type": "function",  # 工具类型
                            "function": {
                                "name": tc.function.name,  # 工具名称
                                "arguments": tc.function.arguments,  # 工具参数（JSON 字符串）
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                # 将 assistant 消息追加到上下文
                self.context.append(assistant_msg)

                # 逐个执行工具调用
                for tc in tool_calls:
                    await self._handle_tool_call(step, tc)

                # 继续下一轮循环（LLM 需要根据工具结果再次决策）
                continue

            # 情况 2：LLM 返回最终结果（没有工具调用）
            content = msg.content or ""
            # 将最终结果追加到上下文
            self.context.append({"role": "assistant", "content": content})
            # 记录最终输出到 Tracer
            self.tracer.log_final(content)
            # 返回最终结果，结束循环
            return content

        # 如果循环结束还没有返回结果，说明超过了最大步数
        self.tracer.log_error(self.max_steps, "runtime", "超过最大步数")
        raise RuntimeError(f"Agent 超过最大步数 {self.max_steps}")

    async def _handle_tool_call(self, step: int, tc: Any) -> None:
        """
        处理单个工具调用。
        
        参数:
            step (int): 当前执行步骤编号。
            tc (Any): 工具调用对象，包含 id、function.name、function.arguments。
        """
        # 提取工具名称
        tool_name = tc.function.name
        # 提取原始参数（JSON 字符串），默认为空对象
        raw_args = tc.function.arguments or "{}"

        # ==================== 解析参数 ====================
        try:
            # 尝试将 JSON 字符串解析为字典
            args = json.loads(raw_args)
            # 确保解析结果是字典类型，如果不是则置为空字典
            if not isinstance(args, dict):
                args = {}
        except json.JSONDecodeError as e:
            # 如果 JSON 解析失败，记录错误并使用空字典
            self.tracer.log_error(step, "tool_args_parse", str(e), {"raw": raw_args})
            args = {}

        # 记录工具调用事件到 Tracer
        self.tracer.log_tool_call(step, tool_name, args)

        # ==================== 查找工具 ====================
        try:
            # 从工具注册表中查找工具
            tool = self.tools.get(tool_name)
        except KeyError as e:
            # 如果工具不存在，记录错误并返回错误结果
            self.tracer.log_error(step, "tool_lookup", str(e), {"tool": tool_name})
            # 将错误结果写回上下文
            self.context.append_tool_result(
                tc.id,  # 工具调用 ID，用于关联请求和结果
                json.dumps(
                    {
                        "status": "error",
                        "error": {
                            "code": ErrorCode.TOOL_NOT_FOUND,  # 错误码：工具不存在
                            "message": f"工具不存在：{tool_name}",
                        },
                    },
                    ensure_ascii=False,  # 确保中文正常显示
                ),
            )
            return  # 结束当前工具调用处理

        # ==================== 执行工具 ====================
        # 记录工具执行开始时间
        t0 = time.time()
        try:
            # 调用工具的 run 方法，传入解析后的参数
            result: ToolResponse = await tool.run(**args)
            # 将结果转换为字典（排除 None 值）
            response_dict = result.model_dump(exclude_none=True)
        except Exception as e:
            # 如果工具执行失败，记录错误并返回错误结果
            time_ms = int((time.time() - t0) * 1000)  # 计算耗时（毫秒）
            self.tracer.log_error(step, "tool_run", str(e), {"tool": tool_name, "args": args})
            response_dict = {
                "status": "error",
                "error": {"code": ErrorCode.TOOL_EXCEPTION, "message": str(e)},
            }
            # 记录工具结果到 Tracer
            self.tracer.log_tool_result(step, tool_name, response_dict, time_ms)
            # 将错误结果写回上下文
            self.context.append_tool_result(tc.id, json.dumps(response_dict, ensure_ascii=False))
            return  # 结束当前工具调用处理

        # 计算工具执行耗时（毫秒）
        time_ms = int((time.time() - t0) * 1000)

        # ==================== 大输出截断 + 落盘 ====================
        # 如果工具执行成功或部分成功，检查输出是否过大
        if response_dict.get("status") in {"success", "partial"}:
            # 调用 maybe_truncate 进行截断处理
            data, text, output_path = maybe_truncate(
                tool_name,                      # 工具名称，用于日志
                response_dict.get("data", {}),  # 结构化数据
                response_dict.get("text", ""),  # 文本输出
            )
            # 更新响应字典中的数据和文本
            response_dict["data"] = data
            response_dict["text"] = text
            # 如果有输出文件路径，说明数据被截断并落盘了
            if output_path:
                # 将状态改为 partial，提示 LLM 数据不完整
                response_dict["status"] = "partial"

        # 记录工具结果到 Tracer
        todo_index = TODO_STEP_BY_TOOL.get(tool_name)
        if (
            response_dict.get("status") == "success"
            and todo_index is not None
            and self.context.todo
        ):
            self.context.todo.done(todo_index)

        self.tracer.log_tool_result(step, tool_name, response_dict, time_ms)
        # 将工具结果写回上下文（通过 tool_call_id 关联）
        self.context.append_tool_result(tc.id, json.dumps(response_dict, ensure_ascii=False))
