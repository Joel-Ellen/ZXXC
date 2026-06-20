# -*- coding: utf-8 -*-
"""
HallucinationChecker — 防幻觉自洽性校验
=======================================

使用 LLM 自洽性 + RAG 验证来检查事实性声明。

来源: backend/services/llm_service.py (merged)
"""
import json
from typing import Dict, List, Any, Optional


class HallucinationChecker:
    """防幻觉机制：自洽性 + RAG 验证。"""

    def __init__(self, llm_client):
        """需要注入一个 LLM 客户端（支持 async chat + json_mode）。"""
        self.llm = llm_client

    async def verify_factual_claims(
        self,
        claims: List[str],
        context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """校验事实性声明是否与上下文或通用知识一致。"""
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
