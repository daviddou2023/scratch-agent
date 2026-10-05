"""高频原子层：视频指标采集。

职责：根据 video_id 返回点赞、转发、评论等指标。
MVP 阶段从 Mock 文件读取；后续可替换为真实 API。

错误码：
- VIDEO_NOT_FOUND：视频不存在
- MISSING_METRICS：部分字段缺失
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
# 导入封装好的三种标准响应辅助函数：成功(ok)、失败(fail)、部分成功(partial)
from app.tools.response import fail, ok, partial

# 定义本地 Mock 数据文件的存储路径（指向 data/mock/video_metrics.json）
MOCK_PATH = Path("data/mock/video_metrics.json")


class FetchMetricsArgs(BaseModel):
    """
    定义 fetch_video_metrics 工具的入参结构。
    大模型在调用该工具时，必须按照此结构生成参数。
    """
    # 视频 ID，必填字段（... 表示必填），并附带描述信息帮助大模型理解
    video_id: str = Field(..., description="视频 ID，例如 video_001")
    # 平台名称，默认为 "douyin"（抖音），同样附带描述信息
    platform: str = Field("douyin", description="平台，例如 douyin / bilibili")


class FetchVideoMetricsTool(Tool):
    """
    获取视频指标的工具类。
    继承自 Tool 基类，通过读取本地 Mock 数据来模拟获取视频的点赞、转发等指标。
    """
    # 工具的唯一标识名称，大模型将通过此名称来调用该工具
    name = "fetch_video_metrics"
    # 工具的功能描述，大模型会根据此描述判断何时需要调用该工具
    description = "获取指定视频的点赞、转发、评论、播放量等指标。大输出会自动截断落盘，可用 read_tool_output 回查。"
    # 绑定前面定义的入参校验模型
    args_schema = FetchMetricsArgs

    async def run(self, video_id: str, platform: str = "douyin") -> ToolResponse:
        """
        执行工具的核心逻辑。
        
        参数:
            video_id (str): 要查询的视频 ID。
            platform (str): 视频所属平台（当前 Mock 实现中暂未实际使用，仅作预留）。
            
        返回:
            ToolResponse: 封装了执行结果、状态码和提示信息的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 video_id 是否为空或纯空白字符，如果是则返回失败响应
        if not video_id.strip():
            return fail(ErrorCode.EMPTY_INPUT, "video_id 不能为空")

        # --- 2. Mock 文件存在性检查 ---
        # 检查本地 Mock 数据文件是否存在，如果不存在则返回未实现的错误
        if not MOCK_PATH.exists():
            return fail(ErrorCode.NOT_IMPLEMENTED, f"Mock 文件不存在：{MOCK_PATH}")

        # --- 3. 读取并查询数据 ---
        # 读取 Mock 文件的文本内容，并解析为 Python 字典
        data = json.loads(MOCK_PATH.read_text(encoding="utf-8"))
        # 根据传入的 video_id 尝试从字典中获取对应的视频数据
        item = data.get(video_id)

        # 如果字典中不存在该 video_id，返回视频未找到的错误响应，并附带详细上下文
        if item is None:
            return fail(
                ErrorCode.VIDEO_NOT_FOUND,
                f"未找到视频 {video_id}",
                details={"video_id": video_id},
            )

        # --- 4. 数据完整性校验 ---
        # 定义获取视频指标所必需的字段列表
        required = ["views", "likes", "shares", "comments"]
        # 使用列表推导式，找出 item 中缺失（值为 None）的必需字段
        missing = [k for k in required if item.get(k) is None]

        # 如果存在缺失的字段，返回部分成功（partial）响应
        # 告知上层（或大模型）数据不完整，但依然返回已有的数据
        if missing:
            return partial(
                data=item,
                text=f"指标部分缺失：{missing}",
                error=None,
            )

        # --- 5. 返回成功结果 ---
        # 如果所有必需字段都齐全，返回成功（ok）响应，包含完整的指标数据
        return ok(data=item, text=f"已获取 {video_id} 的指标")