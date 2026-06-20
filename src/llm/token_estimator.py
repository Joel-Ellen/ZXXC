# -*- coding: utf-8 -*-
"""
TokenEstimator — 轻量级 Token 估算器
=====================================

无外部依赖，基于字符启发式估算：
  - 中文字符: ~1.5 chars/token
  - 英文/数字: ~4 chars/token
  - 混合平均: ~2.5 chars/token

5-10% 安全裕度，避免边缘溢出失败。

来源: backend/services/llm_service.py (merged)
"""
import re
from typing import Dict, List


class TokenEstimator:
    """轻量级 token 计数估算器。"""

    SAFETY_MARGIN = 0.05  # 5% safety buffer

    @staticmethod
    def estimate(text: str) -> int:
        """估算给定文本的 token 数量。"""
        if not text:
            return 0

        cjk_pattern = re.compile(r'[一-鿿㐀-䶿豈-﫿]')
        cjk_chars = len(cjk_pattern.findall(text))
        other_chars = len(text) - cjk_chars

        estimated = int(cjk_chars / 1.5 + other_chars / 4)
        return int(estimated * (1 + TokenEstimator.SAFETY_MARGIN))

    @staticmethod
    def estimate_messages(messages: List[Dict[str, str]]) -> int:
        """估算一组 chat messages 的总 token 数。"""
        total = 0
        for msg in messages:
            total += TokenEstimator.estimate(msg.get("content", ""))
            total += 4  # 每条消息的角色 + 格式化开销
        return total

    @staticmethod
    def estimate_system_overhead() -> int:
        """每次请求的系统格式化开销（估算 token）。"""
        return 20
