"""
上下文分层与拼接。

设计原则（来自笔记第五章）：
1. L1 系统静态层：System Prompt + 工具描述，不可压缩。
2. L2 项目规则层：CODE_LAW.md，可更新，不参与压缩。
3. L3 动态会话层：User/Assistant/Tool 消息，可压缩。

拼接顺序：L1 → L2 → L3 → Todo Recap → 当前用户输入
"""

# 导入 Path，用于读取项目规则文件
from pathlib import Path
# 导入 Any 类型，用于灵活的字典值类型标注
from typing import Any

# 导入 TodoList，用于生成 Todo Recap
from app.core.todo import TodoList


# ==================== 上下文构建器 ====================

class ContextBuilder:
    """
    上下文构建器。
    
    负责管理四层内容（L1/L2/L3 + Summary + Todo Recap），
    并按顺序拼接成完整的 messages 列表，供 LLM 调用。
    
    设计原则：
    - L1 系统静态层：不可压缩，始终保留
    - L2 项目规则层：可更新，不参与压缩
    - L3 动态会话层：可压缩，早期历史提炼成 Summary
    - Todo Recap：当前焦点，每次交互更新
    """
    
    def __init__(
        self,
        l1_system_prompt: str,
        l2_code_law_path: str | None = None,
    ) -> None:
        """
        初始化上下文构建器。
        
        参数:
            l1_system_prompt (str): L1 系统静态层的 System Prompt。
            l2_code_law_path (str | None): L2 项目规则层的路径（CODE_LAW.md）。
        """
        # L1：系统静态层，始终保留，不可压缩
        self.l1 = l1_system_prompt
        
        # L2：项目规则层，从文件加载，可更新但不参与压缩
        self.l2 = self._load_l2(l2_code_law_path)
        
        # L3：动态会话层，存储 User/Assistant/Tool 消息，可压缩
        self.l3: list[dict[str, Any]] = []
        
        # Summary：早期历史的压缩摘要，生成后只读
        self.summary: str | None = None
        
        # Todo：当前待办事项列表，用于生成 Todo Recap
        self.todo: TodoList | None = None

    def _load_l2(self, path: str | None) -> str:
        """
        加载 L2 项目规则层。
        
        从指定路径读取 CODE_LAW.md 文件内容。
        
        参数:
            path (str | None): 项目规则文件的路径。
            
        返回:
            str: 文件内容，如果路径为空或文件不存在则返回空字符串。
        """
        # 如果路径为空，返回空字符串
        if not path:
            return ""
        
        # 创建 Path 对象
        p = Path(path)
        
        # 如果文件不存在，返回空字符串
        if not p.exists():
            return ""
        
        # 读取文件内容，使用 UTF-8 编码
        return p.read_text(encoding="utf-8")

    # ==================== L3 管理 ====================

    def append(self, message: dict[str, Any]) -> None:
        """
        添加一条消息到 L3 动态会话层。
        
        参数:
            message (dict[str, Any]): 消息字典，包含 role 和 content 字段。
        """
        # 将消息添加到 L3 列表末尾
        self.l3.append(message)

    def get_messages(self, current_user_input: str = "") -> list[dict[str, Any]]:
        """
        拼接完整 messages，供 LLM 调用。
        
        拼接顺序：L1 → L2 → L3 → Todo Recap → 当前用户输入
        
        参数:
            current_user_input (str): 当前用户的输入内容。
            
        返回:
            list[dict[str, Any]]: 完整的 messages 列表。
        """
        # 初始化 messages 列表
        messages: list[dict[str, Any]] = []

        # --- L1：系统静态层 ---
        # 始终添加 System Prompt，不可压缩
        messages.append({"role": "system", "content": self.l1})

        # --- L2：项目规则层 ---
        # 如果有项目规则，添加为 system 消息
        if self.l2:
            messages.append(
                {"role": "system", "content": f"【项目规则】\n{self.l2}"}
            )

        # --- L3：动态会话层 ---
        # 如果有 Summary（早期历史摘要），先添加为 system 消息
        if self.summary:
            messages.append(
                {"role": "system", "content": f"【历史摘要】\n{self.summary}"}
            )
        # 然后添加 L3 中的动态消息（User/Assistant/Tool）
        messages.extend(self.l3)

        # --- Todo Recap：当前焦点 ---
        # 如果有 Todo 列表，生成 Recap 并添加为 system 消息
        if self.todo:
            recap = self.todo.recap()
            # 只有 Recap 不为空时才添加
            if recap:
                messages.append(
                    {"role": "system", "content": f"【当前进度】{recap}"}
                )

        # --- 当前用户输入 ---
        # 如果有当前用户输入，添加为 user 消息
        if current_user_input:
            messages.append({"role": "user", "content": current_user_input})

        # 返回完整的 messages 列表
        return messages

    # ==================== 压缩 ====================

    def should_compress(self, max_tokens: int, ratio: float) -> bool:
        """
        判断是否需要压缩。
        
        MVP 用字符数近似 token，计算 L3 动态会话层的总字符数。
        
        参数:
            max_tokens (int): 最大 token 数。
            ratio (float): 压缩触发比例（例如 0.8 表示达到 80% 时触发压缩）。
            
        返回:
            bool: 是否需要压缩。
        """
        # 计算 L3 中所有消息的内容总字符数
        # 使用 str() 转换，确保 content 是字符串
        total_chars = sum(len(str(m.get("content", ""))) for m in self.l3)
        
        # 如果总字符数超过阈值（max_tokens * ratio），返回 True
        return total_chars > max_tokens * ratio

    def apply_summary(self, summary: str) -> None:
        """
        应用 Summary，清空早期 L3。
        
        参数:
            summary (str): 压缩后的 Summary 文本。
        """
        # 保存 Summary，作为只读的"记忆卡片"
        self.summary = summary
        
        # 优先保留最近一组完整的工具调用消息，避免截断消息配对
        # 没有工具调用时才保留最近 4 条普通消息
        last_tool_call_index = None
        for index in range(len(self.l3) - 1, -1, -1):
            message = self.l3[index]
            if message.get("role") == "assistant" and message.get("tool_calls"):
                last_tool_call_index = index
                break

        if last_tool_call_index is not None:
            self.l3 = self.l3[last_tool_call_index:]
        else:
            self.l3 = self.l3[-4:]
            while self.l3 and self.l3[0].get("role") == "tool":
                self.l3.pop(0)

    # ==================== 工具输出 ====================

    def append_tool_result(self, tool_call_id: str, content: str) -> None:
        """
        添加工具执行结果到 L3。
        
        参数:
            tool_call_id (str): 工具调用的 ID，用于关联请求和响应。
            content (str): 工具执行的结果内容。
        """
        # 添加工具消息，role 为 "tool"，包含 tool_call_id 和 content
        self.l3.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )
