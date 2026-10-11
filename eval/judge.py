"""LLM 评审：用于规则难以计算的主观指标。

使用场景：
- 建议是否真正可执行
- 报告结论是否与数据一致
- 是否存在隐性幻觉

设计原则：
1. 评审 Prompt 固定，避免引入变量。
2. 输出结构化 JSON，便于聚合。
3. 与规则指标互补，不重复计算。
"""

import json

from pydantic import BaseModel, Field

from app.core.llm import LLMClient
from eval.schema import GoldLabel, RunResult


class JudgeScores(BaseModel):
    suggestion_actionable: float = Field(0.0, ge=0, le=1, description="建议可执行度")
    report_consistency: float = Field(0.0, ge=0, le=1, description="报告与数据一致性")
    implicit_hallucination: float = Field(0.0, ge=0, le=1, description="隐性幻觉程度")
    reason: str = ""


JUDGE_PROMPT = """\
你是短视频复盘评估专家。请对以下 Agent 输出打分，只输出 JSON。

视频指标：
{metrics}

评论洞察：
{insight}

流量报告：
{report}

创作建议：
{suggestions}

请从三个维度打分（0-1）：
1. suggestion_actionable：建议是否具体可执行。
   - 1.0：每条都有具体动作、对象、时机
   - 0.5：部分建议泛泛而谈
   - 0.0：全是“优化内容”“加强互动”这类空话

2. report_consistency：报告结论是否与数据一致。
   - 1.0：所有结论都有数据支撑
   - 0.5：部分结论缺少依据
   - 0.0：结论与数据矛盾

3. implicit_hallucination：隐性幻觉程度（越低越好）。
   - 0.0：没有编造
   - 1.0：大量编造数据或观点

输出 JSON：
{{
  "suggestion_actionable": 0.0,
  "report_consistency": 0.0,
  "implicit_hallucination": 0.0,
  "reason": "简短说明"
}}
"""


async def judge_run(
    result: RunResult,
    gold: GoldLabel,
    llm: LLMClient,
) -> JudgeScores:
    """对单条运行结果做 LLM 评审。"""
    prompt = JUDGE_PROMPT.format(
        metrics=json.dumps(result.fetched_metrics, ensure_ascii=False),
        insight=json.dumps(result.comment_insight, ensure_ascii=False),
        report=json.dumps(result.report, ensure_ascii=False),
        suggestions=json.dumps(result.suggestions, ensure_ascii=False),
    )

    try:
        response = await llm.chat(
            messages=[
                {"role": "system", "content": "你只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            tools=None,
            step=0,
        )
        content = response.choices[0].message.content or ""
        content = content.strip().removeprefix("```json").removesuffix("```").strip()
        return JudgeScores.model_validate_json(content)
    except Exception as e:
        return JudgeScores(reason=f"评审失败：{e}")