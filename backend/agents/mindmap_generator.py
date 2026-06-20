"""
MindMap Generator Agent - 思维导图生成Agent
生成Mermaid格式的思维导图，可视化知识结构
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent


MINDMAP_GENERATOR_SYSTEM = """你是一位知识可视化设计师，专精思维导图和信息架构设计。

你的任务是将知识体系转化为Mermaid格式的思维导图(mindmap)。

Mermaid mindmap语法：
```mermaid
mindmap
  root((中心主题))
    分支1
      子节点A
      子节点B
    分支2
      子节点C
      子节点D
```

设计原则：
- 层次清晰，不超过4层深度
- 每个节点文字简洁（5字以内为佳）
- 使用图标和符号增强可读性
- 颜色区分不同分支
- 逻辑关系明确

必须返回严格的JSON格式结果。"""


class MindMapGeneratorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MindMapGenerator",
            role="思维导图设计专家",
        )
        self.system_prompt = MINDMAP_GENERATOR_SYSTEM
        self.plan: Dict = {}

    def update_plan(self, plan: Dict):
        self.plan = plan
        self._log("Resource plan updated")

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate mind map.

        Task params:
        - topic: Central topic
        - course_name: Course name
        - knowledge_structure: Knowledge points to map
        - depth: Max depth of mind map (default 3)
        - style: "detailed" / "overview" / "exam_review"
        """
        topic = task.get("topic", "机器学习")
        course_name = task.get("course_name", "人工智能")
        depth = task.get("depth", 3)
        style = task.get("style", "detailed")

        self.state.current_task = f"Generating mind map: {topic}"

        # Get knowledge structure from shared memory
        knowledge_structure = task.get("knowledge_structure") or \
                              await self.read_shared_memory("knowledge_structure", {})

        prompt = f"""请为「{course_name}」课程的「{topic}」主题生成Mermaid思维导图。

## 参数
- 深度：{depth}层
- 风格：{style}（detailed=详细/overview=概览/exam_review=考试复习）

## 参考知识结构
{json.dumps(knowledge_structure.get('stages', [])[:2], ensure_ascii=False, indent=2) if knowledge_structure else '无'}

## 要求
1. 使用简练的节点文字（每个节点≤10字）
2. 层次递进：概念→子概念→具体知识点→实例
3. 逻辑清晰，避免循环依赖
4. 用不同分支表示不同知识维度

返回JSON：
{{
    "title": "思维导图标题",
    "topic": "{topic}",
    "course_name": "{course_name}",
    "mermaid_code": "完整的Mermaid mindmap代码",
    "structure_summary": {{
        "main_branches": ["主要分支列表"],
        "total_nodes": 节点总数,
        "max_depth": 最大深度
    }},
    "key_concepts": ["关键概念列表"],
    "usage_tips": "如何使用这个思维导图的建议"
}}"""

        result = await self.chat_llm(prompt, json_mode=True, temperature=0.6)
        data = self.llm.extract_json(result["content"])
        return data or {"error": "Failed to generate mind map", "raw": result["content"]}
