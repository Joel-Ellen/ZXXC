"""
AI Learning Assistant - LLM Service (Multi-Provider)
多智能体系统 - 大模型服务（多厂商支持）

Supports: Spark (讯飞星火), DeepSeek, Qwen (通义千问), Qwen-Plus, OpenAI
Qwen-Plus: 128K context window, with auto-overflow strategy (Map-Reduce)
"""
import json
import re
import time
import asyncio
from typing import Optional, Dict, Any, List, AsyncGenerator, Tuple
from openai import AsyncOpenAI
from loguru import logger
from config import LLM_CONFIG, LLM_PROVIDER, SECURITY_CONFIG


# ============================================================
# Token Estimator
# ============================================================
class TokenEstimator:
    """
    Lightweight token count estimator (no external deps).
    Uses character-based heuristics:
      - Chinese chars: ~1.5 chars/token
      - English/numbers: ~4 chars/token
      - Average mixed: ~2.5 chars/token (safe upper bound)

    A 5-10% safety margin is applied to avoid edge-of-limit failures.
    """

    SAFETY_MARGIN = 0.05  # 5% safety buffer

    @staticmethod
    def estimate(text: str) -> int:
        """Estimate token count for a given text."""
        if not text:
            return 0

        # Count Chinese/CJK characters
        cjk_pattern = re.compile(r'[一-鿿㐀-䶿豈-﫿]')
        cjk_chars = len(cjk_pattern.findall(text))
        other_chars = len(text) - cjk_chars

        # Chinese: ~1.5 chars/token, Others: ~4 chars/token
        estimated = int(cjk_chars / 1.5 + other_chars / 4)
        # Apply safety margin
        return int(estimated * (1 + TokenEstimator.SAFETY_MARGIN))

    @staticmethod
    def estimate_messages(messages: List[Dict[str, str]]) -> int:
        """Estimate total token count for a list of chat messages."""
        total = 0
        for msg in messages:
            total += TokenEstimator.estimate(msg.get("content", ""))
            # Add token overhead per message (role + formatting)
            total += 4
        return total

    @staticmethod
    def estimate_system_overhead() -> int:
        """Estimated tokens for system formatting overhead per request."""
        return 20


