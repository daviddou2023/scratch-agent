# 从 pydantic 库中导入 BaseModel（用于定义数据模型）和 Field（用于提供字段的额外验证和元数据）
from pydantic import BaseModel, Field

# 从当前项目的 app.tools.base 模块中导入 Tool 基类
from app.tools.base import Tool


# 定义一个继承自 BaseModel 的 Pydantic 模型，用于严格定义和验证 echo 工具的输入参数
class EchoArgs(BaseModel):
    # 定义必填的字符串参数 'text'
    # ... (Ellipsis) 表示该字段是必填项，不能为空；description 提供该字段的中文说明
    text: str = Field(..., description="需要回显的文本")
    
    # 定义整数参数 'repeat'，默认值为 1
    # ge=1 表示最小值为 1，le=5 表示最大值为 5，用于限制用户的重复次数
    repeat: int = Field(1, ge=1, le=5, description="重复次数，默认 1")


# 定义一个继承自 Tool 基类的具体工具类，实现简单的文本回显功能
class EchoTool(Tool):
    # 定义工具的唯一标识名称，供大模型在 function calling 时调用
    name = "echo"
    
    # 定义工具的功能描述，大模型会根据此描述判断何时应该调用该工具
    description = "当用户要求复述、回显或测试工具调用时，返回输入文本。"
    
    # 绑定前面定义的参数模型，用于大模型生成参数时的格式校验和 JSON Schema 生成
    args_schema = EchoArgs

    # 定义工具的异步执行方法，接收的参数与 EchoArgs 模型中的字段一一对应
    async def run(self, text: str, repeat: int = 1) -> dict:
        # 核心逻辑：如果重复次数为 1，则直接使用原文本；
        # 否则，将文本重复 repeat 次，并用空格拼接成一个新字符串
        echo_text = text if repeat == 1 else " ".join([text] * repeat)

        # 返回一个字典，包含处理后的文本、实际重复次数以及原始文本的长度
        return {
            "echo": echo_text,
            "repeat": repeat,
            "length": len(text),
        }