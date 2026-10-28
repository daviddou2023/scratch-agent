"""Deterministic orchestration for the creator video review workflow."""

import time
from typing import Any

from app.core.schemas import ToolResponse
from app.observability.tracer import Tracer
from app.tools.analyze import AnalyzeCommentsTool
from app.tools.clean import CleanCommentsTool
from app.tools.comments import FetchCommentsTool
from app.tools.metrics import FetchVideoMetricsTool
from app.tools.report import GenerateReportTool, GenerateSuggestionsTool


class ReviewWorkflow:
    """Run required review steps in a fixed order and retain structured results."""

    def __init__(
        self,
        metrics_tool: FetchVideoMetricsTool,
        comments_tool: FetchCommentsTool,
        clean_tool: CleanCommentsTool,
        analyze_tool: AnalyzeCommentsTool,
        report_tool: GenerateReportTool,
        suggestions_tool: GenerateSuggestionsTool,
        tracer: Tracer,
    ) -> None:
        self.metrics_tool = metrics_tool
        self.comments_tool = comments_tool
        self.clean_tool = clean_tool
        self.analyze_tool = analyze_tool
        self.report_tool = report_tool
        self.suggestions_tool = suggestions_tool
        self.tracer = tracer

    async def _run_tool(self, step: int, tool: Any, **kwargs: Any) -> ToolResponse:
        started = time.time()
        self.tracer.log_tool_call(step, tool.name, kwargs)
        try:
            response = await tool.run(**kwargs)
        except Exception as exc:
            payload = {
                "status": "error",
                "error": {"message": str(exc)},
                "data": {},
            }
            self.tracer.log_error(step, "tool_run", str(exc), {"tool": tool.name})
            self.tracer.log_tool_result(
                step, tool.name, payload, int((time.time() - started) * 1000)
            )
            raise

        result = response.model_dump(exclude_none=True)
        elapsed = int((time.time() - started) * 1000)
        self.tracer.log_tool_result(step, tool.name, result, elapsed)
        self.tracer.log_context(
            step,
            {"action": "workflow_step", "tool": tool.name, "status": response.status},
        )
        if response.status == "error":
            message = response.error.message if response.error else response.text
            raise RuntimeError(f"{tool.name} failed: {message}")
        return response

    async def run(self, video_id: str) -> dict[str, Any]:
        metrics_response = await self._run_tool(
            1, self.metrics_tool, video_id=video_id,
            platform="bilibili" if "bilibili.com" in video_id.lower() or video_id.lower().startswith(("bv", "av")) else "douyin",
        )
        metrics = metrics_response.data

        comments_response = await self._run_tool(
            2, self.comments_tool, video_id=video_id
        )
        raw_comments = comments_response.data.get("comments", [])
        fetched_comment_count = comments_response.data.get("total", len(raw_comments))

        clean_response = await self._run_tool(
            3, self.clean_tool, comments=raw_comments
        )
        cleaned_comments = clean_response.data.get("comments", [])
        clean_stats = clean_response.data.get("stats", {})

        insight: dict[str, Any] = {}
        if cleaned_comments:
            insight_response = await self._run_tool(
                4,
                self.analyze_tool,
                comments=cleaned_comments,
                video_title=metrics.get("title", ""),
            )
            insight = insight_response.data

        report_response = await self._run_tool(
            5, self.report_tool, metrics=metrics, comment_insight=insight
        )
        report = report_response.data

        suggestions_response = await self._run_tool(
            6,
            self.suggestions_tool,
            report=report,
            comment_insight=insight,
        )
        suggestions = suggestions_response.data.get("suggestions", [])
        result = {
            "metrics": metrics,
            "fetched_comment_count": fetched_comment_count,
            "cleaned_comment_count": clean_stats.get("cleaned", len(cleaned_comments)),
            "clean_stats": clean_stats,
            "comment_insight": insight,
            "report": report,
            "suggestions": suggestions,
        }
        self.tracer.log_final(self.render_markdown(result))
        return result

    @staticmethod
    def render_markdown(result: dict[str, Any]) -> str:
        report = result["report"]
        lines = [
            f"# {result['metrics'].get('title') or '视频复盘报告'}",
            "",
            "## 总结",
            report.get("summary", ""),
            "",
            "## 指标分析",
            report.get("metrics_analysis", ""),
            "",
            "## 评论分析",
            report.get("comment_analysis", ""),
            "",
            "## 优势",
        ]
        lines.extend(f"- {item}" for item in report.get("strengths", []))
        lines.extend(["", "## 待改进", *[f"- {item}" for item in report.get("weaknesses", [])]])
        lines.extend(["", "## 创作建议"])
        lines.extend(f"- {item}" for item in result.get("suggestions", []))
        lines.extend(["", "## 数据说明"])
        lines.extend(f"- 数据缺失：{item}" for item in report.get("data_gaps", []))
        lines.append(
            f"- 评论数：采集 {result['fetched_comment_count']} 条，清洗后有效 {result['cleaned_comment_count']} 条。"
        )
        return "\n".join(lines).rstrip() + "\n"
