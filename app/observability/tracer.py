"""
执行追踪器（Tracer）。

负责记录 Agent 运行过程中的所有关键事件，
生成结构化的 JSONL 日志文件，便于调试、复盘和性能分析。

每个 run_id 对应一次完整的 Agent 执行过程，
日志文件保存在 traces/ 目录下，格式为 {run_id}.jsonl。
"""

# 导入 json，用于序列化日志事件
import json
# 导入 time，用于记录时间戳和计算耗时
import time
# 导入 uuid，用于生成唯一的 run_id
import uuid
# 导入 Path，用于处理日志文件路径
from pathlib import Path
# 导入 Any 类型，用于灵活的字典值类型标注
from typing import Any


# ==================== 追踪器实现 ====================

class Tracer:
    """
    执行追踪器。
    
    负责记录 Agent 运行过程中的所有关键事件，包括：
    - LLM 请求与响应
    - 工具调用与结果
    - 上下文状态
    - 错误信息
    - 最终输出
    
    日志以 JSONL 格式保存，每行一个事件，便于逐行读取和分析。
    """
    
    def __init__(
        self,
        run_id: str | None = None,
        log_dir: str = "traces",
    ) -> None:
        """
        初始化追踪器。
        
        参数:
            run_id (str | None): 运行 ID，用于标识一次完整的 Agent 执行过程。
                如果未提供，则自动生成一个 12 位的随机 ID。
            log_dir (str): 日志文件保存目录，默认为 "traces"。
        """
        # 生成或使用提供的 run_id，截取前 12 位作为唯一标识
        self.run_id = run_id or uuid.uuid4().hex[:12]
        
        # 创建日志目录的 Path 对象
        self.log_dir = Path(log_dir)
        
        # 确保日志目录存在，如果不存在则创建（包括父目录）
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化事件列表，用于存储所有日志事件
        self.events: list[dict[str, Any]] = []
        
        # 记录追踪器初始化的时间戳，用于计算相对时间
        self._t0 = time.time()

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """
        记录一个通用事件。
        
        参数:
            event_type (str): 事件类型，例如 "llm_request"、"tool_call" 等。
            payload (dict[str, Any] | None): 事件的具体数据，默认为空字典。
        """
        # 添加事件到列表，包含四个字段：
        # - ts: 相对时间戳（秒），从追踪器初始化开始计算
        # - run_id: 运行 ID，用于关联同一次执行的所有事件
        # - event: 事件类型
        # - payload: 事件的具体数据
        self.events.append(
            {
                "ts": round(time.time() - self._t0, 4),  # 保留 4 位小数
                "run_id": self.run_id,
                "event": event_type,
                "payload": payload or {},  # 如果 payload 为 None，则使用空字典
            }
        )

    def log_llm_request(
        self,
        step: int,
        messages: list[dict],
        tools: list[dict],
    ) -> None:
        """
        记录 LLM 请求事件。
        
        参数:
            step (int): 当前执行步骤编号。
            messages (list[dict]): 发送给 LLM 的完整 messages 列表。
            tools (list[dict]): 当前可用的工具描述列表。
        """
        self.log(
            "llm_request",  # 事件类型
            {
                "step": step,  # 步骤编号
                "message_count": len(messages),  # 消息数量，用于快速评估上下文长度
                "messages": messages,  # 完整的 messages 列表，用于复盘上下文内容
                "tool_names": [t["function"]["name"] for t in tools],  # 工具名称列表，用于查看当前可用工具
            },
        )

    def log_llm_response(
        self,
        step: int,
        content: str,
        tool_calls: list[dict],
        usage: dict | None,
    ) -> None:
        """
        记录 LLM 响应事件。
        
        参数:
            step (int): 当前执行步骤编号。
            content (str): LLM 回复的文本内容。
            tool_calls (list[dict]): LLM 请求的工具调用列表。
            usage (dict | None): LLM 的 token 使用情况（prompt_tokens、completion_tokens 等）。
        """
        self.log(
            "llm_response",  # 事件类型
            {
                "step": step,  # 步骤编号
                "content": content,  # LLM 回复内容
                "tool_calls": tool_calls,  # 工具调用列表，用于查看 LLM 选择了哪些工具
                "usage": usage or {},  # token 使用情况，用于成本统计和性能分析
            },
        )

    def log_tool_call(
        self,
        step: int,
        tool_name: str,
        args: dict,
    ) -> None:
        """
        记录工具调用事件（调用前）。
        
        参数:
            step (int): 当前执行步骤编号。
            tool_name (str): 被调用的工具名称。
            args (dict): 传递给工具的参数。
        """
        self.log(
            "tool_call",  # 事件类型
            {
                "step": step,  # 步骤编号
                "tool": tool_name,  # 工具名称
                "args": args,  # 工具参数，用于复盘工具调用是否正确
            },
        )

    def log_tool_result(
        self,
        step: int,
        tool_name: str,
        response: dict,
        time_ms: int,
    ) -> None:
        """
        记录工具执行结果事件（调用后）。
        
        参数:
            step (int): 当前执行步骤编号。
            tool_name (str): 被调用的工具名称。
            response (dict): 工具执行的结果字典，包含 status、error、data 等字段。
            time_ms (int): 工具执行耗时（毫秒），用于性能分析。
        """
        self.log(
            "tool_result",  # 事件类型
            {
                "step": step,  # 步骤编号
                "tool": tool_name,  # 工具名称
                "status": response.get("status"),  # 工具执行状态（success/error）
                "error": response.get("error"),  # 错误信息（如果有）
                "truncated": response.get("data", {}).get("truncated", False),  # 数据是否被截断
                "time_ms": time_ms,  # 执行耗时，用于性能分析
            },
        )

    def log_context(self, step: int, info: dict) -> None:
        """
        记录上下文状态事件。
        
        用于记录 Agent 在执行过程中的内部状态变化，
        例如 Todo 列表更新、Summary 生成等。
        
        参数:
            step (int): 当前执行步骤编号。
            info (dict): 上下文状态信息，例如 {"todo_count": 2, "has_summary": True}。
        """
        # 使用 "context" 事件类型，将 info 字典展开合并到 payload 中
        self.log("context", {"step": step, **info})

    def log_error(
        self,
        step: int,
        where: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        """
        记录错误事件。
        
        参数:
            step (int): 当前执行步骤编号。
            where (str): 错误发生的位置，例如 "tool_execution"、"llm_call"。
            message (str): 错误消息。
            details (dict | None): 错误的详细信息，例如堆栈跟踪、异常类型等。
        """
        self.log(
            "error",  # 事件类型
            {
                "step": step,  # 步骤编号
                "where": where,  # 错误位置
                "message": message,  # 错误消息
                "details": details or {},  # 详细信息
            },
        )

    def log_final(self, content: str) -> None:
        """
        记录最终输出事件。
        
        参数:
            content (str): Agent 的最终输出内容。
        """
        self.log(
            "final",  # 事件类型
            {
                "content": content,  # 最终输出内容
            },
        )

    def save(self) -> Path:
        """
        保存所有日志事件到 JSONL 文件。
        
        JSONL 格式：每行一个 JSON 对象，便于逐行读取和分析，
        不需要一次性加载整个文件到内存。
        
        返回:
            Path: 保存的日志文件路径。
        """
        # 构建日志文件路径：traces/{run_id}.jsonl
        path = self.log_dir / f"{self.run_id}.jsonl"
        
        # 以写入模式打开文件，使用 UTF-8 编码
        with path.open("w", encoding="utf-8") as f:
            # 遍历所有事件
            for e in self.events:
                # 将每个事件序列化为 JSON 字符串，写入一行
                # ensure_ascii=False 确保中文等非 ASCII 字符正常显示
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        
        # 返回保存的文件路径
        return path