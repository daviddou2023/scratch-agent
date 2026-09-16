"""错误码恢复策略。

每个错误码对应一段明确的处理指令，写入 System Prompt。
模型看到工具返回的 error.code 后，按这里的策略行动。
"""

RECOVERY_RULES = """\
当工具返回 status=error 时，按 error.code 执行：

- EMPTY_INPUT：参数为空。检查参数，补齐后重试一次；仍失败则告知用户。
- INVALID_ARGUMENT：参数非法。修正参数后重试；不要重复传同样的参数。
- VIDEO_NOT_FOUND：视频不存在。停止任务，让用户确认链接。
- RATE_LIMITED：触发限流。不要立即重试；告知用户“数据抓取受限，请稍后重试”。
- AUTH_FAILED：鉴权失败。停止任务，告知用户检查 API 配置。
- API_TIMEOUT：外部 API 超时。可重试一次；仍失败则基于已有数据继续，并注明缺失。
- NETWORK_ERROR：网络错误。可重试一次；仍失败则告知用户。
- ALL_FILTERED：清洗后评论全被过滤。不要强行分析；报告里注明“有效评论不足”。
- MISSING_METRICS：指标字段缺失。不要编造缺失字段；报告中明确标注。
- LLM_PARSE_ERROR：LLM 输出无法解析。重试一次；仍失败则返回原始文本。
- TOKEN_LIMIT：上下文超限。缩小输入范围后重试。
- TOOL_NOT_FOUND：工具不存在。不要重复调用；改用已有工具或告知用户。
- TOOL_EXCEPTION：工具内部异常。不要重复调用；记录错误并告知用户。
- NOT_IMPLEMENTED：功能未实现。告知用户该功能暂不可用。

重要：
- 同一个错误码连续失败 2 次后，停止重试，向用户报告。
- 禁止用同样的参数重复调用同一个工具超过 2 次。
- 任何降级都必须如实告知用户，不要假装成功。
"""