# 从 typing 模块中导入 Any 类型，用于在类型提示中表示任意数据类型
from typing import Any

# 从当前项目的 app.tools.base 模块中导入 Tool 基类
from app.tools.base import Tool


class ToolRegistry:
    """
    工具注册表类。
    用于统一管理、注册和获取各种工具（Tool）实例，并能将其转换为 OpenAI API 所需的格式。
    """

    def __init__(self) -> None:
        """
        初始化方法。
        创建一个空的字典，用于在内部存储已注册的工具。
        键（key）为工具的名称（字符串），值（value）为对应的 Tool 实例。
        """
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        注册一个工具到注册表中。
        
        参数:
            tool (Tool): 需要注册的工具实例。
        """
        # 以工具的名称作为键，将工具实例存入内部字典中
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """
        根据名称获取指定的工具实例。
        
        参数:
            name (str): 要获取的工具的名称。
            
        返回:
            Tool: 对应的工具实例。
            
        异常:
            KeyError: 当请求的工具名称不在注册表中时抛出。
        """
        # 检查工具名称是否存在于字典中，如果不存在则抛出 KeyError 异常
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        # 如果存在，则返回对应的工具实例
        return self._tools[name]

    def openai_tools(self) -> list[dict[str, Any]]:
        """
        将注册表中的所有工具转换为 OpenAI API 所需的工具定义格式。
        
        返回:
            list[dict[str, Any]]: 包含所有工具定义的字典列表，
                                  每个字典符合 OpenAI function calling 的规范。
        """
        # 使用列表推导式遍历所有已注册的工具实例，生成符合 OpenAI 规范的字典列表
        return [
            {
                "type": "function",  # 工具类型固定为 "function"
                "function": {
                    "name": tool.name,  # 函数的名称
                    "description": tool.description,  # 函数的功能描述
                    # 使用工具自带的参数模式（args_schema）生成 JSON Schema，用于描述函数的参数结构
                    "parameters": tool.args_schema.model_json_schema(),
                },
            }
            # 遍历内部字典中的所有工具实例
            for tool in self._tools.values()
        ]