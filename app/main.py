# 导入 asyncio 模块，用于运行异步函数（async/await）
import asyncio
# 导入 sys 模块，用于获取命令行传入的参数
import sys

# 导入封装好的大语言模型客户端
from app.core.llm import LLMClient
# 导入前面编写的 Agent 运行时类
from app.core.runtime import AgentRuntime
# 导入我们自定义的 Echo 工具类
from app.tools.echo import EchoTool
# 导入工具注册表类
from app.tools.registry import ToolRegistry


async def run_once(user_input: str) -> None:
    """
    执行一次完整的 Agent 交互流程。
    
    参数:
        user_input (str): 用户输入的文本。
    """
    # 1. 初始化并配置工具
    registry = ToolRegistry()
    # 将 Echo 工具实例注册到工具注册表中
    registry.register(EchoTool())

    # 2. 初始化大模型客户端和 Agent 运行时
    llm = LLMClient()
    # 创建运行时实例，传入大模型、工具注册表，并设置最大执行步数为 5
    runtime = AgentRuntime(llm=llm, tools=registry, max_steps=5)

    # 3. 构建初始消息列表（符合 OpenAI API 规范）
    messages = [
        {
            # System 消息：设定 Agent 的角色和行为准则
            "role": "system",
            "content": (
                "你是一个最小 Agent。"
                "当用户要求回显、复述或测试工具调用时，必须调用 echo 工具。"
                "不要自己编造工具执行结果。"
            ),
        },
        {
            # User 消息：传入用户的实际输入
            "role": "user", 
            "content": user_input
        },
    ]

    # 4. 启动 Agent 运行循环，等待大模型处理并返回最终结果
    result = await runtime.run(messages)

    # 5. 在控制台打印最终回复
    print("\n=== 最终回复 ===")
    print(result)


async def interactive() -> None:
    """
    启动交互式命令行循环。
    允许用户连续输入多条消息与 Agent 对话，直到输入退出指令。
    """
    print("Hello Agent 已启动。输入内容，回车发送；输入 exit 退出。")

    # 开启一个无限循环，持续等待用户输入
    while True:
        # 获取用户输入，并去除首尾的空白字符
        user_input = input("\n你：").strip()

        # 如果用户输入 exit 或 quit（不区分大小写），则退出循环
        if user_input.lower() in {"exit", "quit"}:
            print("再见。")
            break

        # 如果用户只输入了回车（空字符串），则跳过本次循环，继续等待输入
        if not user_input:
            continue

        # 调用 run_once 处理当前这一轮的用户输入
        await run_once(user_input)


def main() -> None:
    """
    程序的主入口函数。
    根据是否带有命令行参数，决定是执行单次任务还是进入交互模式。
    """
    # 检查命令行参数的数量（sys.argv[0] 是脚本文件名本身）
    if len(sys.argv) > 1:
        # 如果有参数，将参数列表中除脚本名外的所有部分拼接成一个字符串作为用户输入
        user_input = " ".join(sys.argv[1:])
        # 使用 asyncio.run() 运行单次交互函数
        asyncio.run(run_once(user_input))
    else:
        # 如果没有参数，使用 asyncio.run() 启动交互式对话循环
        asyncio.run(interactive())


# Python 标准入口点判断：
# 当此脚本被直接运行（如 python main.py）时，__name__ 等于 "__main__"，执行 main()
# 当此脚本被其他模块 import 导入时，__name__ 不等于 "__main__"，不会自动执行 main()
if __name__ == "__main__":
    main()