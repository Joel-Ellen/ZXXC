# -*- coding: utf-8 -*-
"""
LLMClientV2 — 统一大模型客户端 v2（合并版）
===========================================

同时支持多厂商：
  - DashScope (阿里云灵积 / 通义千问)
  - iFlyTek Spark (讯飞星火)
  - DeepSeek
  - OpenAI

特性：
  - 异步 OpenAI 兼容接口
  - 自动溢出策略（map_reduce / smart_truncate / sliding_window）
  - 内容安全过滤
  - 防幻觉自洽校验
  - 向后兼容 Backend A 的 4 个注入方法

来源: src/llm/client.py + backend/services/llm_service.py (merged)
"""
from __future__ import annotations

import os
import re
import json
import time
import hmac
import hashlib
import base64
import asyncio
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from datetime import datetime
from enum import Enum

import httpx
try:
    from openai import AsyncOpenAI
except ImportError:  # Providers are optional in offline/test deployments.
    AsyncOpenAI = None  # type: ignore[assignment,misc]

from .token_estimator import TokenEstimator
from .input_manager import InputManager
from .content_filter import ContentFilter


# ============================================================================
# Provider 枚举
# ============================================================================

class Provider(str, Enum):
    DASHSCOPE = "dashscope"
    IFLYTEK = "iflytek"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    OPENAI = "openai"


# ============================================================================
# LLM 配置
# ============================================================================

