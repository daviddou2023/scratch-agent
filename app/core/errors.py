"""
新增错误码
"""

"""统一错误码定义。

设计原则：
1. 错误码机器可读，模型可据此决策。
2. 每个错误码都有明确的恢复策略（见 prompts/recovery.py）。
3. 区分“确实没有数据”和“出错了”。
"""


class ErrorCode:
    # ---- 输入类 ----
    EMPTY_INPUT = "EMPTY_INPUT"                 # 输入为空
    INVALID_ARGUMENT = "INVALID_ARGUMENT"       # 参数非法
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"         # 视频不存在

    # ---- 外部依赖类 ----
    RATE_LIMITED = "RATE_LIMITED"               # 触发限流
    AUTH_FAILED = "AUTH_FAILED"                 # 鉴权失败
    API_TIMEOUT = "API_TIMEOUT"                 # 外部 API 超时
    NETWORK_ERROR = "NETWORK_ERROR"             # 网络错误

    # ---- 数据类 ----
    EMPTY_COMMENTS = "EMPTY_COMMENTS"           # 评论为空（注意：这是 success 的一种）
    ALL_FILTERED = "ALL_FILTERED"               # 清洗后全被过滤
    MISSING_METRICS = "MISSING_METRICS"         # 指标字段缺失

    # ---- LLM 类 ----
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"         # LLM 输出无法解析
    TOKEN_LIMIT = "TOKEN_LIMIT"                 # 上下文超限

    # ---- 工具类 ----
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"           # 工具不存在
    TOOL_EXCEPTION = "TOOL_EXCEPTION"           # 工具内部异常
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"         # 功能未实现