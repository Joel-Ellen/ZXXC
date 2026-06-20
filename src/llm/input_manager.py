# -*- coding: utf-8 -*-
"""
InputManager — 上下文窗口溢出管理
================================

处理超出模型 token 限制的输入。策略：
  - direct:         输入适配 → 直接发送
  - smart_truncate: 保留 system + 最近消息，截断中间/旧内容
  - map_reduce:     拆分为多个块 → 分别处理 → 合成结果
  - sliding_window: 保留 system prompt + 在长内容上滑动窗口

来源: backend/services/llm_service.py (merged)
"""
import re
from typing import Dict, List, Tuple

from .token_estimator import TokenEstimator


class InputManager:
    """管理输入以适配模型 token 限制。"""

    DEFAULT_MAX_INPUT_TOKENS = 128000  # 128K

    def __init__(
        self,
        max_input_tokens: int = None,
        strategy: str = "map_reduce",
    ):
        self.max_input = max_input_tokens or self.DEFAULT_MAX_INPUT_TOKENS
        self.strategy = strategy

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def check_and_plan(
        self,
        messages: List[Dict[str, str]],
    ) -> Tuple[str, List[List[Dict[str, str]]]]:
        """检查输入是否在限制内。若超限则返回处理方案。

        Returns:
            (strategy_name, list_of_message_batches)
        """
        estimated = TokenEstimator.estimate_messages(messages)
        overhead = TokenEstimator.estimate_system_overhead()
        total_estimated = estimated + overhead

        if total_estimated <= self.max_input:
            return "direct", [messages]

        if self.strategy == "map_reduce":
            batches = self._build_map_reduce_batches(messages)
            return "map_reduce", batches
        elif self.strategy == "sliding_window":
            truncated = self._build_sliding_window(messages)
            return "sliding_window", [truncated]
        else:
            truncated = self._build_smart_truncate(messages)
            return "smart_truncate", [truncated]

    # ------------------------------------------------------------------
    # 策略: Map-Reduce
    # ------------------------------------------------------------------

    def _build_map_reduce_batches(
        self,
        messages: List[Dict[str, str]],
    ) -> List[List[Dict[str, str]]]:
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        available_per_batch = self.max_input - system_tokens - 500

        batches: List[List[Dict[str, str]]] = []

        for msg in other_msgs:
            content = msg.get("content", "")
            msg_tokens = TokenEstimator.estimate(content)

            if msg_tokens <= available_per_batch:
                batches.append(system_msgs + [msg])
            else:
                chunks = self._semantic_chunk(content, available_per_batch)
                for chunk in chunks:
                    batches.append(system_msgs + [
                        {"role": msg["role"], "content": chunk}
                    ])

        if not batches:
            return [messages]

        return batches

    # ------------------------------------------------------------------
    # 策略: Smart Truncate
    # ------------------------------------------------------------------

    def _build_smart_truncate(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        available = self.max_input - system_tokens - 200

        result = list(system_msgs)
        remaining = available

        for msg in reversed(other_msgs):
            content = msg.get("content", "")
            msg_tokens = TokenEstimator.estimate(content)

            if msg_tokens <= remaining:
                result.insert(len(system_msgs), msg)
                remaining -= msg_tokens
            elif remaining > 500:
                truncated_content = self._truncate_to_tokens(content, remaining)
                result.insert(len(system_msgs), {
                    "role": msg["role"],
                    "content": truncated_content + "\n\n[... 内容已截断以适配上下文限制 ...]",
                })
                remaining = 0
                break
            else:
                break

        return result

    # ------------------------------------------------------------------
    # 策略: Sliding Window
    # ------------------------------------------------------------------

    def _build_sliding_window(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        system_msgs = [m for m in messages if m["role"] == "system"]
        other_msgs = [m for m in messages if m["role"] != "system"]

        if not other_msgs:
            return system_msgs

        longest = max(other_msgs, key=lambda m: len(m.get("content", "")))
        content = longest.get("content", "")

        system_tokens = TokenEstimator.estimate_messages(system_msgs)
        window_size = self.max_input - system_tokens - 300
        overlap = window_size // 4

        windows = self._sliding_window_chunk(content, window_size, overlap)

        return system_msgs + [{"role": longest["role"], "content": windows[0]}]

    # ==================================================================
    # Chunking utilities
    # ==================================================================

    def _semantic_chunk(self, text: str, max_tokens_per_chunk: int) -> list:
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

        final_chunks = []
        for chunk in chunks:
            if TokenEstimator.estimate(chunk) > max_tokens_per_chunk:
                final_chunks.extend(self._force_split(chunk, max_tokens_per_chunk))
            else:
                final_chunks.append(chunk)

        return final_chunks

    @staticmethod
    def _force_split(text: str, max_tokens: int) -> list:
        sentences = re.split(r'(?<=[。！？.!?；;，,\n])\s*', text)
        chunks = []
        current = ""
        current_tokens = 0

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_tokens = TokenEstimator.estimate(sent)

            if sent_tokens > max_tokens:
                if current.strip():
                    chunks.append(current.strip())
                    current = ""
                    current_tokens = 0
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

        final_chunks = []
        for chunk in chunks:
            if TokenEstimator.estimate(chunk) > max_tokens:
                final_chunks.extend(InputManager._chop_by_chars(chunk, max_tokens))
            else:
                final_chunks.append(chunk)

        return final_chunks if final_chunks else [text]

    @staticmethod
    def _chop_by_chars(text: str, max_tokens: int) -> list:
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
    def _sliding_window_chunk(text: str, window_tokens: int, overlap_tokens: int) -> list:
        window_chars = int(window_tokens * 2.0)
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
        max_chars = int(max_tokens * 2.0)
        if len(text) <= max_chars:
            return text
        head_size = int(max_chars * 0.7)
        tail_size = max_chars - head_size - 50
        return text[:head_size] + "\n\n[... 中间内容已截断 ...]\n\n" + text[-tail_size:]
