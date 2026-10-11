"""Prompt 变体注册。

用于单变量实验：同一个 Prompt，只改一个点，注册为新版本。
"""

from app.prompts.system_prompt import build_l1_system_prompt


def v1_baseline() -> str:
    """基线版本：阶段三的 Prompt。"""
    return build_l1_system_prompt()


def v2_topic_focus() -> str:
    """变体：强化评论主题分析的具体性。"""
    base = build_l1_system_prompt()
    extra = """
【评论主题分析强化】
- 分析评论主题时，必须给出具体话题，不要用“内容好”“节奏不错”这种笼统描述。
- 每个主题必须能对应到至少一条评论原文。
- 如果主题不足 3 个，只输出实际数量，不要凑数。
"""
    return base + "\n\n" + extra.strip()


def v3_suggestion_focus() -> str:
    """变体：强化建议可执行性。"""
    base = build_l1_system_prompt()
    extra = """
【创作建议强化】
- 每条建议必须包含：具体动作 + 具体对象 + 具体时机。
- 禁止出现“优化”“加强”“提升”这类没有动作的词。
- 示例：不要说“优化开头”，要说“前 3 秒直接展示最终效果画面”。
"""
    return base + "\n\n" + extra.strip()


VARIANTS = {
    "v1": v1_baseline,
    "v2_topic": v2_topic_focus,
    "v3_suggestion": v3_suggestion_focus,
}


def get_variant(name: str) -> str:
    if name not in VARIANTS:
        raise KeyError(f"未知 Prompt 变体：{name}")
    return VARIANTS[name]()