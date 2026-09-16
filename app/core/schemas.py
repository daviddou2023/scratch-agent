"""
统一工具响应协议
"""

# 从 typing 模块导入 Any（表示任意类型）和 Literal（用于限定变量只能取特定的字面量值）
from typing import Any, Literal

# 从 pydantic 模块导入 BaseModel（数据模型基类）和 Field（用于提供字段的额外验证和元数据）
from pydantic import BaseModel, Field


# 使用 Literal 定义一个自定义类型别名 ToolStatus
# 限制状态值只能是 "success"、"partial" 或 "error" 这三个字符串之一，避免拼写错误
ToolStatus = Literal["success", "partial", "error"]


# 定义工具执行出错时的错误信息模型
class ToolError(BaseModel):
    # 机器可读的错误码（如 NOT_FOUND / TIMEOUT），... 表示该字段为必填项
    code: str = Field(..., description="机器可读错误码，如 NOT_FOUND / TIMEOUT")
    
    # 人类可读的错误描述，方便开发者或用户理解错误原因
    message: str = Field(..., description="人类可读错误描述")
    
    # 附加的错误详情字典，default_factory=dict 确保每个实例都有独立的新字典，避免引用共享问题
    details: dict[str, Any] = Field(default_factory=dict)


# 定义工具执行的统计信息模型
class ToolStats(BaseModel):
    # 工具执行耗时（毫秒），默认值为 0
    time_ms: int = 0
    
    # 其他扩展统计信息字典
    extra: dict[str, Any] = Field(default_factory=dict)


# 定义工具执行时的上下文信息模型
class ToolContext(BaseModel):
    # 当前工作目录（Current Working Directory），可选字段，默认为 None
    cwd: str | None = None
    
    # 工具接收到的原始输入参数字典
    params_input: dict[str, Any] = Field(default_factory=dict)


# 定义工具的统一响应模型，规范所有工具返回的数据结构
class ToolResponse(BaseModel):
    # 工具的执行状态，类型限定为前面定义的 ToolStatus
    status: ToolStatus
    
    # 工具执行成功后返回的核心数据字典
    data: dict[str, Any] = Field(default_factory=dict)
    
    # 工具返回的纯文本信息，默认为空字符串
    text: str = ""
    
    # 如果执行出错，包含具体的 ToolError 对象；正常时默认为 None
    error: ToolError | None = None
    
    # 包含耗时等统计信息的 ToolStats 对象，每次实例化时生成新对象
    stats: ToolStats = Field(default_factory=ToolStats)
    
    # 包含上下文信息的 ToolContext 对象，每次实例化时生成新对象
    context: ToolContext = Field(default_factory=ToolContext)

    def to_tool_message(self) -> str:
        """
        将响应对象转换为符合 OpenAI 规范的 tool 消息内容（JSON 字符串）。
        使用 exclude_none=True 参数，在序列化时自动忽略值为 None 的字段（例如正常情况下的 error 字段），
        从而减少传输给大模型的数据体积。
        """
        return self.model_dump_json(exclude_none=True)