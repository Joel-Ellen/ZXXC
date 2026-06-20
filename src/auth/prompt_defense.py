# -*- coding: utf-8 -*-
"""
PromptDefense — Prompt 注入攻击防御
====================================

检测和清洗潜在的恶意 Prompt。

来源: backend/utils/security.py (merged)
"""
import re
from typing import Optional, Tuple


# 默认安全配置
DEFAULT_MAX_PROMPT_LENGTH = 4000
DEFAULT_MIN_UNIQUE_RATIO = 0.3


class PromptDefense:
    """Prompt 注入检测与防御。"""

    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions?",
        r"(forget|disregard|override)\s+(your|system)\s+(prompt|instructions?)",
        r"you\s+are\s+(now|no\s+longer)\s+\w+",
        r"act\s+as\s+(if\s+you\s+are|a\s+different)\s+\w+",
        r"system\s*prompt\s*:",
        r"<<\s*SYS\s*>>",
        r"\[system\s*instruction\]",
        r"pretend\s+(to\s+be|you\s+are)",
        r"roleplay\s+as",
        r"do\s+not\s+follow\s+your",
        r"bypass\s+(your\s+)?(restrictions|limitations|rules|safeguards)",
    ]

    def __init__(
        self,
        max_prompt_length: int = DEFAULT_MAX_PROMPT_LENGTH,
        min_unique_ratio: float = DEFAULT_MIN_UNIQUE_RATIO,
    ):
        self.max_prompt_length = max_prompt_length
        self.min_unique_ratio = min_unique_ratio

    def detect_injection(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """检查是否存在 Prompt 注入攻击。

        Returns:
            (is_injection, reason_if_any)
        """
        if not prompt:
            return False, None

        prompt_lower = prompt.lower()

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                return True, "Potential prompt injection detected: matched pattern"

        if len(prompt) > self.max_prompt_length:
            return True, f"Prompt exceeds maximum length ({self.max_prompt_length})"

        words = prompt.split()
        if len(words) > 100:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < self.min_unique_ratio:
                return True, "Repetitive content detected (possible token overflow attack)"

        return False, None

    @classmethod
    def sanitize(cls, prompt: str) -> str:
        """移除 prompt 中的注入模式。"""
        sanitized = prompt
        for pattern in cls.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
        return sanitized


# 单例
_prompt_defense: Optional[PromptDefense] = None


def get_prompt_defense() -> PromptDefense:
    global _prompt_defense
    if _prompt_defense is None:
        _prompt_defense = PromptDefense()
    return _prompt_defense
