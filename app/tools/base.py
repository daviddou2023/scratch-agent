"""
定义了一个工具（Tool）的抽象基类（Abstract Base Class）。在 Agent 架构中，作为一个“接口规范”，
强制要求所有自定义工具（如：抓取视频数据工具、评论分析工具）都必须遵循相同的结构和命名规范。
"""

# 从 Python 标准库 abc (Abstract Base Classes) 中导入 ABC 和 abstractmethod。
# ABC: 抽象基类，用于定义一个不能被直接实例化的类，只能被继承。
# abstractmethod: 装饰器，用于标记抽象方法，强制子类必须实现该方法。
from abc import ABC, abstractmethod
from typing import Any

# Pydantic 是一个强大的数据验证库，在这里主要用于定义工具的“参数结构（Schema）”，
# 这样大模型（LLM）才能准确知道调用该工具时需要传入哪些参数。
from pydantic import BaseModel

# 导入前面定义的工具统一响应模型
from app.core.schemas import ToolResponse

class Tool(ABC):
     # 这个名称会被传递给大模型，大模型通过它来识别和决定调用哪个工具。
    name: str
    # 大模型完全依赖这段描述来理解工具的用途
    description: str
     # 它定义了调用该工具所需的参数结构，大模型会根据这个 Schema 生成符合格式的 JSON 参数。
    args_schema: type[BaseModel]

    # 带有此装饰器的方法没有具体实现逻辑，子类在继承 Tool 时，**必须**重写并实现这个方法
    @abstractmethod
     # 返回类型强制要求为 ToolResponse，保证所有工具的输出格式统一
    async def run(self, **kwargs: Any) -> ToolResponse:
        # - **kwargs: 接收任意数量的关键字参数，这些参数通常是由大模型根据 args_schema 生成的。
        # - -> Any: 返回值类型不限，可以是字符串、字典或自定义对象。
        raise NotImplementedError