import os

# dataclass 是 Python 的一种语法糖，可以自动根据类属性生成 __init__、__repr__ 等方法，让编写数据类变得极其简洁。
from dataclasses import dataclass 
from dotenv import load_dotenv
load_dotenv()

# 使用 dataclass 装饰器将下方的类转化为数据类。
# 关键参数 frozen=True：表示创建一个“冻结（不可变）”的类。
@dataclass(frozen=True)
class Settings:
    # 定义 open_api_key 属性，类型提示为 str。
    # 尝试从环境变量中获取 "OPENAI_API_KEY" 的值；如果找不到，则默认返回空字符串 ""。
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "")

    # ---- 上下文阈值 ----
    context_max_tokens: int = int(os.getenv("CONTEXT_MAX_TOKENS", "8000"))
    context_compress_ratio: float = float(os.getenv("CONTEXT_COMPRESS_RATIO", "0.8"))

    # ---- 工具输出截断 ----
    tool_output_max_lines: int = int(os.getenv("TOOL_OUTPUT_MAX_LINES", "2000"))
    tool_output_max_bytes: int = int(os.getenv("TOOL_OUTPUT_MAX_BYTES", "51200"))
    tool_output_head_tail_lines: int = int(os.getenv("TOOL_OUTPUT_HEAD_TAIL_LINES", "40"))

    # ---- 落盘目录 ----
    tool_output_dir: str = os.getenv("TOOL_OUTPUT_DIR", "tool-output")


# 实例化 Settings 类，创建一个全局单例对象 `settings`。
# 在项目的其他文件中，只需通过 `from 当前文件 import settings` 即可直接访问配置，
# 例如：`settings.open_api_key`，无需重复读取环境变量。
settings = Settings()