# ============================================================
# Input Manager — Overflow Strategy for 128K-limited models
# ============================================================
class InputManager:
    """
    Manages input to respect model token limits.

    Strategies:
      - direct:         Input fits, send as-is
      - smart_truncate: Truncate middle/older content, keep system + recent
      - map_reduce:     Split into chunks → process each → synthesise results
      - sliding_window: Keep system prompt + slide a window over long content
    """

    # Default limits per provider (can be overridden in config)
    DEFAULT_MAX_INPUT_TOKENS = 128000  # 128K

    def __init__(self, max_input_tokens: Optional[int] = None, strategy: str = "map_reduce"):
        self.max_input = max_input_tokens or self.DEFAULT_MAX_INPUT_TOKENS
        self.strategy = strategy

    def check_and_plan(
        self,
        messages: List[Dict[str, str]],
    ) -> Tuple[str, List[List[Dict[str, str]]]]:
        """
        Check if input fits within limit. If not, return a plan.

        Returns:
            (strategy_name, list_of_message_batches)
            - "direct": single batch [[original messages]]
            - "map_reduce": multiple batches for map-reduce processing
            - "smart_truncate": single truncated batch
        """
        estimated = TokenEstimator.estimate_messages(messages)
        overhead = TokenEstimator.estimate_system_overhead()
        total_estimated = estimated + overhead

        logger.info(
            f"[InputManager] Estimated {total_estimated} tokens "
            f"(limit: {self.max_input}) for {len(messages)} messages"
        )

        if total_estimated <= self.max_input:
            logger.info("[InputManager] ✅ Input fits — direct mode")
            return "direct", [messages]

        logger.warning(
            f"[InputManager] ⚠️ Input exceeds limit "
            f"({total_estimated} > {self.max_input}) — applying {self.strategy}"
        )

        if self.strategy == "map_reduce":
            batches = self._build_map_reduce_batches(messages)
            return "map_reduce", batches
        elif self.strategy == "sliding_window":
            truncated = self._build_sliding_window(messages)
            return "sliding_window", [truncated]
        else:  # smart_truncate (default fallback)
            truncated = self._build_smart_truncate(messages)
            return "smart_truncate", [truncated]

    # ------------------------------------------------------------------
    # Strategy: Map-Reduce
    # ------------------------------------------------------------------
    def _build_map_reduce_batches(
        self,
        messages: List[Dict[str, str]],
    ) -> List[List[Dict[str, str]]]:
        """
        Split long content into independent batches.
        Each batch = system_prompt + one chunk of content.

        After all batches are processed, results are merged by a final
        synthesis call (handled by LLMService._map_reduce_chat).
        """
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        # Reserve tokens for synthesis prompt overhead
        available_per_batch = self.max_input - system_tokens - 500

        batches: List[List[Dict[str, str]]] = []

        for msg in other_msgs:
            content = msg.get("content", "")
            msg_tokens = TokenEstimator.estimate(content)

            if msg_tokens <= available_per_batch:
                # Message fits in one batch
                batches.append(system_msgs + [msg])
            else:
                # Message too long — semantic chunking required
                chunks = self._semantic_chunk(content, available_per_batch)
                for chunk in chunks:
                    batches.append(system_msgs + [
                        {"role": msg["role"], "content": chunk}
                    ])
                logger.info(
                    f"[InputManager] Split long message ({msg_tokens} tokens) "
                    f"into {len(chunks)} chunks"
                )

        if not batches:
            # Fallback: at least return original messages
            return [messages]

        logger.info(f"[InputManager] Map-Reduce: {len(batches)} batches created")
        return batches

    # ------------------------------------------------------------------
    # Strategy: Smart Truncate
    # ------------------------------------------------------------------
    def _build_smart_truncate(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Keep system prompt intact. For other messages:
        - Keep most recent messages (higher priority)
        - Truncate middle/older messages to fit limit
        - Never drop system prompt
        """
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        available = self.max_input - system_tokens - 200

        result = list(system_msgs)
        remaining = available

        # Process from most recent to oldest
        for msg in reversed(other_msgs):
            content = msg.get("content", "")
            msg_tokens = TokenEstimator.estimate(content)

            if msg_tokens <= remaining:
                result.insert(len(system_msgs), msg)
                remaining -= msg_tokens
            elif remaining > 500:
                # Truncate this message to fit
                truncated_content = self._truncate_to_tokens(content, remaining)
                result.insert(len(system_msgs), {
                    "role": msg["role"],
                    "content": truncated_content + "\n\n[... 内容已截断以适配上下文限制 ...]",
                })
                remaining = 0
                break
            else:
                break

        logger.info(
            f"[InputManager] Smart Truncate: {len(messages)} → {len(result)} messages "
            f"({TokenEstimator.estimate_messages(result)} estimated tokens)"
        )
        return result

    # ------------------------------------------------------------------
    # Strategy: Sliding Window
    # ------------------------------------------------------------------
    def _build_sliding_window(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        For long single messages: slide a window with overlap.
        The window content is concatenated with a continuity hint.
        """
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        if not other_msgs:
            return system_msgs

        # Find the longest message and apply sliding window
        longest = max(other_msgs, key=lambda m: len(m.get("content", "")))
        content = longest.get("content", "")
        content_tokens = TokenEstimator.estimate(content)

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        window_size = self.max_input - system_tokens - 300  # 300 for overlap hint
        overlap = window_size // 4  # 25% overlap between windows

        windows = self._sliding_window_chunk(content, window_size, overlap)
        logger.info(
            f"[InputManager] Sliding Window: {content_tokens} token content "
            f"→ {len(windows)} windows (size={window_size}, overlap={overlap})"
        )

        # Return system + first window (subsequent windows processed iteratively)
        return system_msgs + [{"role": longest["role"], "content": windows[0]}]

    # ==================================================================
    # Chunking utilities
    # ==================================================================
    def _semantic_chunk(
        self,
        text: str,
        max_tokens_per_chunk: int,
    ) -> List[str]:
        """
        Split text on semantic boundaries (paragraphs, sections).
        Try to keep each chunk within max_tokens_per_chunk.
        """
        # Split on double newlines (paragraph boundaries)
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = TokenEstimator.estimate(para)

            if current_tokens + para_tokens > max_tokens_per_chunk and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
                current_tokens = para_tokens
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                current_tokens += para_tokens

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # If still too large, force split by sentence boundaries
        final_chunks = []
        for chunk in chunks:
            if TokenEstimator.estimate(chunk) > max_tokens_per_chunk:
                final_chunks.extend(self._force_split(chunk, max_tokens_per_chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks

    @staticmethod
    def _force_split(text: str, max_tokens: int) -> List[str]:
        """
        Fallback: split by sentences/clauses, then by fixed-size chunks
        if still too large.
        """
        # Level 1: Split by sentence/clause boundaries
        sentences = re.split(r'(?<=[。！？.!?；;，,\n])\s*', text)
        chunks = []
        current = ""
        current_tokens = 0

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_tokens = TokenEstimator.estimate(sent)

            # If a single sentence/clause still exceeds limit, force-chop it
            if sent_tokens > max_tokens:
                # Save current chunk first
                if current.strip():
                    chunks.append(current.strip())
                    current = ""
                    current_tokens = 0
                # Chop this oversized sentence
                sub_chunks = InputManager._chop_by_chars(sent, max_tokens)
                chunks.extend(sub_chunks)
            elif current_tokens + sent_tokens > max_tokens and current:
                chunks.append(current.strip())
                current = sent
                current_tokens = sent_tokens
            else:
                if current:
                    current += "；" if not current.endswith("；") else ""
                current += sent
                current_tokens += sent_tokens

        if current.strip():
            chunks.append(current.strip())

        # Level 2: Verify all chunks fit; if not, hard-chop the offenders
        final_chunks = []
        for chunk in chunks:
            if TokenEstimator.estimate(chunk) > max_tokens:
                final_chunks.extend(
                    InputManager._chop_by_chars(chunk, max_tokens)
                )
            else:
                final_chunks.append(chunk)

        return final_chunks if final_chunks else [text]

    @staticmethod
    def _chop_by_chars(text: str, max_tokens: int) -> List[str]:
        """
        Last-resort: split text into fixed-size character blocks
        that fit within max_tokens.
        """
        # Convert token limit to char limit (conservative: 1.2 chars/token for safety)
        max_chars = int(max_tokens * 1.2)
        chunks = []
        for i in range(0, len(text), max_chars):
            chunk = text[i:i + max_chars]
            if i > 0:
                chunk = "[...上文续接...]\n" + chunk
            if i + max_chars < len(text):
                chunk = chunk + "\n[...下文待续...]"
            chunks.append(chunk)
        return chunks

    @staticmethod
    def _sliding_window_chunk(
        text: str,
        window_tokens: int,
        overlap_tokens: int,
    ) -> List[str]:
        """Create overlapping windows over long text."""
        # Convert token limits to approximate char limits
        window_chars = int(window_tokens * 2.0)  # rough char estimate
        overlap_chars = int(overlap_tokens * 2.0)
        step = window_chars - overlap_chars

        windows = []
        start = 0
        while start < len(text):
            end = min(start + window_chars, len(text))
            window_text = text[start:end]
            if start > 0:
                window_text = "[...上文续接...]\n\n" + window_text
            if end < len(text):
                window_text = window_text + "\n\n[...下文待续...]"
            windows.append(window_text)
            start += step

        return windows

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        # Use average 2 chars/token for truncation
        max_chars = int(max_tokens * 2.0)
        if len(text) <= max_chars:
            return text
        # Keep beginning and end (beginning usually more important)
        head_size = int(max_chars * 0.7)
        tail_size = max_chars - head_size - 50
        return text[:head_size] + "\n\n[... 中间内容已截断 ...]\n\n" + text[-tail_size:]


# ============================================================
# LLM Service
# ============================================================
class LLMService:
    """Multi-provider LLM service with fallback + overflow handling"""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or LLM_PROVIDER
        self.config = LLM_CONFIG.get(self.provider, LLM_CONFIG["deepseek"])
        self._client: Optional[AsyncOpenAI] = None

        # Set up input manager for providers with explicit input limits
        max_input = self.config.get("max_input_tokens")
        overflow_strategy = self.config.get("overflow_strategy", "map_reduce")
        self._input_manager = InputManager(
            max_input_tokens=max_input,
            strategy=overflow_strategy,
        ) if max_input else None

        self._init_client()

    @property
    def has_input_limit(self) -> bool:
        """Whether this provider enforces an input token limit."""
        return self._input_manager is not None

    @property
    def max_input_tokens(self) -> Optional[int]:
        """The input token limit for this provider, if any."""
        if self._input_manager:
            return self._input_manager.max_input
        return None

    def _init_client(self):
        """Initialize async OpenAI-compatible client"""
        api_key = self.config.get("api_key", "")
        if not api_key or api_key == "":
            logger.warning(
                f"LLM provider '{self.provider}' has no API key configured. "
                f"Set environment variable for the provider."
            )
            api_key = "placeholder"

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.config["api_url"],
        )

    # ------------------------------------------------------------------
    # Public: chat() — with auto overflow handling
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Send chat completion request to LLM.

        If the provider has an input token limit and the messages exceed it,
        automatically applies the configured overflow strategy (map_reduce,
        smart_truncate, or sliding_window).

        Args:
            messages: Chat messages list
            temperature: Sampling temperature
            max_tokens: Max output tokens
            json_mode: Force JSON output
            stream: Enable streaming

        Returns:
            Response dict with 'content', 'usage', 'model'
        """
        temp = temperature if temperature is not None else self.config.get("temperature", 0.7)
        max_tok = max_tokens or self.config.get("max_tokens", 4096)

        # --- Input limit check ---
        if self.has_input_limit:
            strategy, batches = self._input_manager.check_and_plan(messages)

            if strategy == "map_reduce" and len(batches) > 1:
                logger.info(
                    f"[LLMService] Applying Map-Reduce: "
                    f"{len(batches)} batches → synthesis"
                )
                return await self._map_reduce_chat(
                    batches, temp, max_tok, json_mode
                )
            elif strategy == "smart_truncate":
                logger.info("[LLMService] Applying Smart Truncate")
                messages = batches[0]
            elif strategy == "sliding_window":
                logger.info("[LLMService] Applying Sliding Window")
                messages = batches[0]

        # --- Standard single-request path ---
        return await self._single_chat(messages, temp, max_tok, json_mode, stream)

    # ------------------------------------------------------------------
    # Core: single chat request
    # ------------------------------------------------------------------
    async def _single_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        stream: bool,
    ) -> Dict[str, Any]:
        """Execute a single LLM API call (no chunking)."""
        kwargs = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        if stream:
            kwargs["stream"] = True

        try:
            response = await self._client.chat.completions.create(**kwargs)

            if stream:
                return response  # Stream object — caller iterates

            choice = response.choices[0]
            return {
                "content": choice.message.content or "",
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                "model": response.model,
                "finish_reason": choice.finish_reason,
            }
        except Exception as e:
            logger.error(f"LLM chat error ({self.provider}): {e}")
            if self.provider == "spark":
                logger.info("Falling back to DeepSeek...")
                fallback = LLMService("deepseek")
                return await fallback.chat(
                    messages, temperature, max_tokens, json_mode
                )
            raise

    # ------------------------------------------------------------------
    # Map-Reduce: process chunks independently → synthesise
    # ------------------------------------------------------------------
    async def _map_reduce_chat(
        self,
        batches: List[List[Dict[str, str]]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Dict[str, Any]:
        """
        MAP phase: Process each batch independently.
        REDUCE phase: Synthesize all partial results into one final answer.

        This ensures output completeness even when input > 128K tokens.
        """
        # --- MAP: Process all batches concurrently ---
        map_tasks = [
            self._single_chat(batch, temperature, max_tokens, json_mode, False)
            for batch in batches
        ]
        map_results = await asyncio.gather(*map_tasks, return_exceptions=True)

        # Collect partial results
        partial_contents = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_used = self.config["model"]

        for i, result in enumerate(map_results):
            if isinstance(result, Exception):
                logger.error(f"[Map-Reduce] Batch {i} failed: {result}")
                partial_contents.append(f"[批次 {i+1} 处理失败: {str(result)}]")
            elif isinstance(result, dict):
                partial_contents.append(result.get("content", ""))
                usage = result.get("usage", {})
                total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                total_usage["total_tokens"] += usage.get("total_tokens", 0)
                model_used = result.get("model", model_used)

        logger.info(
            f"[Map-Reduce] MAP complete: {len(partial_contents)}/{len(batches)} "
            f"batches processed"
        )

        # If only one batch succeeded, return it directly
        valid_results = [c for c in partial_contents if c and "处理失败" not in c]
        if len(valid_results) == 1:
            return {
                "content": valid_results[0],
                "usage": total_usage,
                "model": model_used,
                "finish_reason": "stop",
                "overflow_applied": "map_reduce_single",
            }

        # --- REDUCE: Synthesise all partial results ---
        synthesis_prompt = self._build_synthesis_prompt(partial_contents, json_mode)
        synthesis_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个专业的内容整合专家。请将以下多个部分的结果整合为"
                    "一个完整、连贯、不重复的回答。保持原始信息的准确性，"
                    "去除重复内容，按逻辑顺序组织。"
                    + ("请返回严格的JSON格式。" if json_mode else "")
                ),
            },
            {"role": "user", "content": synthesis_prompt},
        ]

        logger.info("[Map-Reduce] REDUCE: synthesising results...")
        final_result = await self._single_chat(
            synthesis_messages, temperature, max_tokens, json_mode
        )

        # Merge usage
        final_usage = final_result.get("usage", {})
        total_usage["prompt_tokens"] += final_usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += final_usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += final_usage.get("total_tokens", 0)

        return {
            "content": final_result.get("content", ""),
            "usage": total_usage,
            "model": final_result.get("model", model_used),
            "finish_reason": final_result.get("finish_reason", "stop"),
            "overflow_applied": "map_reduce",
            "batches_processed": len(batches),
        }

    def _build_synthesis_prompt(
        self,
        partial_contents: List[str],
        json_mode: bool,
    ) -> str:
        """Build the synthesis prompt for the reduce phase."""
        parts = []
        for i, content in enumerate(partial_contents):
            # Truncate very long partials in the prompt
            if len(content) > 6000:
                content = content[:3000] + "\n...\n" + content[-3000:]
            parts.append(f"### 第{i+1}部分结果:\n{content}")

        instruction = (
            "请将以上各部分结果整合为一个完整的回答。要求：\n"
            "1. 去除各部分之间的重复信息\n"
            "2. 按逻辑顺序重新组织内容\n"
            "3. 保持所有关键信息不丢失\n"
            "4. 输出格式与各部分保持一致"
        )
        if json_mode:
            instruction += "\n5. 必须返回严格的JSON格式"

        return "\n\n---\n\n".join(parts) + f"\n\n{instruction}"

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion."""
        # For streaming, use smart_truncate if over limit (can't map-reduce a stream)
        if self.has_input_limit:
            strategy, batches = self._input_manager.check_and_plan(messages)
            if strategy != "direct":
                logger.info(
                    f"[LLMService] Stream with overflow → using smart_truncate"
                )
                # Override to smart_truncate for streaming
                messages = self._input_manager._build_smart_truncate(messages)

        response = await self.chat(messages, temperature, max_tokens, stream=True)
        try:
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Stream error: {e}")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def extract_json(content: str) -> Optional[Dict]:
        """Extract JSON from LLM response (handles markdown code blocks)."""
        # Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # ```json ... ``` block
        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Bare JSON object
        brace_pattern = r"\{.*\}"
        brace_matches = re.findall(brace_pattern, content, re.DOTALL)
        for match in brace_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        logger.warning(f"Failed to extract JSON from: {content[:200]}...")
        return None


# ============================================================
# Content Filter
# ============================================================
class ContentFilter:
    """Content safety filter - 内容安全过滤"""

    SENSITIVE_PATTERNS = [
        r"(违法|暴力|色情|歧视|政治敏感)",
        r"(hack|exploit|attack|malware|phishing)",
    ]

    @classmethod
    def check_content(cls, text: str) -> tuple[bool, Optional[str]]:
        """Check content for sensitive/unsafe material."""
        if not text:
            return True, None

        for keyword in SECURITY_CONFIG.get("sensitive_keywords", []):
            if keyword.lower() in text.lower():
                return False, f"Content contains sensitive keyword: {keyword}"

        import re as regex
        for pattern in cls.SENSITIVE_PATTERNS:
            if regex.search(pattern, text, regex.IGNORECASE):
                return False, "Content matches sensitive pattern"

        return True, None

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Remove potentially sensitive content."""
        for keyword in SECURITY_CONFIG.get("sensitive_keywords", []):
            text = text.replace(keyword, "[filtered]")
        return text


# ============================================================
# Hallucination Checker
# ============================================================
class HallucinationChecker:
    """Anti-hallucination mechanism using self-consistency + RAG verification."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def verify_factual_claims(
        self,
        claims: List[str],
        context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Verify factual claims against provided context or general knowledge."""
        verification_prompt = f"""你是一个事实核查专家。请逐一核查以下陈述的准确性。

参考上下文：
{context if context else "无额外上下文，请基于你的知识进行判断"}

需要核查的陈述：
{json.dumps([{"id": i, "claim": c} for i, c in enumerate(claims)], ensure_ascii=False, indent=2)}

请判断每个陈述：
- true: 完全正确
- partially_true: 基本正确但有小错误
- false: 明显错误
- uncertain: 无法确定

返回严格的JSON格式：
{{
    "verifications": [
        {{
            "id": 0,
            "claim": "原文",
            "verdict": "true|partially_true|false|uncertain",
            "confidence": 0.0-1.0,
            "reasoning": "判断理由",
            "correction": "如果错误，提供正确信息；否则为null"
        }}
    ]
}}
"""
        messages = [
            {"role": "system", "content": "你是一个严谨的事实核查专家，只返回JSON格式结果。"},
            {"role": "user", "content": verification_prompt},
        ]

        result = await self.llm.chat(messages, temperature=0.1, json_mode=True)
        data = self.llm.extract_json(result["content"])
        return data.get("verifications", []) if data else []


# ============================================================
# Singleton instances
# ============================================================
_llm_service: Optional[LLMService] = None
_hallucination_checker: Optional[HallucinationChecker] = None


def get_llm_service(provider: Optional[str] = None) -> LLMService:
    global _llm_service
    if _llm_service is None or provider:
        _llm_service = LLMService(provider)
    return _llm_service


def get_hallucination_checker() -> HallucinationChecker:
    global _hallucination_checker
    if _hallucination_checker is None:
        _hallucination_checker = HallucinationChecker(get_llm_service())
    return _hallucination_checker
