# -*- coding: utf-8 -*-
"""
LLMClient — 统一大模型接入层
=============================

同时支持 DashScope (阿里云灵积 Qwen) 和 iFlyTek Spark (讯飞星火)
两套大模型 API，提供一致的调用接口。

DashScope:
  - 兼容 OpenAI Chat Completions 格式
  - 模型: qwen-plus, qwen-max, qwen-turbo 等
  - 端点: https://dashscope.aliyuncs.com/compatible-mode/v1

iFlyTek Spark:
  - 使用星火大模型 v4.0 WebSocket API
  - 需要 APP_ID, API_KEY, API_SECRET 三要素
  - 端点: wss://spark-api.xf-yun.com/v4.0/chat

注入接口:
  - generate_academic_explanation(query, reference_chunks) -> str  (Tutor 用)
  - generate_mermaid_graph(query, text_explanation) -> str        (Tutor 用)
  - generate_content(node_id, card_type, difficulty) -> str       (ContentMesh 用)
  - compute_nli_entailment(text, ground_truth) -> float            (Validator 用)

依赖声明:
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import os
import json
import re
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, field

import requests


# ============================================================================
# 配置
# ============================================================================

class Provider(str, Enum):
    """大模型后端提供商。"""
    DASHSCOPE = "dashscope"       # 阿里云灵积 (Qwen)
    IFLYTEK = "iflytek"           # 讯飞星火 Spark


@dataclass
class LLMConfig:
    """大模型连接配置。"""

    provider: Provider = Provider.DASHSCOPE

    # ---- DashScope ----
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"

    # ---- iFlyTek Spark ----
    spark_app_id: str = ""
    spark_api_key: str = ""
    spark_api_secret: str = ""
    spark_domain: str = "4.0Ultra"  # 模型版本

    # ---- 通用 ----
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout_seconds: int = 60
    max_retries: int = 2


# ============================================================================
# LLM 客户端
# ============================================================================

class LLMClient:
    """统一大模型客户端 — 支持 DashScope 和 iFlyTek Spark 双后端。

    使用示例:
        >>> # 从环境变量自动配置
        >>> client = create_llm_client_from_env()
        >>> # 或手动配置
        >>> config = LLMConfig(provider=Provider.DASHSCOPE, dashscope_api_key="sk-xxx")
        >>> client = LLMClient(config)
        >>> # 用于 Tutor
        >>> text = client.generate_academic_explanation("什么是二叉树?", ["二叉树是..."])

    注入到 EduAgent:
        >>> orchestrator = EduAgentGraph()
        >>> orchestrator.inject_llm(client)
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self._config = config or LLMConfig()

    @property
    def config(self) -> LLMConfig:
        return self._config

    # ------------------------------------------------------------------
    # 核心调用
    # ------------------------------------------------------------------

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """通用 Chat Completions 调用。

        Args:
            messages: [{"role": "system/user/assistant", "content": "..."}]
            **kwargs: 覆盖 config 中的参数。

        Returns:
            模型生成的文本内容。
        """
        if self._config.provider == Provider.DASHSCOPE:
            return self._chat_dashscope(messages, **kwargs)
        elif self._config.provider == Provider.IFLYTEK:
            return self._chat_spark(messages, **kwargs)
        else:
            raise ValueError(f"不支持的 provider: {self._config.provider}")

    # ------------------------------------------------------------------
    # DashScope (Qwen) 实现
    # ------------------------------------------------------------------

    def _chat_dashscope(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> str:
        """通过 DashScope OpenAI 兼容接口调用 Qwen 模型。"""
        url = f"{self._config.dashscope_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._config.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._config.dashscope_model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "temperature": kwargs.get("temperature", self._config.temperature),
        }

        for attempt in range(self._config.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._config.timeout_seconds,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    return body["choices"][0]["message"]["content"]
                else:
                    if attempt < self._config.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return f"[LLM Error: HTTP {resp.status_code}] {resp.text[:200]}"
            except requests.exceptions.Timeout:
                if attempt < self._config.max_retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return "[LLM Error: Request Timeout]"
            except Exception as e:
                if attempt < self._config.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return f"[LLM Error: {str(e)[:200]}]"

        return "[LLM Error: Max retries exceeded]"

    # ------------------------------------------------------------------
    # iFlyTek Spark (讯飞星火) 实现
    # ------------------------------------------------------------------

    def _chat_spark(
        self, messages: List[Dict[str, str]], **kwargs
    ) -> str:
        """通过 WebSocket 调用讯飞星火大模型。

        基于星火 v4.0 的 HTTP 封装（非流式）。
        """
        # 构建鉴权 URL
        import hmac
        import hashlib
        import base64
        from datetime import datetime
        from urllib.parse import urlencode, urlparse

        cfg = self._config
        host = "spark-api.xf-yun.com"
        path = f"/v4.0/chat"
        now = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        # 签名
        signature_origin = f"host: {host}\ndate: {now}\nPOST {path} HTTP/1.1"
        signature_sha = hmac.new(
            cfg.spark_api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode()

        authorization_origin = (
            f'api_key="{cfg.spark_api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        url = f"https://{host}{path}"
        headers = {
            "Authorization": f"Bearer {authorization}",
            "Date": now,
            "Content-Type": "application/json",
        }

        # 构建星火格式的 messages
        spark_messages = []
        for m in messages:
            spark_messages.append({"role": m["role"], "content": m["content"]})

        payload = {
            "header": {
                "app_id": cfg.spark_app_id,
                "uid": f"edu_agent_{uuid.uuid4().hex[:8]}",
            },
            "parameter": {
                "chat": {
                    "domain": cfg.spark_domain,
                    "max_tokens": kwargs.get("max_tokens", cfg.max_tokens),
                    "temperature": kwargs.get("temperature", cfg.temperature),
                }
            },
            "payload": {
                "message": {
                    "text": spark_messages,
                }
            },
        }

        for attempt in range(self._config.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._config.timeout_seconds,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    # 星火返回结构: payload.choices.text[].content
                    choices = (
                        body.get("payload", {})
                        .get("choices", {})
                        .get("text", [])
                    )
                    return "".join(c.get("content", "") for c in choices)
                else:
                    if attempt < self._config.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return f"[Spark Error: HTTP {resp.status_code}] {resp.text[:200]}"
            except requests.exceptions.Timeout:
                if attempt < self._config.max_retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return "[Spark Error: Request Timeout]"
            except Exception as e:
                if attempt < self._config.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return f"[Spark Error: {str(e)[:200]}]"

        return "[Spark Error: Max retries exceeded]"

    # ==================================================================
    # Agent Node 注入接口
    # ==================================================================

    # ------------------------------------------------------------------
    # ContentMesh 用: 生成资源内容
    # ------------------------------------------------------------------

    def generate_content(
        self, node_id: str, card_type: str, difficulty: float
    ) -> str:
        """为指定知识点生成多模态教育资源内容（ContentMesh Node 注入用）。

        Args:
            node_id: 知识点 ID。
            card_type: 资源类型 (concept_map/code_snippet/interactive_exercise/
                       video_summary/diagnostic_quiz)。
            difficulty: 难度系数 (0.0-1.0)。

        Returns:
            Markdown 格式的资源内容。
        """
        type_names = {
            "concept_map": "概念思维导图",
            "code_snippet": "代码实操示例",
            "interactive_exercise": "互动练习题",
            "video_summary": "教学视频摘要",
            "diagnostic_quiz": "诊断测验题",
        }
        type_name = type_names.get(card_type, card_type)

        system_prompt = (
            "你是一个顶级的计算机科学教育专家，擅长数据结构与算法教学。"
            "请根据指定知识点、资源类型和难度系数，生成高质量的中文学习资源。"
            "内容需使用 Markdown 格式，包含适当的结构化组织。"
            "难度系数 0.0-0.3 为基础入门，0.3-0.7 为进阶，0.7-1.0 为高级/竞赛。"
        )

        user_prompt = (
            f"知识点 ID: {node_id}\n"
            f"资源类型: {type_name}\n"
            f"难度系数: {difficulty:.2f} (0-1)\n\n"
            f"请为该知识点生成一份完整的 {type_name} 学习资源。"
            f"使用 Markdown 格式输出，包含标题、要点和具体内容。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages)

    # ------------------------------------------------------------------
    # Tutor 用: 学术原理解释
    # ------------------------------------------------------------------

    def generate_academic_explanation(
        self, query: str, reference_chunks: List[str]
    ) -> str:
        """生成学术原理解释（Tutor Agent 轨一注入用）。

        Args:
            query: 学生的答疑提问文本。
            reference_chunks: Milvus 检索到的参考上下文列表。

        Returns:
            结构化的学术原理讲解（Markdown 格式）。
        """
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
        return self.chat(messages)

    # ------------------------------------------------------------------
    # Tutor 用: 生成 Mermaid 图解
    # ------------------------------------------------------------------

    def generate_mermaid_graph(
        self, query: str, text_explanation: str
    ) -> str:
        """生成 Mermaid 拓扑图解（Tutor Agent 轨二注入用）。

        Args:
            query: 学生的答疑提问。
            text_explanation: 已生成的文字解答（用作 Mermaid 的语义上下文）。

        Returns:
            Mermaid 格式的流程图/TD 图源码。
        """
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

        # 截取前 600 字作为上下文
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
        result = self.chat(messages, temperature=0.3)

        # 清理可能的 Markdown 代码块包裹
        result = result.strip()
        mermaid_match = re.search(r'```mermaid\s*\n?(.*?)```', result, re.DOTALL)
        if mermaid_match:
            return mermaid_match.group(1).strip()
        # 也可能用 ``` 包裹
        code_match = re.search(r'```\s*\n?(graph\s+TD.*?)```', result, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()
        return result

    # ------------------------------------------------------------------
    # Validator 用: NLI 蕴含度计算
    # ------------------------------------------------------------------

    def compute_nli_entailment(self, text: str, ground_truth: str) -> float:
        """计算文本与基准真值之间的 NLI 蕴含度（Validator Node 注入用）。

        通过大模型判断生成的文本是否与 ground truth 保持一致。

        Args:
            text: 待验证的文本（假设）。
            ground_truth: 基准真值（前提）。

        Returns:
            蕴含度分数 [0.0, 1.0]，越高表示越一致。
        """
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

        # 截断以避免 token 超限
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

        result = self.chat(messages, temperature=0.0, max_tokens=10)
        result = result.strip()

        # 解析数字
        try:
            score = float(result)
            return max(0.0, min(1.0, score))
        except ValueError:
            # 尝试从字符串中提取数字
            nums = re.findall(r'0\.\d+|\d+\.\d+', result)
            if nums:
                score = float(nums[0])
                return max(0.0, min(1.0, score))
            return 0.5


# ============================================================================
# 工厂函数
# ============================================================================

def create_llm_client(
    provider: str = "dashscope",
    api_key: str = "",
    model: str = "qwen-plus",
    **kwargs,
) -> LLMClient:
    """创建 LLM 客户端的工厂函数。

    Args:
        provider: "dashscope" 或 "iflytek"。
        api_key: API Key。
        model: 模型名称。
        **kwargs: 其他 LLMConfig 参数。

    Returns:
        LLMClient 实例。
    """
    if provider == "dashscope":
        config = LLMConfig(
            provider=Provider.DASHSCOPE,
            dashscope_api_key=api_key,
            dashscope_model=model,
            **kwargs,
        )
    elif provider == "iflytek":
        config = LLMConfig(
            provider=Provider.IFLYTEK,
            spark_api_key=api_key,
            **kwargs,
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}，可选: dashscope, iflytek")
    return LLMClient(config)


def create_llm_client_from_env() -> LLMClient:
    """从环境变量自动配置 LLM 客户端。

    优先级（赛题规定：优先使用科大讯飞工具）:
      1. 若同时设置 SPARK_APP_ID + SPARK_API_KEY + SPARK_API_SECRET → 讯飞星火（首选）
      2. 若设置 DASHSCOPE_API_KEY → DashScope (Qwen)（备用）
      3. 都不存在 → 抛出异常

    环境变量:
      - SPARK_APP_ID:      讯飞星火 APP ID（优先）
      - SPARK_API_KEY:     讯飞星火 API Key（优先）
      - SPARK_API_SECRET:  讯飞星火 API Secret（优先）
      - DASHSCOPE_API_KEY: 阿里云灵积 API Key（备用）
      - DASHSCOPE_MODEL:   模型名（默认 qwen-plus）
    """
    spark_app_id = os.environ.get("SPARK_APP_ID", "")
    spark_api_key = os.environ.get("SPARK_API_KEY", "")
    spark_api_secret = os.environ.get("SPARK_API_SECRET", "")
    dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "")
    dashscope_model = os.environ.get("DASHSCOPE_MODEL", "qwen-plus")

    # 讯飞星火优先（第十五届中国软件杯赛题规定）
    if spark_app_id and spark_api_key and spark_api_secret:
        config = LLMConfig(
            provider=Provider.IFLYTEK,
            spark_app_id=spark_app_id,
            spark_api_key=spark_api_key,
            spark_api_secret=spark_api_secret,
        )
    elif dashscope_key:
        config = LLMConfig(
            provider=Provider.DASHSCOPE,
            dashscope_api_key=dashscope_key,
            dashscope_model=dashscope_model,
        )
    else:
        raise RuntimeError(
            "未检测到可用的大模型 API Key。请设置以下环境变量之一:\n"
            "  优先（讯飞）: export SPARK_APP_ID=xxx SPARK_API_KEY=xxx SPARK_API_SECRET=xxx\n"
            "  备用（阿里云）: export DASHSCOPE_API_KEY=sk-xxx"
        )
    return LLMClient(config)
