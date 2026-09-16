"""
中频受控层：流量报告与创作建议。

职责：
1. generate_report：基于指标 + 评论洞察，生成流量报告。
2. generate_suggestions：基于报告，生成创作建议。

错误码：
- MISSING_METRICS：指标缺失
- LLM_PARSE_ERROR：LLM 输出无法解析
"""

# 导入 json 模块，用于将字典数据格式化为 JSON 字符串，方便传入 LLM Prompt
import json

# 从 pydantic 导入 BaseModel 和 Field，用于定义工具入参和 LLM 输出的结构化数据
from pydantic import BaseModel, Field

# 导入项目中自定义的错误码枚举
from app.core.errors import ErrorCode
# 导入大语言模型客户端，用于调用 LLM 生成报告和建议
from app.core.llm import LLMClient
# 导入统一的工具响应数据结构
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有自定义工具都需要继承它
from app.tools.base import Tool
# 导入封装好的标准响应辅助函数：成功(ok)、失败(fail)
from app.tools.response import fail, ok


# ==================== 工具 1：生成流量报告 ====================

class GenerateReportArgs(BaseModel):
    """
    定义 generate_report 工具的入参结构。
    """
    # 视频指标字典（如播放量、点赞量、分享量等），必填字段
    metrics: dict = Field(..., description="视频指标")
    # 评论洞察字典（由上一个工具 AnalyzeCommentsTool 输出），默认为空字典
    comment_insight: dict = Field(default_factory=dict, description="评论洞察")


class TrafficReport(BaseModel):
    """
    定义 LLM 生成流量报告后输出的结构化数据模型。
    用于强制校验 LLM 返回的 JSON 是否符合预期格式。
    """
    # 对视频流量表现的一句话总结
    summary: str = Field(..., description="一句话总结")
    # 对各项核心指标（播放、点赞、分享等）的深度分析
    metrics_analysis: str = Field(..., description="指标分析")
    # 对评论区观众反馈的深度分析
    comment_analysis: str = Field(..., description="评论分析")
    # 视频做得好的地方（优点列表）
    strengths: list[str] = Field(default_factory=list, description="做得好的地方")
    # 视频需要改进的地方（缺点列表）
    weaknesses: list[str] = Field(default_factory=list, description="需要改进的地方")
    # 缺失的数据字段列表（用于记录哪些关键指标没有提供）
    data_gaps: list[str] = Field(default_factory=list, description="数据缺失项")


class GenerateReportTool(Tool):
    """
    流量报告生成工具类。
    继承自 Tool 基类，负责调用 LLM 基于视频指标和评论洞察，生成结构化的流量复盘报告。
    """
    # 工具的唯一标识名称
    name = "generate_report"
    # 工具的功能描述
    description = "基于指标和评论洞察，生成视频流量报告。"
    # 绑定前面定义的入参校验模型
    args_schema = GenerateReportArgs

    def __init__(self, llm: LLMClient) -> None:
        """
        初始化方法，注入 LLM 客户端实例。
        """
        self.llm = llm

    async def run(self, metrics: dict, comment_insight: dict | None = None) -> ToolResponse:
        """
        执行流量报告生成的核心逻辑。
        
        参数:
            metrics (dict): 视频指标数据。
            comment_insight (dict | None): 评论洞察数据，可选。
            
        返回:
            ToolResponse: 封装了流量报告的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 metrics 是否确实是一个字典，且字典不为空
        # 如果没有指标数据，直接返回失败响应
        if not isinstance(metrics, dict) or not metrics:
            return fail(ErrorCode.MISSING_METRICS, "缺少指标数据")

        # --- 2. 检查缺失的核心指标字段 ---
        # 定义必须存在的核心指标字段
        required = ["views", "likes", "shares", "comments"]
        # 找出 metrics 字典中缺失的字段，生成缺失列表
        missing = [k for k in required if metrics.get(k) is None]

        # --- 3. 构建 Prompt（提示词） ---
        # 使用 f-string 和 json.dumps 动态生成 Prompt，将指标和评论洞察以格式化的 JSON 字符串填入
        prompt = f"""\
你是短视频流量复盘专家。请基于以下数据生成流量报告，只输出 JSON。

视频指标：
{json.dumps(metrics, ensure_ascii=False, indent=2)}

评论洞察：
{json.dumps(comment_insight or {}, ensure_ascii=False, indent=2)}

缺失字段：{missing}

输出 JSON 格式：
{{
  "summary": "一句话总结",
  "metrics_analysis": "指标分析",
  "comment_analysis": "评论分析",
  "strengths": ["做得好的地方"],
  "weaknesses": ["需要改进的地方"],
  "data_gaps": ["数据缺失项"]
}}

