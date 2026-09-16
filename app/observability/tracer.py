
# 导入 json 模块，用于将事件数据序列化为 JSON 字符串并写入文件
import json
# 导入 time 模块，用于记录事件发生的时间戳和计算耗时
import time
# 导入 uuid 模块，用于生成全局唯一的运行 ID
import uuid
# 从 pathlib 导入 Path 类，提供面向对象的文件系统路径操作方式
from pathlib import Path
# 从 typing 导入 Any 类型，表示任意数据类型
from typing import Any


class Tracer:
    """
    最小可诊断链路追踪器。
    核心功能：记录 Agent 运行过程中的每一步事件（如 LLM 请求、工具调用等），
    并将这些事件以 JSONL（JSON Lines）格式落盘保存，方便后续排查问题和回溯链路。
    """

    def __init__(self, run_id: str | None = None, log_dir: str = "traces") -> None:
        """
        初始化追踪器。
        
        参数:
            run_id (str | None): 本次运行的唯一标识。如果未提供，则自动生成一个 12 位的 UUID 短码。
            log_dir (str): 日志文件保存的目录路径，默认为 "traces"。
        """
        # 设置运行 ID，若未传入则截取 uuid 的前 12 位作为简短的唯一标识
        self.run_id = run_id or uuid.uuid4().hex[:12]
        
        # 将日志目录字符串转换为 Path 对象
        self.log_dir = Path(log_dir)
        # 自动创建日志目录（包括父级目录），如果目录已存在则不报错
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化一个空列表，用于在内存中暂存本次运行期间发生的所有事件
        self.events: list[dict[str, Any]] = []
        
        # 记录追踪器初始化的起始时间，后续所有事件的时间戳都相对于这个时间计算
        self._t0 = time.time()

    def log(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """
        记录一个通用事件（底层核心方法）。
        
        参数:
            event_type (str): 事件的类型名称（如 "llm_request", "tool_call" 等）。
            payload (dict[str, Any] | None): 事件携带的具体数据字典，默认为 None。
        """
        # 构建事件字典并追加到内存事件列表中
        self.events.append(
            {
                "ts": round(time.time() - self._t0, 4),  # 计算相对时间戳（秒），保留 4 位小数
                "run_id": self.run_id,                   # 关联当前的运行 ID
                "event": event_type,                     # 事件类型
                "payload": payload or {},                # 事件数据，若为 None 则使用空字典
            }
        )

    def log_llm_request(self, step: int, messages: list[dict], tools: list[dict]) -> None:
        """
        记录一次发送给大语言模型（LLM）的请求。
        
        参数:
            step (int): 当前执行的步数。
            messages (list[dict]): 发送给 LLM 的完整消息历史。
            tools (list[dict]): 提供给 LLM 的工具定义列表。
        """
        self.log(
            "llm_request",  # 事件类型
            {
                "step": step,
                "messages": messages,
                "tool_count": len(tools),  # 记录可用工具的数量
                # 提取并记录所有可用工具的名称列表，方便快速查看
                "tool_names": [t["function"]["name"] for t in tools],
            },
        )

    def log_llm_response(self, step: int, content: str, tool_calls: list[dict], usage: dict | None) -> None:
        """
        记录大语言模型（LLM）返回的响应。
        
        参数:
            step (int): 当前执行的步数。
            content (str): LLM 返回的文本内容。
            tool_calls (list[dict]): LLM 请求调用的工具列表。
            usage (dict | None): Token 消耗等用量统计信息。
        """
        self.log(
            "llm_response",  # 事件类型
            {
                "step": step,
                "content": content,
                "tool_calls": tool_calls,
                "usage": usage or {},  # 若用量信息为 None，则回退为空字典
            },
        )

    def log_tool_call(self, step: int, tool_name: str, args: dict) -> None:
        """
        记录一次工具调用的发起。
        
        参数:
            step (int): 当前执行的步数。
            tool_name (str): 被调用的工具名称。
            args (dict): 传递给工具的参数字典。
        """
        self.log("tool_call", {"step": step, "tool": tool_name, "args": args})

    def log_tool_result(self, step: int, tool_name: str, response: dict, time_ms: int) -> None:
        """
        记录一次工具调用的执行结果。
        
        参数:
            step (int): 当前执行的步数。
            tool_name (str): 被调用的工具名称。
            response (dict): 工具返回的响应数据（通常包含 status 和 error 等字段）。
            time_ms (int): 工具执行耗时（毫秒）。
        """
        self.log(
            "tool_result",  # 事件类型
            {
                "step": step,
                "tool": tool_name,
                "status": response.get("status"),  # 安全地提取工具执行状态
                "error": response.get("error"),    # 安全地提取错误信息（如果存在）
                "time_ms": time_ms,                # 记录耗时
            },
        )

    def log_error(self, step: int, where: str, message: str, details: dict | None = None) -> None:
        """
        记录运行过程中发生的异常或错误。
        
        参数:
            step (int): 发生错误时的步数。
            where (str): 错误发生的位置或模块名称。
            message (str): 错误描述信息。
            details (dict | None): 错误的详细附加信息。
        """
        self.log("error", {"step": step, "where": where, "message": message, "details": details or {}})

    def log_final(self, content: str) -> None:
        """
        记录 Agent 最终生成的回复内容，标志着一次完整运行的结束。
        
        参数:
            content (str): Agent 最终返回给用户的文本。
        """
        self.log("final", {"content": content})

    def save(self) -> Path:
        """
        将内存中暂存的所有事件序列化为 JSONL 格式并保存到磁盘。
        
        返回:
            Path: 保存的日志文件的完整路径对象。
        """
        # 拼接日志文件的完整路径：日志目录 / 运行ID.jsonl
        path = self.log_dir / f"{self.run_id}.jsonl"
        
        # 以写入模式打开文件，指定 UTF-8 编码
        with path.open("w", encoding="utf-8") as f:
            # 遍历内存中的每一个事件
            for e in self.events:
                # 将事件字典序列化为 JSON 字符串，ensure_ascii=False 确保中文字符正常显示
                # 每行写入一个 JSON 对象，并在末尾加上换行符，符合 JSONL 规范
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        
        # 返回保存的文件路径，方便调用方打印或进一步处理
        return path