"""
低频兜底层：受限 Bash。

定位：只处理原子工具覆盖不到的边角需求。
禁区：禁止读/搜/列（有专门工具）、禁止交互、禁止网络、禁止危险命令。

错误码：
- INVALID_ARGUMENT：命令命中禁区
- TOOL_EXCEPTION：执行异常
"""

# 导入 asyncio 模块，用于异步执行 shell 命令和设置超时
import asyncio
# 导入 re 模块，用于正则表达式匹配，检测命令是否命中禁区
import re

# 从 pydantic 导入 BaseModel 和 Field，用于定义工具入参的结构化校验
from pydantic import BaseModel, Field

# 导入项目中自定义的错误码枚举
from app.core.errors import ErrorCode
# 导入统一的工具响应数据结构
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有自定义工具都需要继承它
from app.tools.base import Tool
# 导入封装好的标准响应辅助函数：成功(ok)、失败(fail)
from app.tools.response import fail, ok

# ==================== 禁区规则定义 ====================
# 禁区：这些高频动作有专门工具，或者存在安全风险，禁止通过 Bash 工具执行
# 格式：(正则表达式, 提示原因)
DISABLED_PATTERNS = [
    # --- 文件操作类：有专门的原子工具，禁止用 Bash 替代 ---
    (r"\bls\b", "请使用 list_dir 工具"),       # 禁止列出目录
    (r"\bcat\b", "请使用 read_file 工具"),      # 禁止读取文件内容
    (r"\bhead\b", "请使用 read_file 工具"),     # 禁止读取文件头部
    (r"\btail\b", "请使用 read_file 工具"),     # 禁止读取文件尾部
    (r"\bgrep\b", "请使用 search_content 工具"), # 禁止文本搜索
    (r"\brg\b", "请使用 search_content 工具"),  # 禁止 ripgrep 搜索
    (r"\bfind\b", "请使用 glob_files 工具"),    # 禁止文件查找
    
    # --- 交互式命令：无法在后台异步执行，禁止使用 ---
    (r"\bvim?\b", "禁止交互式命令"),  # 禁止 vim/vi 编辑器
    (r"\bnano\b", "禁止交互式命令"),  # 禁止 nano 编辑器
    (r"\btop\b", "禁止交互式命令"),   # 禁止 top 进程监控
    (r"\bssh\b", "禁止交互式命令"),   # 禁止 SSH 远程连接
    
    # --- 网络命令：有专门的网络工具，且存在外联风险 ---
    (r"\bcurl\b", "禁止网络命令"),  # 禁止 curl 请求
    (r"\bwget\b", "禁止网络命令"),  # 禁止 wget 下载
    
    # --- 危险命令：可能对系统造成不可逆的破坏 ---
    (r"\brm\s+-rf\b", "禁止危险命令"),  # 禁止强制递归删除
    (r"\bsudo\b", "禁止危险命令"),      # 禁止提权操作
    (r"\bsu\b", "禁止危险命令"),        # 禁止切换用户
    (r"\bmkfs\b", "禁止危险命令"),      # 禁止格式化文件系统
    (r"\bfdisk\b", "禁止危险命令"),     # 禁止磁盘分区操作
]

# ==================== 白名单定义 ====================
# 允许的命令白名单前缀：只允许执行这些安全的、开发场景常用的命令
ALLOWED_PREFIXES = [
    "pytest",        # 运行单元测试
    "python",        # 运行 Python 脚本
    "pip",           # 安装 Python 依赖包
    "git status",    # 查看 Git 状态
    "git diff",      # 查看 Git 代码差异
    "git log",       # 查看 Git 提交日志
    "echo",          # 输出文本（常用于调试）
]

# ==================== 工具类定义 ====================

class RunBashArgs(BaseModel):
    """
    定义 run_bash 工具的入参结构。
    """
    # 要执行的 shell 命令字符串，必填字段
    command: str = Field(..., description="要执行的命令")
    # 命令执行的超时时间（秒），默认 30 秒，最小 1 秒，最大 120 秒
    timeout: int = Field(30, ge=1, le=120, description="超时秒数")


class RunBashTool(Tool):
    """
    受限 Bash 执行工具类。
    继承自 Tool 基类，作为低频兜底工具，用于处理原子工具覆盖不到的边角需求。
    通过"黑名单 + 白名单"双重机制，确保命令执行的安全性。
    """
    # 工具的唯一标识名称
    name = "run_bash"
    # 工具的功能描述
    description = "执行受限 shell 命令。仅用于原子工具覆盖不到的边角需求。"
    # 绑定前面定义的入参校验模型
    args_schema = RunBashArgs

    async def run(self, command: str, timeout: int = 30) -> ToolResponse:
        """
        执行受限 shell 命令的核心逻辑。
        
        参数:
            command (str): 要执行的 shell 命令。
            timeout (int): 超时秒数，默认 30 秒。
            
        返回:
            ToolResponse: 封装了命令执行结果（返回码、标准输出、标准错误）的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查命令是否为空或纯空白字符
        if not command.strip():
            return fail(ErrorCode.EMPTY_INPUT, "command 不能为空")

        # --- 2. 黑名单校验：检查命令是否命中禁区 ---
        # 遍历所有禁区正则规则，如果命令匹配到任意一个，直接返回失败响应
        for pattern, reason in DISABLED_PATTERNS:
            if re.search(pattern, command):
                return fail(
                    ErrorCode.INVALID_ARGUMENT,
                    f"命令命中禁区：{reason}",
                    details={"command": command, "pattern": pattern},  # 附带原始命令和匹配到的规则，方便排查
                )

        # --- 3. 白名单校验：检查命令是否在允许的前缀列表中 ---
        # 如果命令的开头不匹配任何白名单前缀，直接返回失败响应
        if not any(command.strip().startswith(p) for p in ALLOWED_PREFIXES):
            return fail(
                ErrorCode.INVALID_ARGUMENT,
                f"命令不在白名单：{command.split()[0]}",  # 提示用户第一个单词（即命令名）不在白名单
                details={"allowed": ALLOWED_PREFIXES},    # 附带完整的白名单列表，方便用户参考
            )

        # --- 4. 异步执行命令 ---
        try:
            # 使用 asyncio 创建子进程，通过 shell 执行命令
            # stdout 和 stderr 都重定向到管道，以便后续捕获输出内容
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # 使用 asyncio.wait_for 设置超时时间，等待命令执行完成并获取输出
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            
        except asyncio.TimeoutError:
            # 如果命令执行超时，返回超时错误
            return fail(ErrorCode.API_TIMEOUT, f"命令超时：{timeout}s")
            
        except Exception as e:
            # 如果执行过程中出现其他异常（如权限不足、命令不存在等），返回异常错误
            return fail(ErrorCode.TOOL_EXCEPTION, f"命令执行异常：{e}")

        # --- 5. 返回成功结果 ---
        # 将命令的返回码、标准输出、标准错误封装成字典返回
        # 输出内容使用 utf-8 解码（遇到无法解码的字符用替换符代替），并截取前 N 个字符防止输出过长
        return ok(
            data={
                "returncode": proc.returncode,  # 命令返回码（0 表示成功，非 0 表示失败）
                "stdout": stdout.decode("utf-8", errors="replace")[:4000],   # 标准输出，最多截取 4000 字符
                "stderr": stderr.decode("utf-8", errors="replace")[:2000],   # 标准错误，最多截取 2000 字符
            },
            text=f"命令执行完成，返回码 {proc.returncode}",
        )