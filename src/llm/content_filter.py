# -*- coding: utf-8 -*-
"""
ContentFilter — 内容安全过滤
============================

对 LLM 输入/输出进行敏感词和模式检测。

来源: backend/services/llm_service.py (merged)
"""
import re as _regex
from typing import Optional, Tuple


# 内置敏感词列表（可覆盖）
DEFAULT_SENSITIVE_KEYWORDS = [
    "违法", "暴力", "色情", "歧视", "政治敏感",
    "hack", "exploit", "attack", "malware", "phishing",
]


class ContentFilter:
    """内容安全过滤器。"""

    SENSITIVE_PATTERNS = [
        r"(违法|暴力|色情|歧视|政治敏感)",
        r"(hack|exploit|attack|malware|phishing)",
    ]

    @classmethod
    def check_content(
        cls,
        text: str,
        extra_keywords: Optional[list] = None,
    ) -> Tuple[bool, Optional[str]]:
        """检查内容是否含有敏感/不安全信息。

        Returns:
            (is_safe, reason_if_unsafe)
        """
        if not text:
            return True, None

        keywords = DEFAULT_SENSITIVE_KEYWORDS + (extra_keywords or [])

        for keyword in keywords:
            if keyword.lower() in text.lower():
                return False, f"Content contains sensitive keyword: {keyword}"

        for pattern in cls.SENSITIVE_PATTERNS:
            if _regex.search(pattern, text, _regex.IGNORECASE):
                return False, "Content matches sensitive pattern"

        return True, None

    @classmethod
    def sanitize(
        cls,
        text: str,
        extra_keywords: Optional[list] = None,
    ) -> str:
        """移除/替换敏感内容。"""
        keywords = DEFAULT_SENSITIVE_KEYWORDS + (extra_keywords or [])
        for keyword in keywords:
            text = text.replace(keyword, "[filtered]")
        return text
