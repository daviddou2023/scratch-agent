# 导入 re 模块，用于使用正则表达式匹配广告和无意义评论
import re

# 从 pydantic 导入 BaseModel 和 Field，用于定义和校验工具入参
from pydantic import BaseModel, Field

# 导入项目中自定义的错误码枚举
from app.core.errors import ErrorCode
# 导入统一的工具响应数据结构
from app.core.schemas import ToolResponse
# 导入 Tool 基类，所有自定义工具都需要继承它
from app.tools.base import Tool
# 导入封装好的标准响应辅助函数：成功(ok)、失败(fail)、部分成功(partial)
from app.tools.response import fail, ok, partial

# 定义广告 / 引流关键词的正则表达式列表
# 包含常见的加微信、私信、领取资料、网址链接等引流话术
AD_PATTERNS = [
    r"加微信",
    r"加微",
    r"私信",
    r"领取资料",
    r"http[s]?://",
    r"www\.",
    r"VX[:：]",
    r"vx[:：]",
]

# 定义无意义评论的正则表达式列表
# 包含纯笑声（如"哈哈哈"）、纯标点符号、极短的无意义字母数字组合等
NOISE_PATTERNS = [
    r"^哈+$",
    r"^哈{3,}$",
    r"^[。，！？\s]+$",
    r"^[a-zA-Z0-9]{1,3}$",
]


def _is_ad(text: str) -> bool:
    """
    判断一段文本是否为广告。
    
    参数:
        text (str): 待检测的文本。
        
    返回:
        bool: 如果匹配到任意一个广告正则表达式，返回 True，否则返回 False。
    """
    # 遍历所有广告正则，只要有一个匹配成功（忽略大小写），即判定为广告
    return any(re.search(p, text, re.IGNORECASE) for p in AD_PATTERNS)


def _is_noise(text: str) -> bool:
    """
    判断一段文本是否为无意义评论。
    
    参数:
        text (str): 待检测的文本。
        
    返回:
        bool: 如果匹配到任意一个无意义正则表达式，返回 True，否则返回 False。
    """
    # 去除文本首尾的空白字符
    stripped = text.strip()
    # 如果去除空白后长度小于等于 1，直接判定为无意义
    if len(stripped) <= 1:
        return True
    # 遍历所有无意义正则，只要有一个匹配成功，即判定为无意义评论
    return any(re.search(p, stripped) for p in NOISE_PATTERNS)


def _mask_user(user: str) -> str:
    """
    对用户昵称进行脱敏处理，保护用户隐私。
    规则：保留首尾字符，中间部分用星号 * 替换。
    
    参数:
        user (str): 原始用户昵称。
        
    返回:
        str: 脱敏后的用户昵称。
    """
    # 如果昵称长度小于等于 2，只保留第一个字符，后面补一个星号
    if len(user) <= 2:
        return user[0] + "*"
    # 否则，保留首字符 + 中间全部替换为星号 + 保留末字符
    return user[0] + "*" * (len(user) - 2) + user[-1]


class CleanCommentsArgs(BaseModel):
    """
    定义 clean_comments 工具的入参结构。
    """
    # 原始评论列表，必填字段，每个评论是一个字典
    comments: list[dict] = Field(..., description="原始评论列表")
    # 是否过滤广告，默认为 True
    filter_ads: bool = Field(True, description="是否过滤广告")
    # 是否过滤无意义评论，默认为 True
    filter_noise: bool = Field(True, description="是否过滤无意义评论")


class CleanCommentsTool(Tool):
    """
    评论清洗工具类。
    继承自 Tool 基类，负责对原始评论进行去重、过滤广告、过滤无意义内容以及用户脱敏。
    """
    # 工具的唯一标识名称
    name = "clean_comments"
    # 工具的功能描述
    description = "清洗评论：去重、过滤广告、过滤无意义评论、脱敏。"
    # 绑定前面定义的入参校验模型
    args_schema = CleanCommentsArgs

    async def run(
        self,
        comments: list[dict],
        filter_ads: bool = True,
        filter_noise: bool = True,
    ) -> ToolResponse:
        """
        执行评论清洗的核心逻辑。
        
        参数:
            comments (list[dict]): 原始评论列表。
            filter_ads (bool): 是否过滤广告。
            filter_noise (bool): 是否过滤无意义评论。
            
        返回:
            ToolResponse: 封装了清洗后结果和统计信息的响应对象。
        """
        # --- 1. 基础参数校验 ---
        # 检查传入的 comments 是否确实是一个列表，如果不是则返回参数错误
        if not isinstance(comments, list):
            return fail(ErrorCode.INVALID_ARGUMENT, "comments 必须是列表")

        # --- 2. 处理空列表 ---
        # 如果传入的评论列表为空，直接返回成功，无需进行后续清洗
        if len(comments) == 0:
            return ok(data={"comments": [], "total": 0}, text="没有需要清洗的评论")

        # --- 3. 初始化清洗变量 ---
        seen = set()          # 用于记录已经出现过的评论文本，实现去重
        cleaned = []          # 用于存储清洗后保留下来的有效评论
        removed_ads = 0       # 计数器：被过滤掉的广告数量
        removed_noise = 0     # 计数器：被过滤掉的无意义评论数量
        removed_dup = 0       # 计数器：被过滤掉的重复评论数量

        # --- 4. 遍历并清洗每条评论 ---
        for c in comments:
            # 获取评论文本，转为字符串并去除首尾空白
            text = str(c.get("text", "")).strip()
            # 如果文本为空，直接跳过
            if not text:
                continue

            # 去重逻辑：使用文本内容作为去重键
            key = text
            if key in seen:
                removed_dup += 1  # 如果已经出现过，重复计数加 1，跳过当前评论
                continue
            seen.add(key)         # 将当前文本加入已出现集合

            # 过滤广告：如果开启了广告过滤且当前文本被判定为广告
            if filter_ads and _is_ad(text):
                removed_ads += 1  # 广告计数加 1，跳过当前评论
                continue

            # 过滤无意义评论：如果开启了无意义过滤且当前文本被判定为无意义
            if filter_noise and _is_noise(text):
                removed_noise += 1  # 无意义计数加 1，跳过当前评论
                continue

            # 如果评论通过了所有过滤，进行脱敏处理并加入有效列表
            cleaned.append(
                {
                    "id": c.get("id"),                        # 保留评论 ID
                    "user": _mask_user(str(c.get("user", ""))), # 对用户昵称进行脱敏
                    "text": text,                             # 保留评论文本
                    "likes": c.get("likes", 0),               # 保留点赞数，默认为 0
                    "time": c.get("time"),                    # 保留评论时间
                }
            )

        # --- 5. 构建统计信息 ---
        stats = {
            "original": len(comments),  # 原始评论总数
            "cleaned": len(cleaned),    # 清洗后保留的评论数
            "removed_ads": removed_ads, # 被过滤的广告数
            "removed_noise": removed_noise, # 被过滤的无意义评论数
            "removed_dup": removed_dup, # 被过滤的重复评论数
        }

        # --- 6. 返回清洗结果 ---
        # 如果清洗后有效评论为 0，返回部分成功（partial）响应
        # 这属于业务上的正常情况（所有评论都被合理过滤了），而不是系统错误
        if len(cleaned) == 0:
            return partial(
                data={"comments": [], "stats": stats},
                text="清洗后有效评论为 0",
                error=None,
            )

        # 如果有有效评论，返回成功（ok）响应，包含清洗后的数据和详细统计信息
        return ok(
            data={"comments": cleaned, "stats": stats},
            text=f"清洗完成：{len(comments)} → {len(cleaned)}",
        )