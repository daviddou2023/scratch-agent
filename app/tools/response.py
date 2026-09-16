"""
工具响应构造函数
"""

# 从 typing 模块导入 Any 类型，用于在类型提示中表示任意数据类型
from typing import Any

# 从当前项目的 app.core.schemas 模块中导入前面定义的响应相关模型
from app.core.schemas import ToolContext, ToolError, ToolResponse, ToolStats


def ok(data: dict[str, Any] | None = None, text: str = "", **stats) -> ToolResponse:
    """
    构建一个表示工具执行成功的响应对象。
    
    参数:
        data (dict[str, Any] | None): 工具执行成功后返回的核心数据字典，默认为 None。
        text (str): 附带的纯文本信息，默认为空字符串。
        **stats: 接收任意数量的关键字参数，用于动态构建 ToolStats（如 time_ms=100）。
        
    返回:
        ToolResponse: 状态为 "success" 的统一响应对象。
    """
    return ToolResponse(
        status="success",  # 设置状态为成功
        data=data or {},   # 如果 data 为 None，则回退使用空字典
        text=text,         # 设置文本信息
        # 如果传入了 stats 关键字参数，则用它们实例化 ToolStats；否则使用默认的 ToolStats()
        stats=ToolStats(**stats) if stats else ToolStats(),
    )


def partial(
    data: dict[str, Any] | None = None,
    text: str = "",
    error: ToolError | None = None,
    **stats,
) -> ToolResponse:
    """
    构建一个表示工具部分成功（部分失败）的响应对象。
    通常用于工具执行了部分操作但遇到了非致命错误的场景。
    
    参数:
        data (dict[str, Any] | None): 部分执行成功返回的数据字典。
        text (str): 附带的纯文本信息。
        error (ToolError | None): 可选的错误信息对象，用于记录部分失败的原因。
        **stats: 接收任意数量的关键字参数，用于动态构建 ToolStats。
        
    返回:
        ToolResponse: 状态为 "partial" 的统一响应对象。
    """
    return ToolResponse(
        status="partial",  # 设置状态为部分成功
        data=data or {},   # 如果 data 为 None，则回退使用空字典
        text=text,         # 设置文本信息
        error=error,       # 绑定错误对象（如果有）
        # 如果传入了 stats 关键字参数，则用它们实例化 ToolStats；否则使用默认的 ToolStats()
        stats=ToolStats(**stats) if stats else ToolStats(),
    )


def fail(code: str, message: str, details: dict[str, Any] | None = None) -> ToolResponse:
    """
    构建一个表示工具执行完全失败的响应对象。
    
    参数:
        code (str): 机器可读的错误码（如 NOT_FOUND / TIMEOUT）。
        message (str): 人类可读的错误描述。
        details (dict[str, Any] | None): 附加的错误详情字典，默认为 None。
        
    返回:
        ToolResponse: 状态为 "error" 的统一响应对象。
    """
    return ToolResponse(
        status="error",  # 设置状态为失败
        # 将错误码和错误信息拼接为文本，方便大模型或开发者快速查看
        text=f"[{code}] {message}",
        # 实例化 ToolError 对象，如果 details 为 None，则回退使用空字典
        error=ToolError(code=code, message=message, details=details or {}),
    )