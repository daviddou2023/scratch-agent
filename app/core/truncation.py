"""
大输出截断 + 落盘。

设计原则（来自笔记第五章）：
1. 截断显示，但保留回查路径。
2. 完整输出落盘，模型需要时用 read_tool_output 回查。
3. 统一截断规则，所有工具复用。
"""

# 导入 json 模块，用于序列化/反序列化 JSON 数据
import json
# 导入 time 模块，用于生成带时间戳的文件名
import time
# 导入 uuid 模块，用于生成唯一 ID，防止文件名冲突
import uuid
# 导入 pathlib.Path，用于跨平台的文件路径操作
from pathlib import Path
# 导入 typing.Any，用于类型注解（payload 可以是任意类型）
from typing import Any

# 导入项目配置，包含输出目录、最大行数、最大字节数等阈值设置
from app.core.config import settings


# ==================== 内部辅助函数 ====================

def _ensure_dir() -> Path:
    """
    确保工具输出目录存在。
    
    如果目录不存在，则递归创建（parents=True）。
    如果目录已存在，不做任何操作（exist_ok=True）。
    
    返回:
        Path: 输出目录的路径对象。
    """
    # 从配置中读取工具输出目录路径（如 "data/tool_outputs"）
    path = Path(settings.tool_output_dir)
    # 递归创建目录，如果已存在则不报错
    path.mkdir(parents=True, exist_ok=True)
    # 返回目录路径对象
    return path


def _save_full_output(tool_name: str, payload: Any) -> Path:
    """
    把完整输出落盘到 JSON 文件，返回文件路径。
    
    当工具输出过大需要截断时，先将完整内容保存到磁盘，
    后续模型可以通过 read_tool_output 工具回查完整内容。
    
    参数:
        tool_name (str): 工具名称，用于生成文件名前缀。
        payload (Any): 要保存的完整输出数据（通常是 dict 或 str）。
        
    返回:
        Path: 落盘后的文件路径。
    """
    # 确保输出目录存在
    dir_path = _ensure_dir()
    
    # 生成时间戳，格式如 "20260917_143022"
    ts = time.strftime("%Y%m%d_%H%M%S")
    # 生成 6 位随机 UUID 字符串，防止同一秒内多次调用产生文件名冲突
    uid = uuid.uuid4().hex[:6]
    # 组装文件名：工具名_时间戳_UUID.json
    filename = f"{tool_name}_{ts}_{uid}.json"
    # 拼接完整文件路径
    path = dir_path / filename

    # 将 payload 序列化为格式化的 JSON 字符串，并写入文件
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),  # ensure_ascii=False 保证中文正常显示，indent=2 美化输出
        encoding="utf-8",  # 使用 UTF-8 编码
    )
    
    # 返回文件路径对象
    return path


def _truncate_text(text: str, max_lines: int, max_bytes: int, head_tail: int) -> tuple[str, bool]:
    """
    按行数和字节数双重标准截断文本，保留头尾内容。
    
    参数:
        text (str): 原始文本。
        max_lines (int): 最大允许行数。
        max_bytes (int): 最大允许字节数（UTF-8 编码后）。
        head_tail (int): 截断时保留的头部和尾部行数。
        
    返回:
        tuple[str, bool]: (截断后的文本, 是否被截断)。
    """
    # 将文本按行分割成列表
    lines = text.splitlines()
    # 标记是否发生了截断
    truncated = False

    # --- 第一步：按行数截断 ---
    # 如果行数超过阈值，进行行截断
    if len(lines) > max_lines:
        truncated = True
        # 保留头部 N 行 + 省略提示 + 尾部 N 行
        lines = lines[:head_tail] + ["...（中间省略）..."] + lines[-head_tail:]

    # 将行列表重新拼接为字符串
    result = "\n".join(lines)

    # --- 第二步：按字节数截断 ---
    # 如果 UTF-8 编码后的字节数仍超过阈值，进行字节截断
    if len(result.encode("utf-8")) > max_bytes:
        truncated = True
        # 计算前后各保留的字节数（总阈值的一半）
        half = max_bytes // 2
        # 将字符串编码为字节串
        encoded = result.encode("utf-8")
        # 截取前半部分 + 省略提示 + 截取后半部分
        # decode 时使用 errors="ignore" 忽略截断处可能产生的不完整 UTF-8 字符
        result = (
            encoded[:half].decode("utf-8", errors="ignore")
            + "\n...（中间省略）...\n"
            + encoded[-half:].decode("utf-8", errors="ignore")
        )

    # 返回截断后的文本和截断标记
    return result, truncated


# ==================== 核心公开函数 ====================

def maybe_truncate(
    tool_name: str,
    data: dict[str, Any],
    text: str,
) -> tuple[dict[str, Any], str, str | None]:
    """
    对工具输出做截断判断。
    
    这是所有工具输出后统一调用的"守门员"函数。
    如果输出过大，则截断显示 + 完整落盘；否则原样返回。
    
    参数:
        tool_name (str): 工具名称，用于生成落盘文件名。
        data (dict[str, Any]): 工具返回的结构化数据。
        text (str): 工具返回的可读文本描述。
        
    返回:
        tuple[dict[str, Any], str, str | None]:
            - data: 可能被替换为 preview 的数据
            - text: 可能被截断的文本
            - output_path: 如果落盘了，返回文件路径字符串；否则 None
    """
    # 如果 text 为 None 或空字符串，使用空字符串
    raw_text = text or ""
    # 将 data 序列化为 JSON 字符串，用于计算字节大小
    raw_json = json.dumps(data, ensure_ascii=False)

    # --- 判断是否需要截断 ---
    # 两个条件满足任意一个就需要截断：
    # 1. 文本行数超过配置的最大行数
    # 2. JSON 数据的字节数超过配置的最大字节数
    need_truncate = (
        len(raw_text.splitlines()) > settings.tool_output_max_lines
        or len(raw_json.encode("utf-8")) > settings.tool_output_max_bytes
    )

    # --- 如果不需要截断，原样返回 ---
    if not need_truncate:
        return data, text, None

    # --- 如果需要截断，执行截断 + 落盘流程 ---
    
    # 1. 将完整输出落盘到 JSON 文件
    path = _save_full_output(tool_name, {"data": data, "text": text})

    # 2. 对文本进行截断处理
    truncated_text, _ = _truncate_text(
        raw_text,
        settings.tool_output_max_lines,        # 从配置读取最大行数
        settings.tool_output_max_bytes,        # 从配置读取最大字节数
        settings.tool_output_head_tail_lines,  # 从配置读取头尾保留行数
    )

    # 3. 构建 preview 数据，替换原始 data
    # 这样 LLM 看到的是截断后的预览，而不是完整数据
    preview = {
        "truncated": True,                     # 标记已被截断
        "output_path": str(path),              # 完整内容的文件路径
        "original_lines": len(raw_text.splitlines()),  # 原始行数（让 LLM 知道输出有多大）
        "preview": truncated_text,             # 截断后的预览文本
    }

    # 4. 构建通知文本，告知用户/LLM 输出已被截断，并提示如何回查
    notice = (
        f"⚠️ 输出过大已截断，完整内容见 {path}。"
        f"如需查看完整内容，请调用 read_tool_output 工具，path={path}"
    )

    # 返回 preview 数据、通知文本、文件路径
    return preview, notice, str(path)