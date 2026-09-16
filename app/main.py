# 导入 asyncio 模块，用于运行异步函数（如 async def 定义的协程）
import asyncio
# 导入 sys 模块，用于获取命令行传入的参数
import sys

# 导入前面编写的大语言模型客户端
from app.core.llm import LLMClient
# 导入 Agent 运行时类，负责驱动核心交互循环
from app.core.runtime import AgentRuntime
# 导入链路追踪器，用于记录运行全过程
from app.observability.tracer import Tracer
# 导入具体的 Echo 工具实现
from app.tools.echo import EchoTool
# 导入工具注册表，用于统一管理所有可用工具
from app.tools.registry import ToolRegistry


async def run_once(user_input: str) -> None:
    """
    执行一次完整的 Agent 交互流程。
    
    参数:
        user_input (str): 用户输入的文本内容。
    """
    # 初始化一个链路追踪器实例，自动分配 run_id 并创建 traces 目录
    tracer = Tracer()

    # 初始化工具注册表
    registry = ToolRegistry()
    # 将 EchoTool 实例注册到注册表中，使其对 Agent 可用
    registry.register(EchoTool())

    # 初始化 LLM 客户端，并注入 tracer，使其能自动记录 LLM 的请求和响应
    llm = LLMClient(tracer=tracer)
    
    # 初始化 Agent 运行时环境，注入 llm、工具注册表和 tracer，并设置最大执行步数为 5
    runtime = AgentRuntime(llm=llm, tools=registry, tracer=tracer, max_steps=5)

    # 构建初始的对话消息列表
    messages = [
        {
            "role": "system",  # 系统提示词，用于设定 Agent 的角色和行为规范
            "content": (
                "你是一个最小 Agent。"
                "当用户要求回显、复述或测试工具调用时，必须调用 echo 工具。"
                "不要自己编造工具执行结果。"
            ),
        },
        {"role": "user", "content": user_input},  # 用户的实际输入内容
    ]

    try:
        # 异步运行 Agent 的核心交互循环，获取最终生成的文本回复
        result = await runtime.run(messages)
        # 在控制台打印最终回复
        print("\n=== 最终回复 ===")
        print(result)
    finally:
        # 无论 Agent 执行成功还是中途抛出异常，finally 块中的代码都会被执行
        # 将追踪器内存中记录的所有事件序列化为 JSONL 文件并保存到磁盘
        path = tracer.save()
        # 在控制台打印 Trace 文件的保存路径和本次运行的 ID，方便后续排查问题
        print(f"\n=== Trace 已保存 ===")
        print(path)
        print(f"run_id: {tracer.run_id}")


async def interactive() -> None:
    """
    启动交互式命令行界面（CLI），允许用户连续与 Agent 进行多轮对话。
    """
    print("Hello Agent 已启动。输入内容，回车发送；输入 exit 退出。")

    # 开启一个无限循环，持续等待用户输入
    while True:
        # 获取用户在控制台的输入，并去除首尾的空白字符
        user_input = input("\n你：").strip()

        # 如果用户输入了退出指令（不区分大小写），则打印告别语并跳出循环
        if user_input.lower() in {"exit", "quit"}:
            print("再见。")
            break

        # 如果用户直接回车（输入为空），则跳过本次循环，继续等待输入
        if not user_input:
            continue

        # 调用 run_once 函数，处理用户的本次输入
        await run_once(user_input)


def main() -> None:
    """
    程序的主入口函数。
    根据是否传入了命令行参数，决定是执行单次任务还是进入交互模式。
    """
    # 检查是否通过命令行传入了参数（例如：python main.py 你好 世界）
    if len(sys.argv) > 1:
        # 如果有参数，将所有参数用空格拼接成一个完整的字符串作为用户输入
        user_input = " ".join(sys.argv[1:])
        # 使用 asyncio.run() 运行单次的异步任务
        asyncio.run(run_once(user_input))
    else:
        # 如果没有传入参数，则使用 asyncio.run() 启动交互式对话模式
        asyncio.run(interactive())


# 判断当前脚本是否被直接运行（而不是被其他模块 import 导入）
if __name__ == "__main__":
    # 如果是直接运行，则调用主入口函数
    main()