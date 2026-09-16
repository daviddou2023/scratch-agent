"""高频原子层：评论采集。

职责：根据 video_id 返回原始评论列表。
MVP 阶段从 Mock 文件读取。

错误码：
- EMPTY_COMMENTS：评论为空（注意：这是 success，不是 error）
- VIDEO_NOT_FOUND：视频不存在
"""

# 导入 json 模块，用于解析本地 Mock 数据文件中的 JSON 内容
import json
# 从 pathlib 模块导入 Path 类，用于以面向对象的方式处理文件路径
from pathlib import Path

# 从 pydantic 导入 BaseModel 和 Field，用于定义和校验大模型传给工具的参数结构
from pydantic import BaseModel, Field

# 导入项目中自定义的错误码枚举
from app.core.errors import ErrorCode
# 导入统一的工具响应数据结构（通常基于 Pydantic 模型）
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有自定义工具都需要继承它
from app.tools.base import Tool
# 导入封装好的标准响应辅助函数：成功(ok)、失败(fail)
from app.tools.response import fail, ok

# 定义本地 Mock 评论数据文件的存储路径（指向 data/mock/comments.json）
MOCK_PATH = Path("data/mock/comments.json")


class FetchCommentsArgs(BaseModel):
    """
    定义 fetch_comments 工具的入参结构。
    大模型在调用该工具时，必须按照此结构生成参数。
    """
    # 视频 ID，必填字段（... 表示必填），并附带描述信息帮助大模型理解
    video_id: str = Field(..., description="视频 ID")
    # 最多返回的评论条数，默认为 500
    # ge=1 表示最小值为 1，le=2000 表示最大值为 2000（Pydantic 会自动拦截超出范围的请求）
    limit: int = Field(500, ge=1, le=2000, description="最多返回多少条评论")


class FetchCommentsTool(Tool):
    """
    获取视频评论列表的工具类。
    继承自 Tool 基类，通过读取本地 Mock 数据来模拟获取指定视频的原始评论。
    """
    # 工具的唯一标识名称，大模型将通过此名称来调用该工具
    name = "fetch_comments"
    # 工具的功能描述，大模型会根据此描述判断何时需要调用该工具
    description = "获取指定视频的评论列表，返回原始评论。"
    # 绑定前面定义的入参校验模型
    args_schema = FetchCommentsArgs

    async def run(self, video_id: str, limit: int = 500) -> ToolResponse:
        """
        执行工具的核心逻辑。
        
        参数:
            video_id (str): 要查询评论的视频 ID。
            limit (int): 最多返回的评论条数，默认 500。
            
        返回:
            ToolResponse: 封装了执行结果、状态码和提示信息的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 video_id 是否为空或纯空白字符，如果是则返回失败响应
        if not video_id.strip():
            return fail(ErrorCode.EMPTY_INPUT, "video_id 不能为空")

        # --- 2. Mock 文件存在性检查 ---
        # 检查本地 Mock 评论文件是否存在，如果不存在则返回未实现的错误
        if not MOCK_PATH.exists():
            return fail(ErrorCode.NOT_IMPLEMENTED, f"Mock 文件不存在：{MOCK_PATH}")

        # --- 3. 读取并查询数据 ---
        # 读取 Mock 文件的文本内容，并解析为 Python 字典
        data = json.loads(MOCK_PATH.read_text(encoding="utf-8"))
        # 根据传入的 video_id 尝试从字典中获取对应的评论列表
        comments = data.get(video_id)

        # 如果字典中不存在该 video_id，返回视频未找到的错误响应，并附带详细上下文
        if comments is None:
            return fail(
                ErrorCode.VIDEO_NOT_FOUND,
                f"未找到视频 {video_id} 的评论",
                details={"video_id": video_id},
            )

        # --- 4. 处理空评论列表（关键逻辑） ---
        # 如果该视频存在但评论列表为空，返回成功响应（而不是报错）
        # 因为"没有评论"是正常业务状态，不属于系统异常
        if len(comments) == 0:
            return ok(
                data={"comments": [], "total": 0},
                text=f"{video_id} 暂无评论",
            )

        # --- 5. 截取并返回结果 ---
        # 根据传入的 limit 参数，对评论列表进行切片截取
        comments = comments[:limit]
        # 返回成功响应，包含截取后的评论数据和总条数
        return ok(
            data={"comments": comments, "total": len(comments)},
            text=f"已获取 {len(comments)} 条评论",
        )