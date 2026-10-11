"""评估报告生成：把结果转成人类可读的 Markdown。"""

import json
from pathlib import Path

from eval.metrics import aggregate_scores, compute_overall
from eval.schema import ExperimentResult, RunResult


REPORTS_DIR = Path("data/eval/reports")


def render_run_summary(results: list[RunResult], title: str) -> str:
    """生成单次运行的汇总报告。"""
    scores = aggregate_scores(results)
    overall = compute_overall(scores)

    lines = [
        f"# {title}",
        "",
        f"- 视频数：{len(results)}",
        f"- 成功：{sum(1 for r in results if r.success)}",
        f"- 失败：{sum(1 for r in results if not r.success)}",
        f"- 总分：{overall:.3f}",
        "",
        "## 指标明细",
        "",
        "| 指标 | 平均分 |",
        "|---|---|",
    ]
    for k, v in scores.items():
        lines.append(f"| {k} | {v:.3f} |")

    lines.append("")
    lines.append("## 逐条结果")
    lines.append("")
    lines.append("| video_id | 成功 | 步骤 | tokens | 总分 |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        overall_r = compute_overall(r.scores)
        lines.append(
            f"| {r.video_id} | {r.success} | {r.steps} | {r.total_tokens} | {overall_r:.3f} |"
        )

    return "\n".join(lines)


def render_experiment(result: ExperimentResult) -> str:
    """生成对比实验报告。"""
    lines = [
        f"# 实验：{result.config.name}",
        "",
        f"- 变量：{result.config.variable}",
        f"- 基线：{result.config.baseline}",
        f"- 实验：{result.config.candidate}",
        f"- 结论：{result.conclusion}",
        "",
        "## 指标对比",
        "",
        "| 指标 | 基线 | 实验 | Δ |",
        "|---|---|---|---|",
    ]
    for k in result.baseline_scores:
        b = result.baseline_scores.get(k, 0)
        c = result.candidate_scores.get(k, 0)
        d = result.delta.get(k, 0)
        lines.append(f"| {k} | {b:.3f} | {c:.3f} | {d:+.3f} |")

    return "\n".join(lines)


def save_report(content: str, name: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path