"""评估体系数据结构。

设计原则：
1. 评估集、标注、运行结果、指标、实验配置全部结构化。
2. 所有结果可 JSON 序列化，方便对比和归档。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---- 评估集 ----

class EvalComment(BaseModel):
    id: str
    user: str
    text: str
    likes: int = 0


class EvalVideo(BaseModel):
    video_id: str
    platform: str = "douyin"
    title: str = ""
    category: Literal["爆款", "普通", "扑街", "争议", "广告多"] = "普通"
    metrics: dict[str, Any] = Field(default_factory=dict)
    comments: list[EvalComment] = Field(default_factory=list)


class EvalDataset(BaseModel):
    version: str
    created_at: str
    videos: list[EvalVideo]


# ---- 人工标注 ----

class GoldLabel(BaseModel):
    hot_topics: list[str] = Field(default_factory=list)
    emotions: dict[str, float] = Field(default_factory=dict)
    high_like_opinions: list[str] = Field(default_factory=list)
    audience_questions: list[str] = Field(default_factory=list)
    valid_comment_count: int = 0
    should_filter_ads: int = 0
    expected_data_gaps: list[str] = Field(default_factory=list)


class GoldLabels(BaseModel):
    version: str
    labels: dict[str, GoldLabel]


# ---- 单次运行结果 ----

class RunResult(BaseModel):
    video_id: str
    run_id: str
    success: bool = True
    error: str | None = None

    # 采集层
    fetched_metrics: dict[str, Any] = Field(default_factory=dict)
    fetched_comment_count: int = 0
    cleaned_comment_count: int = 0

    # 分析层
    comment_insight: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)

    # 运行指标
    steps: int = 0
    total_tokens: int = 0
    elapsed_ms: int = 0

    # 评估结果（由 metrics.py 填充）
    scores: dict[str, float] = Field(default_factory=dict)


# ---- 实验配置 ----

class ExperimentConfig(BaseModel):
    name: str
    description: str = ""
    variable: str                      # 变量名，例如 "prompt_version"
    baseline: str                      # 基线值，例如 "v1"
    candidate: str                     # 实验值，例如 "v2"
    video_ids: list[str] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    config: ExperimentConfig
    baseline_results: list[RunResult] = Field(default_factory=list)
    candidate_results: list[RunResult] = Field(default_factory=list)
    baseline_scores: dict[str, float] = Field(default_factory=dict)
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    delta: dict[str, float] = Field(default_factory=dict)
    conclusion: str = ""