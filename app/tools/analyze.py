"""
中频受控层：评论洞察。

职责：调用 LLM，分析评论主题、情绪、高赞观点、观众问题。
输出结构化 JSON。

错误码：
- LLM_PARSE_ERROR：LLM 输出无法解析
"""

# 导入 json 模块（当前代码中暂未直接使用，但可用于更复杂的 JSON 处理）
import json

# 从 pydantic 导入 BaseModel 和 Field，用于定义工具入参和 LLM 输出的结构化数据
from pydantic import BaseModel, Field

# 导入项目中自定义的错误码枚举
from app.core.errors import ErrorCode
# 导入大语言模型客户端，用于调用 LLM 进行评论分析
from app.core.llm import LLMClient
# 导入统一的工具响应数据结构
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有自定义工具都需要继承它
from app.tools.base import Tool
# 导入封装好的标准响应辅助函数：成功(ok)、失败(fail)
from app.tools.response import fail, ok


class AnalyzeCommentsArgs(BaseModel):
    """
    定义 analyze_comments 工具的入参结构。
    """
    # 清洗后的评论列表，必填字段，每个评论是一个字典
    comments: list[dict] = Field(..., description="清洗后的评论列表")
    # 视频标题，默认为空字符串，用于为 LLM 提供额外的上下文信息
    video_title: str = Field("", description="视频标题，用于上下文")


class CommentInsight(BaseModel):
    """
    定义 LLM 分析评论后输出的结构化数据模型。
    用于强制校验 LLM 返回的 JSON 是否符合预期格式。
    """
    # 观众最关注的话题列表
    hot_topics: list[str] = Field(default_factory=list, description="观众最关注的话题")
    # 情绪分布字典，键为情绪类型（如"正面"），值为占比浮点数（0.0~1.0）
    emotions: dict[str, float] = Field(default_factory=dict, description="情绪分布")
    # 高赞观点列表，提取评论区内点赞较高的核心观点
    high_like_opinions: list[str] = Field(default_factory=list, description="高赞观点")
    # 观众问题列表，提取评论区中观众提出的疑问
    audience_questions: list[str] = Field(default_factory=list, description="观众问题")
    # 内容偏好提示列表，分析观众暗示想看的内容方向
    content_hints: list[str] = Field(default_factory=list, description="观众暗示的内容偏好")


class AnalyzeCommentsTool(Tool):
    """
    评论洞察工具类。
    继承自 Tool 基类，负责调用 LLM 对清洗后的评论进行深度分析，并输出结构化的洞察结果。
    """
    # 工具的唯一标识名称
    name = "analyze_comments"
    # 工具的功能描述
    description = "分析评论，输出观众兴趣、情绪、高赞观点和内容偏好。"
    # 绑定前面定义的入参校验模型
    args_schema = AnalyzeCommentsArgs

    def __init__(self, llm: LLMClient) -> None:
        """
        初始化方法，注入 LLM 客户端实例。
        因为该工具需要调用大模型，所以必须在构造时传入。
        """
        self.llm = llm

    async def run(self, comments: list[dict], video_title: str = "") -> ToolResponse:
        """
        执行评论分析的核心逻辑。
        
        参数:
            comments (list[dict]): 清洗后的评论列表。
            video_title (str): 视频标题，用于提供上下文。
            
        返回:
            ToolResponse: 封装了 LLM 分析结果的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 comments 是否确实是一个列表，且列表不为空
        # 如果没有可分析的评论，直接返回失败响应
        if not isinstance(comments, list) or len(comments) == 0:
            return fail(ErrorCode.EMPTY_COMMENTS, "没有可分析的评论")

        # --- 2. 构建 LLM 输入文本 ---
        # 将评论列表格式化为带点赞数的纯文本，方便 LLM 阅读和理解
        # 格式示例：- [100赞] 这条视频太棒了！
        comment_text = "\n".join(
            f"- [{c.get('likes', 0)}赞] {c.get('text', '')}" for c in comments
        )

        # --- 3. 构建 Prompt（提示词） ---
        # 使用 f-string 动态生成 Prompt，将视频标题和格式化后的评论列表填入
        prompt = f"""\
你是短视频评论分析专家。请分析以下评论，只输出 JSON。

视频标题：{video_title}

评论列表：
{comment_text}

输出 JSON 格式：
{{
  "hot_topics": ["观众最关注的话题"],
  "emotions": {{"正面": 0.6, "中性": 0.3, "负面": 0.1}},
  "high_like_opinions": ["高赞观点"],
  "audience_questions": ["观众问题"],
  "content_hints": ["观众暗示的内容偏好"]
}}

要求：
- 只基于评论内容，不要编造。
- 反讽、广告、水军评论不要当作真实反馈。
- 如果信息不足，对应字段返回空列表。
"""

        # --- 4. 调用 LLM 并解析结果 ---
        try:
            # 异步调用 LLM 客户端的 chat 方法
            response = await self.llm.chat(
                messages=[
                    # 系统提示词：强制要求 LLM 只输出 JSON，避免输出多余的废话
                    {"role": "system", "content": "你只输出 JSON，不要输出其他内容。"},
                    # 用户提示词：传入前面构建好的详细分析要求
                    {"role": "user", "content": prompt},
                ],
                tools=None,   # 本次调用不需要 LLM 使用工具
                step=0,       # 当前执行步数（用于链路追踪）
            )
            
            # 提取 LLM 返回的文本内容
            content = response.choices[0].message.content or ""
            
            # 数据清洗：去除首尾空白，并兼容 LLM 输出 Markdown 代码块（```json ... ```）的情况
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            
            # 使用 Pydantic 的 model_validate_json 方法，将 JSON 字符串解析并校验为 CommentInsight 对象
            # 如果 JSON 格式不对或缺少必填字段，这里会直接抛出异常
            insight = CommentInsight.model_validate_json(content)
            
        except Exception as e:
            # --- 5. 异常处理 ---
            # 如果 LLM 调用失败、返回内容不是合法 JSON、或字段校验不通过，捕获异常并返回失败响应
            # 同时附带前 500 个字符的原始返回内容，方便排查 LLM 到底输出了什么
            return fail(
                ErrorCode.LLM_PARSE_ERROR,
                f"评论分析失败：{e}",
                details={"raw": content[:500] if "content" in dir() else ""},
            )

        # --- 6. 返回成功结果 ---
        # 将 Pydantic 模型对象转为标准字典，并返回成功响应
        return ok(data=insight.model_dump(), text="评论分析完成")