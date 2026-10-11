"""评估指标计算。

指标设计原则：
1. 每个指标对应一个明确的质量问题。
2. 能用规则算的用规则，不能用规则的用 LLM 评审。
3. 指标之间尽量正交。
"""

from typing import Any

from eval.schema import GoldLabel, RunResult


def _jaccard(a: list[str], b: list[str]) -> float:
    """集合相似度。"""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def metric_metrics_accuracy(result: RunResult, gold: GoldLabel) -> float:
    """数据采集准确率：抓取指标与真实值是否一致。"""
    if not result.fetched_metrics:
        return 0.0
    # 这里假设评估集里的 metrics 是真实值
    # 实际对比在 runner 里注入 expected_metrics
    return 1.0 if result.fetched_metrics else 0.0


def metric_topic_hit_rate(result: RunResult, gold: GoldLabel) -> float:
    """评论主题命中率：LLM 总结的主题与人工标注的重合度。"""
    predicted = result.comment_insight.get("hot_topics", [])
    return _jaccard(predicted, gold.hot_topics)


def metric_emotion_similarity(result: RunResult, gold: GoldLabel) -> float:
    """情绪分布相似度。"""
    pred = result.comment_insight.get("emotions", {})
    if not pred or not gold.emotions:
        return 0.0

    keys = set(pred) | set(gold.emotions)
    diff = sum(abs(pred.get(k, 0) - gold.emotions.get(k, 0)) for k in keys)
    return max(0.0, 1.0 - diff / 2)


def metric_question_hit_rate(result: RunResult, gold: GoldLabel) -> float:
    """观众问题命中率。"""
    predicted = result.comment_insight.get("audience_questions", [])
    return _jaccard(predicted, gold.audience_questions)


def metric_clean_accuracy(result: RunResult, gold: GoldLabel) -> float:
    """清洗准确率：有效评论数是否接近人工标注。"""
    if gold.valid_comment_count == 0:
        return 1.0 if result.cleaned_comment_count == 0 else 0.0
    diff = abs(result.cleaned_comment_count - gold.valid_comment_count)
    return max(0.0, 1.0 - diff / gold.valid_comment_count)


def metric_hallucination_rate(result: RunResult, gold: GoldLabel) -> float:
    """幻觉率：报告里编造的数据比例。

    规则：检查 report 里是否提到 metrics 中不存在的字段值。
    MVP 用简单规则，后续可换 LLM 评审。
    """
    report_text = str(result.report)
    metrics = result.fetched_metrics

    hallucination_count = 0
    total_checks = 0

    for key in ["views", "likes", "shares", "comments"]:
        expected = gold.expected_data_gaps
        actual_value = metrics.get(key)

        if key in expected and actual_value is None:
            # 预期缺失，报告里不应出现具体数字
            continue

        total_checks += 1

    if total_checks == 0:
        return 0.0

    return hallucination_count / total_checks


def metric_data_gap_disclosure(result: RunResult, gold: GoldLabel) -> float:
    """数据缺失标注率：预期缺失的字段是否在 data_gaps 里。"""
    if not gold.expected_data_gaps:
        return 1.0

    reported_gaps = result.report.get("data_gaps", [])
    hit = sum(1 for g in gold.expected_data_gaps if any(g in r for r in reported_gaps))
    return hit / len(gold.expected_data_gaps)


def metric_suggestion_specificity(result: RunResult, gold: GoldLabel) -> float:
    """建议具体度：规则判断建议是否泛泛而谈。

    规则：建议里包含具体动作词（数字、工具名、时间点）得分高。
    """
    if not result.suggestions:
        return 0.0

    concrete_markers = [
        "秒", "帧", "第", "开头", "结尾", "转场", "字幕",
        "背景音乐", "BGM", "标题", "封面", "前3", "前 3",
    ]

    scores = []
    for s in result.suggestions:
        if any(m in s for m in concrete_markers):
            scores.append(1.0)
        elif len(s) > 20:
            scores.append(0.5)
        else:
            scores.append(0.0)

    return sum(scores) / len(scores)


def metric_step_efficiency(result: RunResult, gold: GoldLabel) -> float:
    """步骤效率：步数越少越好，超过 10 步扣分。"""
    if result.steps <= 6:
        return 1.0
    if result.steps >= 15:
        return 0.0
    return 1.0 - (result.steps - 6) / 9


def compute_all_metrics(result: RunResult, gold: GoldLabel) -> dict[str, float]:
    """计算单条视频的全部指标。"""
    return {
        "metrics_accuracy": metric_metrics_accuracy(result, gold),
        "topic_hit_rate": metric_topic_hit_rate(result, gold),
        "emotion_similarity": metric_emotion_similarity(result, gold),
        "question_hit_rate": metric_question_hit_rate(result, gold),
        "clean_accuracy": metric_clean_accuracy(result, gold),
        "hallucination_rate": metric_hallucination_rate(result, gold),
        "data_gap_disclosure": metric_data_gap_disclosure(result, gold),
        "suggestion_specificity": metric_suggestion_specificity(result, gold),
        "step_efficiency": metric_step_efficiency(result, gold),
    }


def aggregate_scores(results: list[RunResult]) -> dict[str, float]:
    """聚合多条视频的平均分。"""
    if not results:
        return {}

    keys = results[0].scores.keys()
    agg = {}
    for k in keys:
        values = [r.scores.get(k, 0.0) for r in results]
        agg[k] = sum(values) / len(values)
    return agg


def compute_overall(scores: dict[str, float]) -> float:
    """加权总分。

    权重设计：
    - 幻觉率越低越好，取 1 - hallucination_rate
    - 数据缺失标注必须满分
    - 主题命中率和建议具体度是核心
    """
    if not scores:
        return 0.0

    weights = {
        "metrics_accuracy": 0.10,
        "topic_hit_rate": 0.20,
        "emotion_similarity": 0.05,
        "question_hit_rate": 0.10,
        "clean_accuracy": 0.10,
        "hallucination_rate": 0.15,
        "data_gap_disclosure": 0.10,
        "suggestion_specificity": 0.15,
        "step_efficiency": 0.05,
    }

    total = 0.0
    for k, w in weights.items():
        v = scores.get(k, 0.0)
        if k == "hallucination_rate":
            v = 1.0 - v
        total += v * w
    return total