# 默认多供应商配置
DEFAULT_LLM_CONFIGS = {
    "dashscope": {
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "spark": {
        "api_key": os.getenv("SPARK_API_KEY", ""),
        "api_secret": os.getenv("SPARK_API_SECRET", ""),
        "app_id": os.getenv("SPARK_APP_ID", ""),
        "api_url": "https://spark-api-open.xf-yun.com/v1",
        "model": "spark-pro",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "deepseek": {
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "api_url": os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
        "model": "deepseek-chat",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    "qwen": {
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "max_tokens": 4096,
        "temperature": 0.7,
        "max_input_tokens": 128000,
        "overflow_strategy": "map_reduce",
    },
    "openai": {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "api_url": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1"),
        "model": "gpt-4o",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
}


# ============================================================================
# LLMClientV2（统一异步客户端）
# ============================================================================

class LLMClientV2:
    """统一多厂商大模型客户端 — 异步版。

    使用示例:
        >>> client = LLMClientV2(provider="dashscope")
        >>> result = await client.chat([{"role": "user", "content": "你好"}])
        >>> print(result["content"])

        >>> # 向后兼容的注入方法
        >>> text = client.generate_content("N01", "concept_map", 0.5)
        >>> score = client.compute_nli_entailment("假设", "前提")
    """

    def __init__(self, provider: str = None):
        provider = provider or os.getenv("LLM_PROVIDER", "dashscope")
        self.provider = provider
        self.config = DEFAULT_LLM_CONFIGS.get(provider, DEFAULT_LLM_CONFIGS["deepseek"])
        self._client: Optional[AsyncOpenAI] = None

        # Input manager（仅对有限制的 provider 启用）
        max_input = self.config.get("max_input_tokens")
        overflow_strategy = self.config.get("overflow_strategy", "map_reduce")
        self._input_manager = InputManager(
            max_input_tokens=max_input,
            strategy=overflow_strategy,
        ) if max_input else None

        self._init_client()

    @property
    def has_input_limit(self) -> bool:
        return self._input_manager is not None

    def _init_client(self):
        api_key = self.config.get("api_key", "")
        if not api_key:
            api_key = "placeholder"

        # 讯飞星火使用自定义 HTTP auth（不走 AsyncOpenAI）
        if self.provider == "spark":
            self._client = None
            return

        if AsyncOpenAI is None:
            raise ImportError("openai is required for OpenAI-compatible LLM providers")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.config["api_url"],
        )

    # ==================================================================
    # 核心 API: chat()
    # ==================================================================

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
        json_mode: bool = False,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """发送 chat completion 请求。

        若 provider 有输入 token 限制且消息超限，自动应用溢出策略。
        """
        temp = temperature if temperature is not None else self.config.get("temperature", 0.7)
        max_tok = max_tokens or self.config.get("max_tokens", 4096)

        # --- 输入限制检查 ---
        if self.has_input_limit:
            strategy, batches = self._input_manager.check_and_plan(messages)

            if strategy == "map_reduce" and len(batches) > 1:
                return await self._map_reduce_chat(batches, temp, max_tok, json_mode)
            elif strategy in ("smart_truncate", "sliding_window"):
                messages = batches[0]

        # --- 标准单请求路径 ---
        return await self._single_chat(messages, temp, max_tok, json_mode, stream)

    # ------------------------------------------------------------------
    # 单次请求
    # ------------------------------------------------------------------

    async def _single_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """执行单次 LLM API 调用。"""
        # 讯飞星火走自定义 HTTP 路径
        if self.provider == "spark":
            return await self._chat_spark_http(messages, temperature, max_tokens, json_mode)

        kwargs = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)

            if stream:
                return response  # caller iterates

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
            if self.provider == "spark":
                # Spark 失败 → 降级到 DeepSeek
                fallback = LLMClientV2("deepseek")
                return await fallback.chat(messages, temperature, max_tokens, json_mode)
            raise

    # ------------------------------------------------------------------
    # 讯飞星火 HTTP 路径（非 AsyncOpenAI）
    # ------------------------------------------------------------------

    async def _chat_spark_http(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Dict[str, Any]:
        """通过 HTTP 调用讯飞星火大模型（含 HMAC 鉴权）。"""
        cfg = self.config
        host = "spark-api-open.xf-yun.com"
        path = "/v1/chat/completions"

        # HMAC 签名
        now_str = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {host}\ndate: {now_str}\nPOST {path} HTTP/1.1"
        signature_sha = hmac.new(
            cfg.get("api_secret", "").encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode()

        authorization_origin = (
            f'api_key="{cfg.get("api_key", "")}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        headers = {
            "Authorization": f"Bearer {authorization}",
            "Date": now_str,
            "Content-Type": "application/json",
        }

        payload = {
            "model": cfg.get("model", "spark-pro"),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://{host}{path}",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                body = resp.json()
                choices = body.get("choices", [])
                content = ""
                for c in choices:
                    content += c.get("message", {}).get("content", "")
                return {
                    "content": content,
                    "usage": body.get("usage", {}),
                    "model": body.get("model", cfg.get("model")),
                    "finish_reason": choices[0].get("finish_reason", "stop") if choices else "stop",
                }
            else:
                raise RuntimeError(f"Spark HTTP {resp.status_code}: {resp.text[:200]}")

    # ------------------------------------------------------------------
    # Map-Reduce
    # ------------------------------------------------------------------

    async def _map_reduce_chat(
        self,
        batches: List[List[Dict[str, str]]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Dict[str, Any]:
        map_tasks = [
            self._single_chat(batch, temperature, max_tokens, json_mode)
            for batch in batches
        ]
        map_results = await asyncio.gather(*map_tasks, return_exceptions=True)

        partial_contents = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        model_used = self.config["model"]

        for i, result in enumerate(map_results):
            if isinstance(result, Exception):
                partial_contents.append(f"[批次 {i+1} 处理失败: {str(result)}]")
            elif isinstance(result, dict):
                partial_contents.append(result.get("content", ""))
                usage = result.get("usage", {})
                total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                total_usage["total_tokens"] += usage.get("total_tokens", 0)
                model_used = result.get("model", model_used)

        valid_results = [c for c in partial_contents if c and "处理失败" not in c]
        if len(valid_results) == 1:
            return {
                "content": valid_results[0],
                "usage": total_usage,
                "model": model_used,
                "finish_reason": "stop",
                "overflow_applied": "map_reduce_single",
            }

        # Reduce: 合成
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

        final_result = await self._single_chat(synthesis_messages, temperature, max_tokens, json_mode)
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

    def _build_synthesis_prompt(self, partial_contents: list, json_mode: bool) -> str:
        parts = []
        for i, content in enumerate(partial_contents):
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
        temperature: float = None,
        max_tokens: int = None,
    ) -> AsyncGenerator[str, None]:
        """流式 chat completion。"""
        if self.has_input_limit:
            strategy, batches = self._input_manager.check_and_plan(messages)
            if strategy != "direct":
                messages = self._input_manager._build_smart_truncate(messages)

        temp = temperature if temperature is not None else self.config.get("temperature", 0.7)
        max_tok = max_tokens or self.config.get("max_tokens", 4096)

        if self.provider == "spark":
            result = await self._chat_spark_http(messages, temp, max_tok, False)
            yield result["content"]
            return

        kwargs = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tok,
            "stream": True,
        }

        response = await self._client.chat.completions.create(**kwargs)
        try:
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"\n[Stream error: {e}]"

    # ------------------------------------------------------------------
    # JSON 提取
    # ------------------------------------------------------------------

    @staticmethod
    def extract_json(content: str) -> Optional[Dict]:
        """从 LLM 响应中提取 JSON（处理 markdown 代码块）。"""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        brace_pattern = r"\{.*\}"
        brace_matches = re.findall(brace_pattern, content, re.DOTALL)
        for match in brace_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        return None

    # ==================================================================
    # 注入接口（向后兼容 Backend A）
    # ==================================================================

    def generate_content(
        self,
        node_id: str,
        card_type: str,
        difficulty: float,
        *,
        timeout_sec: Optional[float] = None,
        course_id: str = "",
        node_title: str = "",
    ) -> str:
        """为指定知识点生成多模态教育资源（ContentMesh Node 注入用）。"""
        type_names = {
            "concept_map": "概念思维导图",
            "code_snippet": "代码实操示例",
            "interactive_exercise": "互动练习题",
            "video_summary": "教学视频摘要",
            "diagnostic_quiz": "诊断测验题",
        }
        type_name = type_names.get(card_type, card_type)
        canonical_title = str(node_title or node_id).strip()
        canonical_course = str(course_id or "unspecified").strip()

        system_prompt = (
            "你是一个顶级的计算机科学教育专家，擅长数据结构与算法教学。"
            "请根据指定知识点、资源类型和难度系数，生成高质量的中文学习资源。"
            "内容需使用 Markdown 格式，包含适当的结构化组织。"
            "课程 ID、知识点 ID 和规范标题由服务端提供，不得自行改成其他知识点。"
            "输出的第一个 Markdown 标题必须包含服务端给出的规范标题，正文必须始终围绕该标题。"
            "难度系数 0.0-0.3 为基础入门，0.3-0.7 为进阶，0.7-1.0 为高级/竞赛。"
        )

        user_prompt = (
            f"课程 ID: {canonical_course}\n"
            f"知识点 ID: {node_id}\n"
            f"规范知识点标题: {canonical_title}\n"
            f"资源类型: {type_name}\n"
            f"难度系数: {difficulty:.2f} (0-1)\n\n"
            f"请只为“{canonical_title}”生成一份完整的 {type_name} 学习资源。"
            f"使用 Markdown 格式输出，包含标题、要点和具体内容。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._sync_chat_wrapper(messages, timeout_sec=timeout_sec)

    def generate_academic_explanation(
        self, query: str, reference_chunks: List[str]
    ) -> str:
        """生成学术原理解释（Tutor Agent 轨一注入用）。"""
        context = "\n\n---\n\n".join(reference_chunks[:5]) if reference_chunks else "无参考上下文"

        system_prompt = (
            "你是一个耐心、专业的计算机科学助教。请根据提供的参考知识库内容，"
            "用清晰易懂的中文解答学生的问题。你的回答应包含：\n"
            "1. 核心概念解释（用通俗语言）\n"
            "2. 关键步骤或原理拆解\n"
            "3. 一个简单的例子或类比帮助理解\n"
            "请使用 Markdown 格式，结构清晰、层次分明。"
        )

        user_prompt = (
            f"学生提问: {query}\n\n"
            f"参考知识库内容:\n{context}\n\n"
            f"请根据以上参考资料，为学生提供详细的学术原理解答。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._sync_chat_wrapper(messages)

    def generate_mermaid_graph(
        self, query: str, text_explanation: str
    ) -> str:
        """生成 Mermaid 拓扑图解（Tutor Agent 轨二注入用）。"""
        system_prompt = (
            "你是一个 Mermaid.js 图表生成专家。请根据给定的学术讲解内容，"
            "生成一个对应的 Mermaid 拓扑流程图（graph TD 格式），"
            "用可视化的方式展示核心概念之间的关系。\n\n"
            "要求：\n"
            "1. 必须使用 graph TD（自上而下）格式\n"
            "2. 节点标签用方括号 [] 包裹，如 A[概念名]\n"
            "3. 箭头使用 -->\n"
            "4. 只输出 Mermaid 代码，不要包含任何其他文字说明\n"
            "5. 节点数量控制在 4-8 个，结构清晰"
        )

        context = text_explanation[:600] if text_explanation else query

        user_prompt = (
            f"问题: {query}\n\n"
            f"解答摘要:\n{context}\n\n"
            f"请生成对应的 Mermaid graph TD 图解。只输出 Mermaid 代码。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result = self._sync_chat_wrapper(messages, temperature=0.3)

        # 清理 Markdown 代码块包裹
        result = result.strip()
        mermaid_match = re.search(r'```mermaid\s*\n?(.*?)```', result, re.DOTALL)
        if mermaid_match:
            return mermaid_match.group(1).strip()
        code_match = re.search(r'```\s*\n?(graph\s+TD.*?)```', result, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()
        return result

    def compute_nli_entailment(self, text: str, ground_truth: str) -> float:
        """计算 NLI 蕴含度（Validator Node 注入用）。"""
        if not text or not ground_truth:
            return 0.5

        system_prompt = (
            "你是一个严格的自然语言推理 (NLI) 评判员。"
            "你的任务是判断一段文本（假设 hypothesis）是否与基准真值（前提 premise）"
            "语义一致。请只输出一个 0 到 1 之间的小数，表示蕴含度分数：\n"
            "- 1.0 = 完全一致（entailment）\n"
            "- 0.5 = 部分相关（neutral）\n"
            "- 0.0 = 完全矛盾（contradiction）\n\n"
            "只输出数字，不要包含任何其他文字。"
        )

        gt_truncated = ground_truth[:800]
        text_truncated = text[:500]

        user_prompt = (
            f"基准真值 (premise):\n{gt_truncated}\n\n"
            f"待验证文本 (hypothesis):\n{text_truncated}\n\n"
            f"请给出蕴含度分数 (0-1 之间的小数):"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = self._sync_chat_wrapper(messages, temperature=0.0, max_tokens=10)
        result = result.strip()

        try:
            score = float(result)
            return max(0.0, min(1.0, score))
        except ValueError:
            nums = re.findall(r'0\.\d+|\d+\.\d+', result)
            if nums:
                score = float(nums[0])
                return max(0.0, min(1.0, score))
            return 0.5

    # ------------------------------------------------------------------
    # 同步封装（供现有同步代码使用）
    # ------------------------------------------------------------------

    def _sync_chat_wrapper(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
        timeout_sec: Optional[float] = None,
    ) -> str:
        """同步调用 chat() 的便捷封装。"""
        bounded_timeout = None
        if timeout_sec is not None:
            bounded_timeout = max(0.1, float(timeout_sec))

        async def invoke() -> Dict[str, Any]:
            request = self.chat(messages, temperature, max_tokens)
            if bounded_timeout is not None:
                return await asyncio.wait_for(request, timeout=bounded_timeout)
            return await request

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # 在已运行的事件循环中（如 uvicorn），在线程池中运行
                import concurrent.futures
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                future = pool.submit(asyncio.run, invoke())
                try:
                    result = future.result(timeout=(bounded_timeout or 45.0) + 0.5)
                finally:
                    # The coroutine has its own ``wait_for`` cancellation
                    # budget. Do not turn an outer timeout into an unbounded
                    # shutdown wait on this synchronous compatibility path.
                    pool.shutdown(wait=False, cancel_futures=True)
            else:
                result = loop.run_until_complete(
                    invoke()
                )
        except RuntimeError as exc:
            if "no current event loop" not in str(exc).lower() and "no running event loop" not in str(exc).lower():
                raise
            result = asyncio.run(invoke())

        return result.get("content", "") if isinstance(result, dict) else str(result)

    # ------------------------------------------------------------------
    # 同步 chat() — 兼容需要 dict 返回的旧代码
    # ------------------------------------------------------------------

    def chat_sync(
        self,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
        json_mode: bool = False,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """同步版本的 chat()，返回与 async chat() 相同的 dict 结构。"""
        bounded_timeout = max(0.1, float(timeout_sec)) if timeout_sec is not None else 45.0

        async def invoke() -> Dict[str, Any]:
            return await asyncio.wait_for(
                self.chat(messages, temperature, max_tokens, json_mode),
                timeout=bounded_timeout,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        invoke(),
                    )
                    return future.result(timeout=bounded_timeout + 0.5)
            else:
                return loop.run_until_complete(invoke())
        except RuntimeError:
            return asyncio.run(invoke())


# ============================================================================
# 工厂函数
# ============================================================================

def create_llm_client_v2(provider: str = None) -> LLMClientV2:
    """创建 LLMClientV2 实例的工厂函数。"""
    return LLMClientV2(provider=provider)


def create_llm_client_v2_from_env() -> LLMClientV2:
    """从环境变量自动检测并创建 LLMClientV2。

    优先级（赛题要求：优先使用科大讯飞相关工具）:
      1. SPARK_API_KEY + SPARK_APP_ID + SPARK_API_SECRET → spark（讯飞星火，首选）
      2. DASHSCOPE_API_KEY → dashscope（阿里云 Qwen，备用）
      3. DEEPSEEK_API_KEY → deepseek
      4. OPENAI_API_KEY → openai
      5. 都不存在 → 抛出异常
    """
    # 讯飞星火优先（第十五届中国软件杯赛题规定：使用科大讯飞相关工具）
    if os.getenv("SPARK_API_KEY") and os.getenv("SPARK_APP_ID") and os.getenv("SPARK_API_SECRET"):
        return LLMClientV2(provider="spark")
    elif os.getenv("DASHSCOPE_API_KEY"):
        return LLMClientV2(provider="dashscope")
    elif os.getenv("DEEPSEEK_API_KEY"):
        return LLMClientV2(provider="deepseek")
    elif os.getenv("OPENAI_API_KEY"):
        return LLMClientV2(provider="openai")
    else:
        raise RuntimeError(
            "未检测到可用的大模型 API Key。请设置以下环境变量之一:\n"
            "  优先（讯飞）: SPARK_API_KEY + SPARK_APP_ID + SPARK_API_SECRET\n"
            "  备用（阿里云）: DASHSCOPE_API_KEY\n"
            "  其他: DEEPSEEK_API_KEY / OPENAI_API_KEY"
        )
