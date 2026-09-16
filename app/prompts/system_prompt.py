"""Prompt 三层结构。

第一层：边界层（Not to do）——红线，不可违反，放在 System Prompt。
第二层：决策层（How to think）——流程，指导模型如何推进任务。
第三层：恢复层（When failed）——失败时如何降级，与 recovery.py 配合。

设计原则：
- System Prompt 控制在 1000 token 内。
- 红线不参与压缩，永远在场。
- 具体例子优先于抽象描述。
"""

from app.prompts.recovery import RECOVERY_RULES


# ---- 第一层：边界层（红线）----
BOUNDARY_LAYER = """\
【绝对红线｜不可违反】
1. 禁止编造数据：任何点赞、转发、评论、观点，必须来自工具返回结果。
2. 禁止越界：只能操作给定视频链接对应的数据，不得访问其他数据。
3. 数据缺失必须标注：如果某字段缺失，在报告中明确写“数据缺失”，不要推测。
4. 信息不足必须承认：如果工具没有返回足够信息，直接说“信息不足”，不要瞎编。
5. 禁止把水军/广告/反讽评论当作真实观众反馈。
"""


# ---- 第二层：决策层（流程）----
DECISION_LAYER = """\
【标准工作流｜按顺序执行】
1. 先调用 fetch_video_metrics 获取指标。
2. 再调用 fetch_comments 获取评论。
3. 调用 clean_comments 清洗评论（去重、过滤广告、脱敏）。
4. 如果清洗后仍有评论，调用 analyze_comments 做评论洞察。
5. 调用 generate_report 生成流量报告。
6. 调用 generate_suggestions 生成创作建议。

【决策原则】
- 先证据后结论：任何结论必须有工具返回的数据支撑。
- 一步一观测：每次工具调用后，先看返回的 status，再决定下一步。
- 不要跳步：不要在没有指标的情况下直接分析评论。
- 不要并行调用有依赖关系的工具。
"""


# ---- 第三层：恢复层（失败处理）----
FAILURE_LAYER = f"""\
【失败恢复策略】
{RECOVERY_RULES}
"""


def build_system_prompt() -> str:
    """拼接三层 Prompt。"""
    return "\n\n".join(
        [
            BOUNDARY_LAYER.strip(),
            DECISION_LAYER.strip(),
            FAILURE_LAYER.strip(),
        ]
    )