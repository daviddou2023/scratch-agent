"""单变量对比实验。

设计原则（来自笔记第四章）：
1. 一次只改一个变量。
2. 跑同一批视频，对比指标。
3. 用 Trace 对比行为差异。
"""

import json
from pathlib import Path

from eval.dataset_loader import load_dataset, load_gold_labels
from eval.metrics import aggregate_scores, compute_overall
from eval.runner import run_dataset
from eval.schema import ExperimentConfig, ExperimentResult


EXPERIMENTS_DIR = Path("data/eval/experiments")


async def run_experiment(
    config: ExperimentConfig,
    baseline_prompt: str,
    candidate_prompt: str,
) -> ExperimentResult:
    """运行单变量对比实验。"""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset()
    labels = load_gold_labels()

    videos = dataset.videos
    if config.video_ids:
        videos = [v for v in videos if v.video_id in config.video_ids]

    print(f"\n=== 实验：{config.name} ===")
    print(f"变量：{config.variable}")
    print(f"基线：{config.baseline} vs 实验：{config.candidate}")
    print(f"视频数：{len(videos)}")

    baseline_results = await run_dataset(
        videos, labels.labels, tag=f"{config.name}_baseline"
    )
    candidate_results = await run_dataset(
        videos, labels.labels, tag=f"{config.name}_candidate"
    )

    baseline_scores = aggregate_scores(baseline_results)
    candidate_scores = aggregate_scores(candidate_results)

    delta = {
        k: candidate_scores.get(k, 0) - baseline_scores.get(k, 0)
        for k in baseline_scores
    }

    baseline_overall = compute_overall(baseline_scores)
    candidate_overall = compute_overall(candidate_scores)

    conclusion = _make_conclusion(
        config, baseline_overall, candidate_overall, delta
    )

    result = ExperimentResult(
        config=config,
        baseline_results=baseline_results,
        candidate_results=candidate_results,
        baseline_scores=baseline_scores,
        candidate_scores=candidate_scores,
        delta=delta,
        conclusion=conclusion,
    )

    out_path = EXPERIMENTS_DIR / f"{config.name}.json"
    out_path.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(f"\n[conclusion] {conclusion}")
    print(f"[saved] {out_path}")

    return result


def _make_conclusion(
    config: ExperimentConfig,
    baseline_overall: float,
    candidate_overall: float,
    delta: dict[str, float],
) -> str:
    """根据结果生成结论。"""
    diff = candidate_overall - baseline_overall

    if diff > 0.05:
        verdict = f"{config.candidate} 明显优于 {config.baseline}"
    elif diff > 0.01:
        verdict = f"{config.candidate} 略优于 {config.baseline}"
    elif diff < -0.05:
        verdict = f"{config.candidate} 明显差于 {config.baseline}"
    elif diff < -0.01:
        verdict = f"{config.candidate} 略差于 {config.baseline}"
    else:
        verdict = f"{config.candidate} 与 {config.baseline} 无显著差异"

    biggest_gain = max(delta.items(), key=lambda x: x[1]) if delta else ("", 0)
    biggest_loss = min(delta.items(), key=lambda x: x[1]) if delta else ("", 0)

    return (
        f"{verdict}（总分 {baseline_overall:.3f} → {candidate_overall:.3f}）。"
        f"最大提升：{biggest_gain[0]} {biggest_gain[1]:+.3f}；"
        f"最大下降：{biggest_loss[0]} {biggest_loss[1]:+.3f}。"
    )
