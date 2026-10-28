"""批量运行 Agent，产出 RunResult。

设计原则：
1. 每条视频独立运行，互不污染。
2. 复用生产环境的 Runtime / ContextBuilder / ToolRegistry。
3. 结果落盘到 data/eval/runs/。
"""

import asyncio
import json
import time
from pathlib import Path

from app.core.llm import LLMClient
from app.core.review_workflow import ReviewWorkflow
from app.observability.tracer import Tracer
from app.tools.analyze import AnalyzeCommentsTool
from app.tools.clean import CleanCommentsTool
from app.tools.comments import FetchCommentsTool
from app.tools.metrics import FetchVideoMetricsTool
from app.tools.report import GenerateReportTool, GenerateSuggestionsTool

from eval.metrics import compute_all_metrics
from eval.schema import EvalVideo, GoldLabel, RunResult


RUNS_DIR = Path("data/eval/runs")


async def run_one_video(
    video: EvalVideo,
    gold: GoldLabel,
    llm: LLMClient,
    system_prompt: str | None = None,
) -> RunResult:
    """运行单条视频，返回结构化结果。"""
    tracer = Tracer()
    workflow = ReviewWorkflow(
        metrics_tool=FetchVideoMetricsTool(),
        comments_tool=FetchCommentsTool(),
        clean_tool=CleanCommentsTool(),
        analyze_tool=AnalyzeCommentsTool(llm),
        report_tool=GenerateReportTool(llm),
        suggestions_tool=GenerateSuggestionsTool(llm),
        tracer=tracer,
    )

    t0 = time.time()
    result = RunResult(video_id=video.video_id, run_id=tracer.run_id)

    try:
        workflow_result = await workflow.run(video.video_id)
        result.fetched_metrics = workflow_result["metrics"]
        result.fetched_comment_count = workflow_result["fetched_comment_count"]
        result.cleaned_comment_count = workflow_result["cleaned_comment_count"]
        result.comment_insight = workflow_result["comment_insight"]
        result.report = workflow_result["report"]
        result.suggestions = workflow_result["suggestions"]
    except Exception as e:
        result.success = False
        result.error = str(e)
    finally:
        result.elapsed_ms = int((time.time() - t0) * 1000)
        result.steps = len([e for e in tracer.events if e["event"] == "llm_response"])
        total_tokens = sum(
            e["payload"].get("usage", {}).get("total_tokens", 0)
            for e in tracer.events
            if e["event"] == "llm_response"
        )
        result.total_tokens = total_tokens

    result.scores = compute_all_metrics(result, gold)

    tracer.save()
    return result


async def run_dataset(
    videos: list[EvalVideo],
    labels: dict[str, GoldLabel],
    system_prompt: str | None = None,
    tag: str = "baseline",
) -> list[RunResult]:
    """批量运行评估集，结果落盘。"""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    llm = LLMClient(tracer=None)

    results: list[RunResult] = []
    for video in videos:
        gold = labels.get(video.video_id)
        if gold is None:
            print(f"[skip] {video.video_id} 缺少标注")
            continue

        print(f"[run] {video.video_id} ...")
        result = await run_one_video(video, gold, llm)
        results.append(result)

    out_path = RUNS_DIR / f"{tag}.json"
    out_path.write_text(
        json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[saved] {out_path}")
    return results
