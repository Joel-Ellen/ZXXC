"""
AI Learning Assistant - Security Utilities
安全工具：JWT认证、密码哈希、内容审核、Prompt注入防御
"""
import re
import time
import hashlib
from typing import Optional, Tuple
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from loguru import logger
from config import SECURITY_CONFIG

# Password hashing
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
SECRET_KEY = "ai-learning-assistant-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


class PromptDefense:
    """
    Prompt injection defense - Prompt攻击防御
    Detects and sanitizes potentially malicious prompts.
    """

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

    @classmethod
    def detect_injection(cls, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Check for prompt injection attempts.
        Returns (is_injection, reason)
        """
        prompt_lower = prompt.lower()

        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                return True, f"Potential prompt injection detected: matched pattern"

        # Check for excessive length (possible DOS)
        if len(prompt) > SECURITY_CONFIG.get("max_prompt_length", 4000):
            return True, "Prompt exceeds maximum length"

        # Check for repetitive patterns (possible token overflow attack)
        words = prompt.split()
        if len(words) > 100:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                return True, "Repetitive content detected"

        return False, None

    @classmethod
    def sanitize(cls, prompt: str) -> str:
        """Remove potential injection patterns from prompt"""
        sanitized = prompt
        for pattern in cls.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
        return sanitized


class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict = {}

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """
        Check if request is allowed under rate limit.
        Returns (allowed, remaining_requests)
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if t > window_start]
        else:
            self._requests[key] = []

        # Check limit
        if len(self._requests[key]) >= self.max_requests:
            return False, 0

        self._requests[key].append(now)
        remaining = self.max_requests - len(self._requests[key])
        return True, remaining


# Singleton instances
_rate_limiter = RateLimiter(
    max_requests=SECURITY_CONFIG.get("rate_limit_per_minute", 30)
)
_prompt_defense = PromptDefense()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


def get_prompt_defense() -> PromptDefense:
    return _prompt_defense
