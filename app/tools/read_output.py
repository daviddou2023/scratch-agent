"""
回查落盘的大输出。

当工具返回 status=partial 且 data.truncated=true 时，
模型可以用这个工具读取完整输出。
"""

# 导入 pathlib.Path，用于跨平台的文件路径操作
from pathlib import Path

# 导入 Pydantic 的 BaseModel 和 Field，用于定义参数校验模型
from pydantic import BaseModel, Field

# 导入项目配置，包含工具输出目录等设置
from app.core.config import settings
# 导入错误码枚举，用于统一错误类型
from app.core.errors import ErrorCode
# 导入工具响应的基础 Schema，定义返回格式
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有工具都需要继承它
from app.tools.base import Tool
# 导入 ok/fail 快捷响应函数，用于构建成功/失败的返回结果
from app.tools.response import fail, ok


# ==================== 参数校验模型 ====================

class ReadOutputArgs(BaseModel):
    """
    read_tool_output 工具的参数校验模型。
    
    使用 Pydantic 自动校验用户传入的参数格式和范围。
    """
    # 落盘文件的路径，必填字段
    # 例如 "tool-output/Grep_xxx.json"
    path: str = Field(
        ...,                                    # ... 表示必填
        description="落盘文件路径，例如 tool-output/Grep_xxx.json"
    )
    
    # 起始行号，可选字段，默认为 0（从头开始读）
    # ge=0 表示必须 >= 0
    offset: int = Field(
        0,                                      # 默认值为 0
        ge=0,                                   # 最小值为 0
        description="起始行号"
    )
    
    # 最多读取的行数，可选字段，默认为 200
    # ge=1 表示至少读 1 行，le=2000 表示最多读 2000 行
    limit: int = Field(
        200,                                    # 默认值为 200
        ge=1,                                   # 最小值为 1
        le=200,                                # 最大值可以自己设定
        description="最多读取行数"
    )


# ==================== 工具实现 ====================

class ReadOutputTool(Tool):
    """
    读取之前被截断落盘的完整工具输出。
    
    当某个工具的输出过大被截断后，LLM 可以调用此工具
    按需读取完整内容，避免一次性加载所有内容导致上下文爆炸。
    """
    # 工具名称：LLM 调用时使用的函数名
    name = "read_tool_output"
    
    # 工具描述：告诉 LLM 这个工具的作用和使用场景
    description = "读取之前被截断落盘的完整工具输出。"
    
    # 参数校验模型：LLM 调用时必须符合这个 Schema
    args_schema = ReadOutputArgs

    async def run(self, path: str, offset: int = 0, limit: int = 200) -> ToolResponse:
        """
        执行工具，读取落盘文件的内容。
        
        参数:
            path (str): 落盘文件的路径。
            offset (int): 起始行号，默认 0（从头开始）。
            limit (int): 最多读取的行数，默认 200，最大 2000。
            
        返回:
            ToolResponse: 工具响应，包含读取的内容和元信息。
        """
        # --- 1. 参数校验 ---
        # 检查 path 是否为空或只包含空白字符
        if not path.strip():
            return fail(ErrorCode.EMPTY_INPUT, "path 不能为空")

        # --- 2. 安全检查：防止目录穿越攻击 ---
        # 获取配置的工具输出目录的绝对路径
        base = Path(settings.tool_output_dir).resolve()
        # 获取用户传入路径的绝对路径
        target = Path(path).resolve()

        # 安全检查：只允许读取 tool_output_dir 目录下的文件
        # target.parents 是 target 的所有父目录集合
        # 如果 base 不在 target 的父目录中，且 target 不等于 base 本身，说明越权了
        if base not in target.parents and target != base:
            return fail(
                ErrorCode.INVALID_ARGUMENT,
                f"只能读取 {settings.tool_output_dir} 目录下的文件",
                details={"path": path},  # 附加错误详情，方便调试
            )

        # --- 3. 文件存在性检查 ---
        # 检查目标文件是否存在
        if not target.exists():
            return fail(ErrorCode.VIDEO_NOT_FOUND, f"文件不存在：{path}")

        # --- 4. 读取文件内容 ---
        # 读取文件的完整文本内容，按行分割
        lines = target.read_text(encoding="utf-8").splitlines()
        
        # 根据 offset 和 limit 切片，只读取指定范围的内容
        # 例如 offset=100, limit=200 → 读取第 100-299 行
        chunk = lines[offset : offset + limit]

        # --- 5. 返回结果 ---
        return ok(
            data={
                "path": str(target),                # 文件的绝对路径
                "offset": offset,                   # 本次读取的起始行号
                "limit": limit,                     # 本次读取的最大行数
                "total_lines": len(lines),           # 文件总行数（让 LLM 知道还有多少内容没读）
                "content": "\n".join(chunk),        # 读取到的内容（按行拼接为字符串）
            },
            text=f"已读取 {len(chunk)} 行（共 {len(lines)} 行）",  # 简短的可读描述
        )