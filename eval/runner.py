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

from app.core.context_builder import ContextBuilder
from app.core.llm import LLMClient
from app.core.runtime import AgentRuntime
from app.core.summarizer import Summarizer
from app.core.todo import TodoList
from app.observability.tracer import Tracer
from app.prompts.system_prompt import build_l1_system_prompt
from app.tools.analyze import AnalyzeCommentsTool
from app.tools.clean import CleanCommentsTool
from app.tools.comments import FetchCommentsTool
from app.tools.metrics import FetchVideoMetricsTool
from app.tools.read_output import ReadOutputTool
from app.tools.registry import ToolRegistry
from app.tools.report import GenerateReportTool, GenerateSuggestionsTool

from eval.metrics import compute_all_metrics
from eval.schema import EvalVideo, GoldLabel, RunResult


RUNS_DIR = Path("data/eval/runs")


def build_registry(llm: LLMClient) -> ToolRegistry:
    """构建评估用的工具注册表。

    注意：评估时不注册 Bash 和 Echo，只保留创作者助手核心工具。
    """
    registry = ToolRegistry()
    registry.register(FetchVideoMetricsTool())
    registry.register(FetchCommentsTool())
    registry.register(CleanCommentsTool())
    registry.register(AnalyzeCommentsTool(llm))
    registry.register(GenerateReportTool(llm))
    registry.register(GenerateSuggestionsTool(llm))
    registry.register(ReadOutputTool())
    return registry


def build_todo() -> TodoList:
    todo = TodoList()
    todo.add("采集视频指标")
    todo.add("采集评论")
    todo.add("清洗评论")
    todo.add("分析评论")
    todo.add("生成流量报告")
    todo.add("生成创作建议")
    return todo


async def run_one_video(
    video: EvalVideo,
    gold: GoldLabel,
    llm: LLMClient,
    system_prompt: str,
) -> RunResult:
    """运行单条视频，返回结构化结果。"""
    tracer = Tracer()
    registry = build_registry(llm)

    context = ContextBuilder(l1_system_prompt=system_prompt, l2_code_law_path=None)
    context.todo = build_todo()

    summarizer = Summarizer(llm=llm)

    runtime = AgentRuntime(
        llm=llm,
        tools=registry,
        tracer=tracer,
        context=context,
        summarizer=summarizer,
        max_steps=12,
    )

    user_input = f"请复盘视频 {video.video_id}，标题：{video.title}"

    t0 = time.time()
    result = RunResult(video_id=video.video_id, run_id=tracer.run_id)

    try:
        await runtime.run(user_input)
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

    # 从 Trace 里提取中间结果
    for event in tracer.events:
        if event["event"] != "tool_result":
            continue
        tool = event["payload"].get("tool")
        # 从 context 的 L3 里拿工具返回内容更准确
        # MVP 简化：直接扫 context.l3
    for msg in context.l3:
        if msg.get("role") != "tool":
            continue
        try:
            payload = json.loads(msg.get("content", "{}"))
        except json.JSONDecodeError:
            continue
        data = payload.get("data", {})
        if "comments" in data and "total" in data:
            result.fetched_comment_count = data.get("total", 0)
            if "stats" in data:
                result.cleaned_comment_count = data["stats"].get("cleaned", 0)
        if "views" in data or "likes" in data:
            result.fetched_metrics = data
        if "hot_topics" in data:
            result.comment_insight = data
        if "summary" in data:
            result.report = data
        if "suggestions" in data:
            result.suggestions = data["suggestions"]

    result.scores = compute_all_metrics(result, gold)

    tracer.save()
    return result


async def run_dataset(
    videos: list[EvalVideo],
    labels: dict[str, GoldLabel],
    system_prompt: str,
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
        result = await run_one_video(video, gold, llm, system_prompt)
        results.append(result)

    out_path = RUNS_DIR / f"{tag}.json"
    out_path.write_text(
        json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[saved] {out_path}")
    return results