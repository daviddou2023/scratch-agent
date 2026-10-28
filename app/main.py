import asyncio
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.llm import LLMClient
from app.core.review_workflow import ReviewWorkflow
from app.observability.tracer import Tracer
from app.platforms.bilibili import BilibiliProvider, parse_bilibili_ref
from app.tools.analyze import AnalyzeCommentsTool
from app.tools.clean import CleanCommentsTool
from app.tools.comments import FetchCommentsTool
from app.tools.metrics import FetchVideoMetricsTool
from app.tools.report import GenerateReportTool, GenerateSuggestionsTool


REPORTS_DIR = Path("reports")


def _extract_video_id(user_input: str) -> str:
    match = re.search(r"\bvideo_[A-Za-z0-9_-]+\b", user_input)
    return match.group(0) if match else user_input.strip()


def _format_publish_date(value: object) -> str | None:
    if isinstance(value, (int, float)):
        shanghai = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(value, tz=shanghai).strftime("%Y-%m-%d")
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone(timedelta(hours=8)))
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            return value[:10]
    return None


def _save_markdown_report(markdown: str, metrics: dict) -> Path | None:
    video_id = metrics.get("video_id")
    publish_date = _format_publish_date(metrics.get("published_at"))
    if not video_id or not publish_date:
        return None
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{video_id}-{publish_date}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


async def run_once(user_input: str) -> None:
    tracer = Tracer()
    try:
        llm = LLMClient(tracer=tracer)
        video_ref = parse_bilibili_ref(user_input)
        video_id = (
            (video_ref.bvid or f"av{video_ref.aid}")
            if video_ref
            else _extract_video_id(user_input)
        )
        provider = BilibiliProvider() if video_ref else None
        workflow = ReviewWorkflow(
            metrics_tool=FetchVideoMetricsTool(provider),
            comments_tool=FetchCommentsTool(provider),
            clean_tool=CleanCommentsTool(),
            analyze_tool=AnalyzeCommentsTool(llm),
            report_tool=GenerateReportTool(llm),
            suggestions_tool=GenerateSuggestionsTool(llm),
            tracer=tracer,
        )
        result = await workflow.run(video_id)
        markdown = workflow.render_markdown(result)
        report_path = _save_markdown_report(markdown, result["metrics"])
        print("\n=== 最终回复 ===")
        print(markdown)
        if report_path:
            print(f"\n=== Markdown report saved ===\n{report_path}")
    finally:
        path = tracer.save()
        print("\n=== Trace 已保存 ===")
        print(path)
        print(f"run_id: {tracer.run_id}")


async def interactive() -> None:
    print("创作者助手已启动。输入内容，回车发送；输入 exit 退出。")
    while True:
        user_input = input("\n你：").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("再见。")
            break
        if user_input:
            await run_once(user_input)


def main() -> None:
    if len(sys.argv) > 1:
        asyncio.run(run_once(" ".join(sys.argv[1:])))
    else:
        asyncio.run(interactive())


if __name__ == "__main__":
    main()
