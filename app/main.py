# 导入 asyncio 模块，用于运行异步函数（async/await）
import asyncio
# 导入 sys 模块，用于读取命令行参数（sys.argv）
import sys

# 导入全局配置文件
from app.core.config import settings
# 导入上下文构建器
from app.core.context_builder import ContextBuilder

# 导入大语言模型客户端，负责与 LLM 进行对话交互
from app.core.llm import LLMClient
# 导入 Agent 运行时引擎，负责驱动"思考-行动-观察"的完整闭环
from app.core.runtime import AgentRuntime

# 导入上下文压缩器
from app.core.summarizer import Summarizer
# 导入todo recap
from app.core.todo import default_todo_for_creator_review


# 导入链路追踪器，用于记录 Agent 每一步的决策和执行过程，方便调试和复盘
from app.observability.tracer import Tracer
# 导入系统提示词构建函数，用于组装 Agent 的身份、规则、工具描述等
from app.prompts.system_prompt import build_l1_system_prompt

# ==================== 导入所有工具 ====================
# 中频受控层：需要 LLM 驱动的业务工具
from app.tools.analyze import AnalyzeCommentsTool        # 评论洞察工具
from app.tools.report import GenerateReportTool           # 流量报告生成工具
from app.tools.report import GenerateSuggestionsTool      # 创作建议生成工具

# 低频兜底层：受限 Bash 执行工具
from app.tools.bash import RunBashTool                    # 受限 Shell 命令执行

# 高频原子层：基础文件/数据操作工具
from app.tools.clean import CleanCommentsTool             # 评论清洗工具
from app.tools.comments import FetchCommentsTool          # 评论拉取工具
from app.tools.echo import EchoTool                       # 回声/调试工具（用于原样返回输入或简单响应）
from app.tools.metrics import FetchVideoMetricsTool       # 视频指标拉取工具

# 导入回查落盘的大输出
from app.tools.read_output import ReadOutputTool
# 导入工具注册表，用于统一管理所有可用工具
from app.tools.registry import ToolRegistry


# ==================== 工具注册函数 ====================
def build_registry(llm: LLMClient) -> ToolRegistry:
    """
    构建工具注册表，将所有工具按"三层架构"注册进去。
    
    参数:
        llm (LLMClient): LLM 客户端实例，部分工具需要依赖它。
        
    返回:
        ToolRegistry: 已注册所有工具的工具注册表。
    """
    # 创建空的工具注册表实例
    registry = ToolRegistry()

    # --- 高频原子层：基础数据获取与处理工具 ---
    # 这些工具不依赖 LLM，执行速度快，是 Agent 的"手脚"
    registry.register(EchoTool())                    # 回声工具：用于调试或简单响应
    registry.register(FetchVideoMetricsTool())        # 拉取视频的播放量、点赞量等核心指标
    registry.register(FetchCommentsTool())            # 拉取视频的评论区原始数据
    registry.register(CleanCommentsTool())            # 清洗评论：去重、去广告、脱敏

    # --- 中频受控层：需要 LLM 驱动的业务工具 ---
    # 这些工具依赖 LLM 进行分析和生成，是 Agent 的"大脑"
    registry.register(AnalyzeCommentsTool(llm))              # 基于清洗后的评论，提取主题和情绪
    registry.register(GenerateReportTool(llm))               # 基于指标和评论洞察，生成流量复盘报告
    registry.register(GenerateSuggestionsTool(llm))          # 基于流量报告，生成下一步创作建议

    # --- 低频兜底层：受限 Bash 执行 ---
    # 处理原子工具覆盖不到的边角需求，是 Agent 的"备用方案"
    registry.register(RunBashTool())                 # 执行受限的 Shell 命令（如运行测试、查看 Git 状态）

    # 回查工具
    registry.register(ReadOutputTool())
    # 返回已注册完成的工具注册表
    return registry


# ==================== 单次执行函数 ====================
async def run_once(user_input: str) -> None:
    """
    执行一次完整的 Agent 对话流程。
    
    参数:
        user_input (str): 用户输入的内容（如"帮我复盘视频 12345 的流量"）。
    """
    # --- 1. 初始化核心组件 ---
    # 创建链路追踪器，用于记录 Agent 的每一步决策和执行过程
    tracer = Tracer()

    # 创建 LLM 客户端，传入追踪器以便记录每次 LLM 调用的耗时和结果
    llm = LLMClient(tracer=tracer)
    
    # 构建工具注册表，将所有工具注册进去
    registry = build_registry(llm)

    # 创建上下文生成器
    context = ContextBuilder(
        l1_system_prompt=build_l1_system_prompt(),
        l2_code_law_path=None, # 后续可以放CODE_LAW.md
    )
    context.todo = default_todo_for_creator_review()
    summarizer = Summarizer(llm=llm)
    
    # 创建 Agent 运行时引擎
    # llm: 大语言模型客户端
    # tools: 工具注册表，Agent 可以从中调用工具
    # tracer: 链路追踪器，记录执行过程
    # max_steps=10: 最大执行步数，防止 Agent 无限循环（每调用一次工具算一步）
    runtime = AgentRuntime(
        llm=llm, 
        tools=registry, 
        tracer=tracer, 
        context=context,
        summarizer=summarizer,
        max_steps=10
        )

    # --- 3. 执行 Agent 并输出结果 ---
    try:
        # 调用 Agent 运行时的 run 方法，传入消息列表
        # Agent 会自动进行"思考-行动-观察"的循环，直到得出结论或达到最大步数
        result = await runtime.run(user_input)
        
        # 打印最终回复结果
        print("\n=== 最终回复 ===")
        print(result)
        
    finally:
        # 无论执行成功还是失败，都保存追踪数据
        # 将链路追踪数据保存到文件（如 JSON 格式），方便后续调试和复盘
        path = tracer.save()
        print(f"\n=== Trace 已保存 ===")
        print(path)                          # 打印追踪文件的保存路径
        print(f"run_id: {tracer.run_id}")    # 打印本次执行的唯一 ID，方便定位问题


# ==================== 交互式对话函数 ====================
async def interactive() -> None:
    """
    启动交互式对话模式，用户可以持续输入问题，Agent 持续回复。
    """
    # 打印启动提示
    print("创作者助手已启动。输入内容，回车发送；输入 exit 退出。")

    # 进入无限循环，持续接收用户输入
    while True:
        # 从命令行读取用户输入，并去除首尾空白
        user_input = input("\n你：").strip()

        # 如果用户输入 "exit" 或 "quit"，退出循环
        if user_input.lower() in {"exit", "quit"}:
            print("再见。")
            break

        # 如果用户输入为空（直接回车），跳过本次循环
        if not user_input:
            continue

        # 调用单次执行函数，处理用户输入
        await run_once(user_input)


# ==================== 主入口函数 ====================
def main() -> None:
    """
    程序主入口，根据命令行参数决定运行模式。
    """
    # 判断是否有命令行参数（sys.argv[0] 是脚本名，sys.argv[1:] 是用户传入的参数）
    if len(sys.argv) > 1:
        # --- 单次执行模式 ---
        # 如果有命令行参数，将所有参数拼接成一个字符串作为用户输入
        user_input = " ".join(sys.argv[1:])
        # 使用 asyncio.run() 运行单次异步函数
        asyncio.run(run_once(user_input))
    else:
        # --- 交互式模式 ---
        # 如果没有命令行参数，启动交互式对话
        asyncio.run(interactive())


# ==================== 程序入口 ====================
if __name__ == "__main__":
    # 当脚本被直接运行时（而非被其他模块导入时），执行 main 函数
    main()