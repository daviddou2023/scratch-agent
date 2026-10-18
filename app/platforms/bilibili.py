"""Minimal Bilibili public data provider."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.core.config import settings
from app.core.errors import ErrorCode
from app.tools.response import fail, ok, partial


@dataclass(frozen=True)
class BilibiliRef:
    bvid: str | None = None
    aid: int | None = None


def parse_bilibili_ref(value: str) -> BilibiliRef | None:
    text = value.strip()
    bvid_match = re.search(r"BV[0-9A-Za-z]+", text, re.IGNORECASE)
    if bvid_match:
        return BilibiliRef(bvid=bvid_match.group(0))

    aid_match = re.search(r"(?:^|\W)av(\d+)(?:$|\W)", text, re.IGNORECASE)
    if aid_match:
        return BilibiliRef(aid=int(aid_match.group(1)))

    parsed = urlparse(text)
    if parsed.netloc.lower().endswith("bilibili.com"):
        path_match = re.search(r"/video/(BV[0-9A-Za-z]+)", parsed.path, re.IGNORECASE)
        if path_match:
            return BilibiliRef(bvid=path_match.group(1))
    return None


class BilibiliProvider:
    def __init__(self, timeout: float | None = None) -> None:
        self.timeout = timeout or settings.bilibili_timeout
        self.user_agent = settings.bilibili_user_agent

    async def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urlencode(params)
        url = f"{endpoint}?{query}"

        def request() -> dict[str, Any]:
            req = Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    "Referer": "https://www.bilibili.com/",
                },
            )
            with urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            payload = await asyncio.to_thread(request)
        except HTTPError as exc:
            if exc.code == 429:
                raise RuntimeError(ErrorCode.RATE_LIMITED) from exc
            raise RuntimeError(f"HTTP_{exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(ErrorCode.NETWORK_ERROR) from exc

        if payload.get("code") != 0:
            raise RuntimeError(str(payload.get("message") or payload.get("code")))
        return payload

    async def fetch_metrics(self, video_ref: str) -> Any:
        ref = parse_bilibili_ref(video_ref)
        if ref is None:
            return fail(ErrorCode.INVALID_ARGUMENT, "无效的 B 站视频地址、BV 号或 AV 号")

        try:
            params = {"bvid": ref.bvid} if ref.bvid else {"aid": ref.aid}
            payload = await self._get_json(
                "https://api.bilibili.com/x/web-interface/view", params
            )
        except RuntimeError as exc:
            return fail(ErrorCode.BILIBILI_API_ERROR, f"B 站视频信息获取失败：{exc}")

        data = payload.get("data") or {}
        stat = data.get("stat") or {}
        metrics = {
            "platform": "bilibili",
            "video_id": data.get("bvid") or ref.bvid,
            "aid": data.get("aid") or ref.aid,
            "title": data.get("title", ""),
            "author": {"mid": data.get("owner", {}).get("mid"), "name": data.get("owner", {}).get("name")},
            "published_at": data.get("pubdate"),
            "duration": data.get("duration"),
            "views": stat.get("view"),
            "likes": stat.get("like"),
            "coins": stat.get("coin"),
            "favorites": stat.get("favorite"),
            "shares": stat.get("share"),
            "comments": stat.get("reply"),
            "danmaku": stat.get("danmaku"),
        }
        gaps = [key for key, value in metrics.items() if value is None]
        metrics["data_gaps"] = gaps
        status = "partial" if gaps else "success"
        if status == "partial":
            return partial(data=metrics, text="B 站指标部分缺失")
        return ok(data=metrics, text="已获取 B 站视频指标")

    async def fetch_comments(self, video_ref: str, limit: int = 500) -> Any:
        ref = parse_bilibili_ref(video_ref)
        if ref is None:
            return fail(ErrorCode.INVALID_ARGUMENT, "无效的 B 站视频地址、BV 号或 AV 号")

        metrics_response = await self.fetch_metrics(video_ref)
        aid = metrics_response.data.get("aid")
        if not aid:
            return fail(ErrorCode.VIDEO_NOT_FOUND, "无法解析 B 站视频 aid")

        comments: list[dict[str, Any]] = []
        page = 1
        page_size = min(20, limit)
        reported_total = None
        try:
            while len(comments) < limit:
                payload = await self._get_json(
                    "https://api.bilibili.com/x/v2/reply",
                    {"type": 1, "oid": aid, "pn": page, "ps": page_size, "sort": 2},
                )
                data = payload.get("data") or {}
                reported_total = (data.get("cursor") or {}).get("all_count")
                replies = data.get("replies") or []
                if not replies:
                    break
                for reply in replies:
                    member = reply.get("member") or {}
                    comments.append(
                        {
                            "id": str(reply.get("rpid")),
                            "user": member.get("uname", ""),
                            "text": (reply.get("content") or {}).get("message", ""),
                            "likes": reply.get("like", 0),
                            "time": reply.get("ctime"),
                        }
                    )
                    if len(comments) >= limit:
                        break
                if len(replies) < page_size:
                    break
                page += 1
        except RuntimeError as exc:
            if comments:
                return partial(
                    data={"comments": comments, "total": len(comments), "reported_total": reported_total},
                    text=f"B 站评论部分获取：{exc}",
                )
            return fail(ErrorCode.BILIBILI_API_ERROR, f"B 站评论获取失败：{exc}")

        return ok(
            data={"comments": comments, "total": len(comments), "reported_total": reported_total},
            text=f"已获取 {len(comments)} 条 B 站评论",
        )
