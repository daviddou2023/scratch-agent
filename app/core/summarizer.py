"""
Summary 压缩。

设计原则（来自笔记第五章）：
1. 压缩不是删除，而是把早期历史提炼成 Summary。
2. Summary 一旦生成就是只读的"记忆卡片"，不再参与压缩。
3. 关键约束不进动态历史，压缩前先提取。
"""

# 导入 Any 类型，用于灵活的字典值类型标注
from typing import Any

# 导入 LLM 客户端，用于后续调用 LLM 生成摘要（MVP 版本暂未使用）
from app.core.llm import LLMClient


# ==================== Summary 模板 ====================

# 定义 Summary 的结构化模板，使用 Markdown 格式
# 包含四个核心部分：目标与状态、完成的里程碑、关键洞察与决策、数据状态
SUMMARY_TEMPLATE = """\
## Archived Session Summary
(Contains context from earlier conversation)

### Objectives & Status
- Original Goal: {goal}

### Completed Milestones
{milestones}

### Key Insights & Decisions
{insights}

### Data State
{data_state}
"""


# ==================== 压缩器实现 ====================

class Summarizer:
    """
    对话历史压缩器。
    
    负责把早期的消息列表压缩成结构化的 Summary 文本，
    节省上下文窗口，同时保留关键信息。
    
    MVP 版本使用规则提取，不调用 LLM。
    后续可替换为 LLM 摘要生成，提升压缩质量。
    """
    
    def __init__(self, llm: LLMClient) -> None:
        """
        初始化压缩器。
        
        参数:
            llm (LLMClient): LLM 客户端实例，用于后续调用 LLM 生成摘要。
        """
        # 保存 LLM 客户端，MVP 版本暂未使用，预留扩展
        self.llm = llm

    async def summarize(
        self,
        messages: list[dict[str, Any]],
        goal: str = "",
    ) -> str:
        """
        把早期消息压缩成 Summary。
        
        MVP 用规则提取，不调 LLM。后续可替换为 LLM 摘要。
        
        参数:
            messages (list[dict[str, Any]]): 早期的对话消息列表。
                每条消息是一个字典，包含 role 和 content 字段。
            goal (str): 用户的原始目标，用于填充 Summary 的"目标"部分。
            
        返回:
            str: 压缩后的 Summary 文本，使用 SUMMARY_TEMPLATE 格式化。
        """
        # --- 初始化三个列表，用于收集不同类型的信息 ---
        # 里程碑：记录已完成的任务、工具执行成功等
        milestones: list[str] = []
        # 洞察与决策：记录模型分析、工具失败记录等
        insights: list[str] = []
        # 数据状态：记录当前数据的状态（MVP 版本暂未使用）
        data_state: list[str] = []

        # --- 遍历所有消息，按规则提取关键信息 ---
        for msg in messages:
            # 获取消息的角色（user / assistant / tool / system）
            role = msg.get("role")
            # 获取消息的内容，默认为空字符串
            content = msg.get("content", "")

            if role == "tool":
                # 处理工具返回的消息
                # 检查内容中是否包含"已完成"或"success"，判断为工具执行成功
                if "已完成" in content or "success" in content:
                    # 截取前 80 个字符，避免单条信息过长
                    milestones.append(f"- 工具执行成功：{content[:80]}")
                # 检查内容中是否包含"error"（不区分大小写），判断为工具执行失败
                elif "error" in content.lower():
                    # 截取前 80 个字符，记录失败信息
                    insights.append(f"- 工具失败记录：{content[:80]}")

            elif role == "assistant" and content:
                # 处理模型回复的消息
                # 检查内容中是否包含"总结"或"分析"，判断为模型的分析输出
                if "总结" in content or "分析" in content:
                    # 截取前 80 个字符，记录模型分析
                    insights.append(f"- 模型分析：{content[:80]}")

        # --- 使用模板格式化 Summary ---
        # 使用 SUMMARY_TEMPLATE 模板，填充四个部分的内容
        return SUMMARY_TEMPLATE.format(
            # 原始目标，如果未提供则显示"未明确"
            goal=goal or "未明确",
            # 完成的里程碑，如果没有则显示"- 无"
            milestones="\n".join(milestones) or "- 无",
            # 关键洞察与决策，如果没有则显示"- 无"
            insights="\n".join(insights) or "- 无",
            # 数据状态，如果没有则显示"- 无"
            data_state="\n".join(data_state) or "- 无",
        )