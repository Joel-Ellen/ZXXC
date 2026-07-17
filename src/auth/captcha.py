# -*- coding: utf-8 -*-
"""
验证码生成器 — SVG 数学公式验证码
=================================
生成简单算术运算的 SVG 验证码图片，无需外部图片库依赖。
开发环境可使用进程内 TTL 存储；生产环境使用共享 Redis，保证多副本可验证。
"""

from __future__ import annotations

import random
import secrets
import string
import time
import threading
from typing import Any, Dict, Tuple
from dataclasses import dataclass


class CaptchaBackendUnavailable(RuntimeError):
    """Raised when the required shared captcha backend cannot be used."""


@dataclass
class CaptchaRecord:
    """单条验证码记录。"""

    token: str            # 不可预测的一次性标识
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
    MAX_RECORDS: int = 10_000

    def __init__(self, *, redis_client: Any = None, require_shared: bool = False) -> None:
        if require_shared and redis_client is None:
            raise CaptchaBackendUnavailable("shared captcha backend is required")
        self._redis = redis_client
        self._records: Dict[str, CaptchaRecord] = {}
        self._cleanup_counter: int = 0
        self._lock = threading.RLock()

    @property
    def uses_shared_backend(self) -> bool:
        return self._redis is not None

    @staticmethod
    def _redis_key(token: str) -> str:
        return f"eduagent:auth:captcha:{token}"

    # ------------------------------------------------------------------
    # 验证码生成
    # ------------------------------------------------------------------

    def generate(self) -> Tuple[str, str]:
        """生成一个 SVG 数学验证码。

        Returns:
            (svg_markup, token): SVG 字符串和验证令牌。
        """
        self._maybe_cleanup()

        a = secrets.randbelow(20) + 1
        b = secrets.randbelow(20) + 1
        op = secrets.choice(["+", "-", "*"])

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
            a = secrets.randbelow(9) + 1
            b = secrets.randbelow(9) + 1
            answer = a * b
            expr = f"{a} x {b} = ?"

        if self._redis is not None:
            token = ""
            for _attempt in range(3):
                candidate = secrets.token_hex(8)
                try:
                    stored = self._redis.set(
                        self._redis_key(candidate),
                        str(answer),
                        ex=self.EXPIRE_SECONDS,
                        nx=True,
                    )
                except Exception as exc:
                    raise CaptchaBackendUnavailable("shared captcha backend unavailable") from exc
                if stored:
                    token = candidate
                    break
            if not token:
                raise CaptchaBackendUnavailable("captcha token collision")
        else:
            token = secrets.token_hex(8)
            with self._lock:
                if len(self._records) >= self.MAX_RECORDS:
                    oldest = min(self._records.values(), key=lambda record: record.created_at)
                    self._records.pop(oldest.token, None)
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
        normalized_token = str(token or "").strip().lower()
        if len(normalized_token) != 16 or any(
            character not in string.hexdigits for character in normalized_token
        ):
            return False
        normalized_answer = str(user_answer or "").strip()
        if self._redis is not None:
            try:
                expected = self._redis.getdel(self._redis_key(normalized_token))
            except Exception as exc:
                raise CaptchaBackendUnavailable("shared captcha backend unavailable") from exc
            if isinstance(expected, bytes):
                expected = expected.decode("utf-8")
            return bool(
                expected is not None
                and secrets.compare_digest(str(expected).strip(), normalized_answer)
            )

        self._maybe_cleanup()
        with self._lock:
            record = self._records.get(normalized_token)
            if record is None:
                return False
            if record.is_expired():
                del self._records[normalized_token]
                return False
            # 验证后立即删除（一次性使用）
            is_correct = secrets.compare_digest(record.answer.strip(), normalized_answer)
            del self._records[normalized_token]
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
        if self._redis is not None:
            return
        with self._lock:
            self._cleanup_counter += 1
            if self._cleanup_counter < 50:
                return
            self._cleanup_counter = 0
            expired = [token for token, record in self._records.items() if record.is_expired()]
            for token in expired:
                del self._records[token]
