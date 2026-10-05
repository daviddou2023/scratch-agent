"""
Todo Recap：当前焦点管理。

设计原则（来自笔记第五章）：
- Summary 告诉模型"从哪来"，Todo 告诉模型"现在在哪"。
- 每次交互时，把当前 Todo 状态压缩成一行，放在上下文最后。
"""

# 导入 dataclass 装饰器，用于自动生成 __init__、__repr__ 等方法
from dataclasses import dataclass, field


# ==================== 数据模型 ====================

@dataclass
class TodoItem:
    """
    单个待办事项。
    
    包含内容和状态，状态有三种：
    - pending: 待处理
    - in_progress: 进行中
    - done: 已完成
    """
    # 待办事项的内容描述
    content: str
    
    # 当前状态，默认为 "pending"（待处理）
    status: str = "pending"  # pending / in_progress / done


@dataclass
class TodoList:
    """
    待办事项列表。
    
    管理一组 TodoItem，支持添加、开始、完成操作，
    并能生成一行压缩的 Recap 文本，放在上下文最后。
    """
    # 待办事项列表，使用 field(default_factory=list) 确保每个实例有独立的列表
    items: list[TodoItem] = field(default_factory=list)

    def add(self, content: str) -> None:
        """
        添加一个新的待办事项。
        
        参数:
            content (str): 待办事项的内容描述。
        """
        # 创建一个新的 TodoItem，状态默认为 pending，添加到列表末尾
        self.items.append(TodoItem(content=content))

    def start(self, index: int) -> None:
        """
        将指定索引的待办事项标记为"进行中"。
        
        参数:
            index (int): 待办事项的索引（从 0 开始）。
        """
        # 检查索引是否在有效范围内
        if 0 <= index < len(self.items):
            # 将状态改为 "in_progress"
            self.items[index].status = "in_progress"

    def done(self, index: int) -> None:
        """
        将指定索引的待办事项标记为"已完成"。
        
        参数:
            index (int): 待办事项的索引（从 0 开始）。
        """
        # 检查索引是否在有效范围内
        if 0 <= index < len(self.items):
            # 将状态改为 "done"
            self.items[index].status = "done"

    def recap(self) -> str:
        """
        生成一行 Todo Recap，放在上下文最后。
        
        设计原则：
        - 告诉模型"现在在哪"（当前进行中的任务）
        - 告诉模型"还剩什么"（待办事项列表）
        - 压缩成一行，节省上下文空间
        
        返回:
            str: 压缩后的 Recap 文本，如果没有待办事项则返回空字符串。
        """
        # 如果没有待办事项，返回空字符串
        if not self.items:
            return ""

        # --- 统计信息 ---
        # 待办事项总数
        total = len(self.items)
        # 当前进行中的任务索引（从 1 开始，方便人类阅读）
        current_idx = None
        # 当前进行中的任务内容
        current = None
        # 待处理的任务列表
        pending = []

        # --- 遍历所有待办事项，分类统计 ---
        for i, item in enumerate(self.items):
            if item.status == "in_progress" and current is None:
                # 找到第一个"进行中"的任务
                # 只记录第一个，避免多个任务同时标记为 in_progress 时混乱
                current_idx = i + 1  # 索引从 1 开始
                current = item.content
            elif item.status == "pending":
                # 收集所有"待处理"的任务
                pending.append(item.content)

        # --- 如果没有进行中的任务 ---
        if current is None:
            # 统计已完成的任务数量
            done_count = sum(1 for i in self.items if i.status == "done")
            
            # 如果全部完成
            if done_count == total:
                return f"[{total}/{total}] 全部完成."
            
            # 否则返回已完成数量和待办列表
            return f"[{done_count}/{total}] 待办: {'; '.join(pending)}"

        # --- 如果有进行中的任务 ---
        # 将待办列表拼接为字符串，如果没有待办则显示"无"
        pending_str = "; ".join(pending) if pending else "无"
        
        # 返回格式化的 Recap 文本
        # 格式：[当前进度/总数] 进行中: {当前任务}. 待办: {待办列表}.
        return (
            f"[{current_idx}/{total}] 进行中: {current}. "
            f"待办: {pending_str}."
        )


# ==================== 预设 Todo 模板 ====================

def default_todo_for_creator_review() -> TodoList:
    """
    创作者复盘的默认 Todo。
    
    这是一个预设的待办事项模板，用于创作者视频复盘场景。
    包含从数据采集到报告生成的完整流程。
    
    返回:
        TodoList: 预设的待办事项列表。
    """
    # 创建一个新的待办事项列表
    todo = TodoList()
    
    # 添加 6 个步骤，构成完整的复盘流程
    todo.add("采集视频指标")      # 步骤 1：获取视频的播放量、点赞数等指标
    todo.add("采集评论")          # 步骤 2：拉取视频下的评论数据
    todo.add("清洗评论")          # 步骤 3：过滤垃圾评论、广告等
    todo.add("分析评论")          # 步骤 4：情感分析、关键词提取等
    todo.add("生成流量报告")      # 步骤 5：生成结构化的流量分析报告
    todo.add("生成创作建议")      # 步骤 6：基于分析结果给出创作优化建议
    
    # 返回预设的待办事项列表
    return todo