要求：
- 禁止编造数据。缺失字段必须写入 data_gaps。
- 所有结论必须基于给定数据。
- 不要给出泛泛而谈的建议。
"""

        # --- 4. 调用 LLM 并解析结果 ---
        try:
            # 异步调用 LLM 客户端的 chat 方法
            response = await self.llm.chat(
                messages=[
                    # 系统提示词：强制要求 LLM 只输出 JSON
                    {"role": "system", "content": "你只输出 JSON，不要输出其他内容。"},
                    # 用户提示词：传入前面构建好的详细报告生成要求
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                step=0,
            )
            
            # 提取 LLM 返回的文本内容
            content = response.choices[0].message.content or ""
            
            # 数据清洗：去除首尾空白，并兼容 LLM 输出 Markdown 代码块的情况
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            
            # 使用 Pydantic 强校验，将 JSON 字符串解析为 TrafficReport 对象
            report = TrafficReport.model_validate_json(content)
            
        except Exception as e:
            # --- 5. 异常处理 ---
            # 如果 LLM 调用失败或返回内容无法解析，捕获异常并返回失败响应
            return fail(ErrorCode.LLM_PARSE_ERROR, f"报告生成失败：{e}")

        # --- 6. 返回成功结果 ---
        # 将 Pydantic 模型对象转为标准字典，并返回成功响应
        return ok(data=report.model_dump(), text="流量报告生成完成")


# ==================== 工具 2：生成创作建议 ====================

class GenerateSuggestionsArgs(BaseModel):
    """
    定义 generate_suggestions 工具的入参结构。
    """
    # 流量报告字典（由上一个工具 GenerateReportTool 输出），必填字段
    report: dict = Field(..., description="流量报告")
    # 评论洞察字典，默认为空字典，用于提供额外的观众反馈上下文
    comment_insight: dict = Field(default_factory=dict, description="评论洞察")


class SuggestionList(BaseModel):
    """
    定义 LLM 生成创作建议后输出的结构化数据模型。
    """
    # 具体的创作建议列表
    suggestions: list[str] = Field(default_factory=list, description="创作建议")


class GenerateSuggestionsTool(Tool):
    """
    创作建议生成工具类。
    继承自 Tool 基类，负责调用 LLM 基于流量报告，生成下一条视频的可执行创作建议。
    """
    # 工具的唯一标识名称
    name = "generate_suggestions"
    # 工具的功能描述
    description = "基于流量报告，生成下一条视频的创作建议。"
    # 绑定前面定义的入参校验模型
    args_schema = GenerateSuggestionsArgs

    def __init__(self, llm: LLMClient) -> None:
        """
        初始化方法，注入 LLM 客户端实例。
        """
        self.llm = llm

    async def run(self, report: dict, comment_insight: dict | None = None) -> ToolResponse:
        """
        执行创作建议生成的核心逻辑。
        
        参数:
            report (dict): 流量报告数据。
            comment_insight (dict | None): 评论洞察数据，可选。
            
        返回:
            ToolResponse: 封装了创作建议列表的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 report 是否确实是一个字典，且字典不为空
        # 如果没有报告数据，直接返回参数错误
        if not isinstance(report, dict) or not report:
            return fail(ErrorCode.INVALID_ARGUMENT, "缺少报告数据")

        # --- 2. 构建 Prompt（提示词） ---
        prompt = f"""\
你是短视频创作顾问。请基于以下报告，给出 3 条可执行的创作建议，只输出 JSON。

流量报告：
{json.dumps(report, ensure_ascii=False, indent=2)}

评论洞察：
{json.dumps(comment_insight or {}, ensure_ascii=False, indent=2)}

输出 JSON 格式：
{{
  "suggestions": ["建议1", "建议2", "建议3"]
}}

要求：
- 每条建议必须具体、可执行。
- 禁止泛泛而谈，例如“优化开头”不算建议，“前 3 秒直接展示结果画面”才算。
- 建议必须基于报告中的证据。
"""

        # --- 3. 调用 LLM 并解析结果 ---
        try:
            # 异步调用 LLM 客户端的 chat 方法
            response = await self.llm.chat(
                messages=[
                    # 系统提示词：强制要求 LLM 只输出 JSON
                    {"role": "system", "content": "你只输出 JSON，不要输出其他内容。"},
                    # 用户提示词：传入前面构建好的详细建议生成要求
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                step=0,
            )
            
            # 提取 LLM 返回的文本内容
            content = response.choices[0].message.content or ""
            
            # 数据清洗：去除首尾空白，并兼容 LLM 输出 Markdown 代码块的情况
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            
            # 使用 Pydantic 强校验，将 JSON 字符串解析为 SuggestionList 对象
            result = SuggestionList.model_validate_json(content)
            
        except Exception as e:
            # --- 4. 异常处理 ---
            # 如果 LLM 调用失败或返回内容无法解析，捕获异常并返回失败响应
            return fail(ErrorCode.LLM_PARSE_ERROR, f"建议生成失败：{e}")

        # --- 5. 返回成功结果 ---
        # 将 Pydantic 模型对象转为标准字典，并返回成功响应
        return ok(data=result.model_dump(), text="创作建议生成完成")