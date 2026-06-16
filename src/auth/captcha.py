# -*- coding: utf-8 -*-
"""
验证码生成器 — SVG 数学公式验证码
=================================
生成简单算术运算的 SVG 验证码图片，无需外部图片库依赖。
验证码答案存入内存，带 TTL 过期机制。
"""

from __future__ import annotations

import random
import time
import hashlib
from typing import Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CaptchaRecord:
    """单条验证码记录。"""

    token: str            # 唯一标识 (SHA256 hash)
    answer: str           # 正确答案
    expression: str       # 显示的表达式 (如 "3 + 5 = ?")
    created_at: float     # 创建时间戳
    ttl_seconds: int = 300  # 有效期 (默认 5 分钟)

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


class CaptchaGenerator:
    """SVG 数学公式验证码生成器。

    用法:
        >>> gen = CaptchaGenerator()
        >>> svg, token = gen.generate()
        >>> # 在 HTML 中嵌入 svg 字符串
        >>> gen.verify(token, "8")  # True if answer matches
    """

    EXPIRE_SECONDS: int = 300      # 5 分钟过期
    SVG_WIDTH: int = 180
    SVG_HEIGHT: int = 60
    SVG_FONT_SIZE: int = 28

    def __init__(self) -> None:
        self._records: Dict[str, CaptchaRecord] = {}
        self._cleanup_counter: int = 0

    # ------------------------------------------------------------------
    # 验证码生成
    # ------------------------------------------------------------------

    def generate(self) -> Tuple[str, str]:
        """生成一个 SVG 数学验证码。

        Returns:
            (svg_markup, token): SVG 字符串和验证令牌。
        """
        self._maybe_cleanup()

        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(["+", "-", "*"])

        if op == "+":
            answer = a + b
            expr = f"{a} + {b} = ?"
        elif op == "-":
            # 确保结果非负
            if a < b:
                a, b = b, a
            answer = a - b
            expr = f"{a} - {b} = ?"
        else:  # "*"
            # 限制乘数范围避免过大
            a = random.randint(1, 9)
            b = random.randint(1, 9)
            answer = a * b
            expr = f"{a} x {b} = ?"

        token = hashlib.sha256(
            f"{expr}{time.time()}{random.random()}".encode()
        ).hexdigest()[:16]

        self._records[token] = CaptchaRecord(
            token=token,
            answer=str(answer),
            expression=expr,
            created_at=time.time(),
            ttl_seconds=self.EXPIRE_SECONDS,
        )

        return self._render_svg(expr), token

    def verify(self, token: str, user_answer: str) -> bool:
        """验证用户输入的答案。

        Args:
            token: generate() 返回的令牌。
            user_answer: 用户输入的回答。

        Returns:
            True 若正确且在有效期内。
        """
        self._maybe_cleanup()
        record = self._records.get(token)
        if record is None:
            return False
        if record.is_expired():
            del self._records[token]
            return False
        # 验证后立即删除（一次性使用）
        is_correct = record.answer.strip() == user_answer.strip()
        del self._records[token]
        return is_correct

    # ------------------------------------------------------------------
    # SVG 渲染
    # ------------------------------------------------------------------

    def _render_svg(self, expression: str) -> str:
        """将表达式渲染为 SVG 图片标记。

        使用干扰线 + 背景噪点增加视觉混淆。
        """
        w, h = self.SVG_WIDTH, self.SVG_HEIGHT
        fs = self.SVG_FONT_SIZE

        # 干扰线
        noise_lines = ""
        for _ in range(3):
            x1 = random.randint(10, w - 10)
            y1 = random.randint(5, h - 5)
            x2 = random.randint(10, w - 10)
            y2 = random.randint(5, h - 5)
            color = random.choice(["#d0d0d0", "#e0e0e0", "#c0c0c0"])
            noise_lines += (
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{color}" stroke-width="1.5"/>'
            )

        # 背景点
        dots = ""
        for _ in range(15):
            cx = random.randint(5, w - 5)
            cy = random.randint(5, h - 5)
            r = random.uniform(0.8, 2.0)
            dots += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ddd"/>'

        # 随机颜色文字
        text_color = random.choice(["#2c3e50", "#34495e", "#1a1a2e", "#16213e"])

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#f8f9fa" rx="6"/>'
            f"{dots}"
            f"{noise_lines}"
            f'<text x="{w // 2}" y="{h // 2 + fs // 4}" '
            f'font-size="{fs}px" font-family="Arial, sans-serif" font-weight="bold" '
            f'fill="{text_color}" text-anchor="middle" dominant-baseline="middle" '
            f'letter-spacing="3">'
            f"{expression}</text>"
            f"</svg>"
        )
        return svg

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _maybe_cleanup(self) -> None:
        """定期清理过期记录（每 50 次调用执行一次）。"""
        self._cleanup_counter += 1
        if self._cleanup_counter < 50:
            return
        self._cleanup_counter = 0
        expired = [t for t, r in self._records.items() if r.is_expired()]
        for t in expired:
            del self._records[t]
