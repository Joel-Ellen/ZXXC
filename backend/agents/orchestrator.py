"""
AI Learning Assistant - Agent Orchestrator (Multi-Agent Coordinator)
多智能体系统 - 编排器（多智能体协同核心）

Implements:
- Agent lifecycle management
- Task decomposition & assignment
- Inter-agent message routing
- Shared memory management
- Workflow execution (sequential / parallel / pipeline)
- Status aggregation for UI
"""
import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime
from collections import defaultdict
from loguru import logger
from .base_agent import BaseAgent, AgentMessage, AgentState

# Agent imports
from .student_profiler import StudentProfilerAgent
from .knowledge_analysis import KnowledgeAnalysisAgent
from .resource_planner import ResourcePlannerAgent
from .ppt_generator import PPTGeneratorAgent
from .question_generator import QuestionGeneratorAgent
from .mindmap_generator import MindMapGeneratorAgent
from .coding_practice import CodingPracticeAgent
from .video_script import VideoScriptAgent
from .learning_coach import LearningCoachAgent
from .evaluation import EvaluationAgent


class AgentOrchestrator:
    """
    Central orchestrator for the multi-agent learning system.

    Responsibilities:
    1. Initialize and manage all agents
    2. Route messages between agents
    3. Decompose user requests into agent tasks
    4. Execute multi-agent workflows
    5. Aggregate and return results
    6. Track agent states for UI display
    """

    # Agent dependency graph (which agents depend on which)
    AGENT_DEPENDENCIES = {
        "StudentProfiler": [],
        "KnowledgeAnalysis": ["StudentProfiler"],
        "ResourcePlanner": ["StudentProfiler", "KnowledgeAnalysis"],
        "PPTGenerator": ["ResourcePlanner", "KnowledgeAnalysis"],
        "QuestionGenerator": ["ResourcePlanner", "KnowledgeAnalysis"],
        "MindMapGenerator": ["ResourcePlanner", "KnowledgeAnalysis"],
        "CodingPractice": ["ResourcePlanner", "KnowledgeAnalysis"],
        "VideoScript": ["ResourcePlanner", "KnowledgeAnalysis"],
        "LearningCoach": ["StudentProfiler", "KnowledgeAnalysis"],
        "Evaluation": ["StudentProfiler", "LearningCoach", "QuestionGenerator"],
    }

    # Workflow definitions (predefined agent execution sequences)
    WORKFLOWS = {
        "build_profile": {
            "name": "学习画像构建",
            "agents": ["StudentProfiler"],
            "mode": "sequential",
        },
        "generate_all_resources": {
            "name": "全资源生成",
            "agents": [
                "KnowledgeAnalysis",
                "ResourcePlanner",
                "PPTGenerator",
                "QuestionGenerator",
                "MindMapGenerator",
                "CodingPractice",
                "VideoScript",
            ],
            "mode": "parallel_grouped",
            "groups": [
                ["KnowledgeAnalysis", "ResourcePlanner"],  # Phase 1: Analysis & Planning
                ["PPTGenerator", "QuestionGenerator", "MindMapGenerator", "CodingPractice", "VideoScript"],  # Phase 2: Generation (parallel)
            ],
        },
        "learning_path": {
            "name": "学习路径规划",
            "agents": ["StudentProfiler", "KnowledgeAnalysis", "ResourcePlanner"],
            "mode": "pipeline",
        },
        "tutoring": {
            "name": "智能辅导",
            "agents": ["StudentProfiler", "LearningCoach"],
            "mode": "sequential",
        },
        "evaluation": {
            "name": "学习评估",
            "agents": ["StudentProfiler", "LearningCoach", "Evaluation"],
            "mode": "pipeline",
        },
        "full_assessment": {
            "name": "完整评估流程",
            "agents": [
                "StudentProfiler",
                "KnowledgeAnalysis",
                "ResourcePlanner",
                "QuestionGenerator",
                "LearningCoach",
                "Evaluation",
            ],
            "mode": "pipeline",
        },
    }

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.shared_memory: Dict[str, Any] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.execution_history: List[Dict[str, Any]] = []
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize all agent instances and wire up shared memory"""
        if self._initialized:
            return

        logger.info("Initializing Agent Orchestrator...")

        # Create all agents
        self.agents = {
            "StudentProfiler": StudentProfilerAgent(),
            "KnowledgeAnalysis": KnowledgeAnalysisAgent(),
            "ResourcePlanner": ResourcePlannerAgent(),
            "PPTGenerator": PPTGeneratorAgent(),
            "QuestionGenerator": QuestionGeneratorAgent(),
            "MindMapGenerator": MindMapGeneratorAgent(),
            "CodingPractice": CodingPracticeAgent(),
            "VideoScript": VideoScriptAgent(),
            "LearningCoach": LearningCoachAgent(),
            "Evaluation": EvaluationAgent(),
        }

        # Wire up shared memory for all agents
        for agent in self.agents.values():
            agent.shared_memory = self.shared_memory

        # Register inter-agent message handlers
        self._register_message_handlers()

        self._initialized = True
        logger.info(f"Orchestrator initialized with {len(self.agents)} agents: {list(self.agents.keys())}")

    def _register_message_handlers(self):
        """Register message handlers between dependent agents"""
        # KnowledgeAnalysis needs StudentProfiler output
        self.agents["KnowledgeAnalysis"].register_handler(
            "profile_update",
            lambda msg: self.agents["KnowledgeAnalysis"].update_student_context(msg.content),
        )
        # ResourcePlanner needs both profile and knowledge analysis
        self.agents["ResourcePlanner"].register_handler(
            "knowledge_structure",
            lambda msg: self.agents["ResourcePlanner"].update_knowledge_structure(msg.content),
        )
        # Resource generators need plan output
        for name in ["PPTGenerator", "QuestionGenerator", "MindMapGenerator",
                      "CodingPractice", "VideoScript"]:
            self.agents[name].register_handler(
                "resource_plan",
                lambda msg, n=name: self.agents[n].update_plan(msg.content),
            )
        # Evaluation needs learning records
        self.agents["Evaluation"].register_handler(
            "learning_records",
            lambda msg: self.agents["Evaluation"].update_records(msg.content),
        )

    async def execute_workflow(
        self,
        workflow_name: str,
        params: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a predefined workflow.

        Args:
            workflow_name: Name of the workflow (from WORKFLOWS)
            params: Input parameters
            user_id: User ID for logging

        Returns:
            Aggregated workflow results
        """
        await self.initialize()

        workflow = self.WORKFLOWS.get(workflow_name)
        if not workflow:
            raise ValueError(f"Unknown workflow: {workflow_name}. Available: {list(self.WORKFLOWS.keys())}")

        workflow_id = str(uuid.uuid4())
        self.active_workflows[workflow_id] = {
            "name": workflow["name"],
            "started_at": datetime.utcnow(),
            "status": "running",
            "agents": workflow["agents"],
            "results": {},
        }

        logger.info(f"Starting workflow: {workflow_name} ({workflow['name']}) [mode={workflow['mode']}]")

        try:
            if workflow["mode"] == "sequential":
                results = await self._execute_sequential(workflow["agents"], params)
            elif workflow["mode"] == "parallel_grouped":
                results = await self._execute_grouped(workflow["groups"], params)
            elif workflow["mode"] == "pipeline":
                results = await self._execute_pipeline(workflow["agents"], params)
            else:
                results = await self._execute_sequential(workflow["agents"], params)

            self.active_workflows[workflow_id]["status"] = "completed"
            self.active_workflows[workflow_id]["results"] = results
            self.active_workflows[workflow_id]["completed_at"] = datetime.utcnow()

            # Log execution
            self.execution_history.append({
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "user_id": user_id,
                "params": params,
                "results_summary": {k: type(v).__name__ for k, v in results.items()},
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "status": "completed",
                "results": results,
            }

        except Exception as e:
            logger.error(f"Workflow {workflow_name} failed: {e}")
            self.active_workflows[workflow_id]["status"] = "failed"
            self.active_workflows[workflow_id]["error"] = str(e)
            raise

    async def _execute_sequential(
        self,
        agent_names: List[str],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute agents one after another, passing results forward"""
        results = {}
        context = dict(params)

        for name in agent_names:
            agent = self.agents.get(name)
            if not agent:
                logger.warning(f"Agent '{name}' not found, skipping")
                continue

            logger.info(f"Executing agent: {name}")
            agent.state.status = "working"
            agent.state.current_task = context.get("task_description", f"Execute {name}")

            try:
                result = await agent.execute(context)
                results[name] = result
                # Pass results as context for next agent
                context[f"{name}_output"] = result
                agent.state.status = "idle"
            except Exception as e:
                logger.error(f"Agent {name} failed: {e}")
                agent.state.status = "error"
                agent.state.errors.append(str(e))
                results[name] = {"error": str(e)}

        return results

    async def _execute_grouped(
        self,
        groups: List[List[str]],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute agents in phases - agents within a group run in parallel"""
        results = {}
        context = dict(params)

        for group_idx, group in enumerate(groups):
            logger.info(f"Phase {group_idx + 1}: Executing {group} in parallel")

            async def run_agent(name: str, ctx: Dict) -> Tuple[str, Dict]:
                agent = self.agents.get(name)
                if not agent:
                    return name, {"error": f"Agent {name} not found"}
                agent.state.status = "working"
                try:
                    result = await agent.execute(ctx)
                    agent.state.status = "idle"
                    return name, result
                except Exception as e:
                    agent.state.status = "error"
                    return name, {"error": str(e)}

            # Run group in parallel
            tasks = [run_agent(name, context) for name in group]
            group_results = await asyncio.gather(*tasks)

            for name, result in group_results:
                results[name] = result
                context[f"{name}_output"] = result

        return results

    async def _execute_pipeline(
        self,
        agent_names: List[str],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute agents in pipeline mode.
        Each agent receives the previous agent's output and enriches it.
        """
        results = {}
        pipeline_data = dict(params)

        for name in agent_names:
            agent = self.agents.get(name)
            if not agent:
                continue

            task = {"pipeline_data": pipeline_data, "agent_params": params.get(name, {})}
            agent.state.status = "working"

            try:
                result = await agent.execute(task)
                results[name] = result
                # Merge result into pipeline data for next agent
                if isinstance(result, dict):
                    pipeline_data.update(result)
                agent.state.status = "idle"
            except Exception as e:
                agent.state.status = "error"
                results[name] = {"error": str(e)}

        return results

    async def execute_single_agent(
        self,
        agent_name: str,
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single agent directly"""
        await self.initialize()

        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")

        agent.state.status = "working"
        agent.state.current_task = task.get("description", f"Execute {agent_name}")

        try:
            result = await agent.execute(task)
            agent.state.status = "idle"
            return result
        except Exception as e:
            agent.state.status = "error"
            agent.state.errors.append(str(e))
            raise

    def get_all_agent_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all agents for UI display"""
        return [agent.get_status() for agent in self.agents.values()]

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get overall orchestrator status"""
        active_agents = sum(
            1 for a in self.agents.values() if a.state.status == "working"
        )
        return {
            "total_agents": len(self.agents),
            "active_agents": active_agents,
            "idle_agents": len(self.agents) - active_agents,
            "active_workflows": len([w for w in self.active_workflows.values() if w["status"] == "running"]),
            "shared_memory_keys": list(self.shared_memory.keys()),
            "execution_history_count": len(self.execution_history),
        }

    def get_agent_workflow_diagram(self) -> str:
        """Generate Mermaid diagram showing agent workflow and dependencies"""
        mermaid = """```mermaid
graph TD
    %% Agent Workflow Diagram
    SP[Student Profiler<br/>学生画像构建] --> KA[Knowledge Analysis<br/>知识点拆解]
    SP --> LC[Learning Coach<br/>学习指导]

    KA --> RP[Resource Planner<br/>学习资源规划]
    KA --> LC

    RP --> PPT[PPT Generator<br/>课件生成]
    RP --> QG[Question Generator<br/>题库生成]
    RP --> MM[MindMap Generator<br/>思维导图生成]
    RP --> CP[Coding Practice<br/>代码实战生成]
    RP --> VS[Video Script<br/>视频脚本生成]

    QG --> EV[Evaluation Agent<br/>学习评估]
    LC --> EV
    SP --> EV

    %% Shared Memory
    SM[(Shared Memory<br/>共享记忆)] -.-> SP
    SM -.-> KA
    SM -.-> RP
    SM -.-> LC
    SM -.-> EV

    %% Styling
    classDef profile fill:#4CAF50,stroke:#333,color:#fff
    classDef analysis fill:#2196F3,stroke:#333,color:#fff
    classDef generate fill:#FF9800,stroke:#333,color:#fff
    classDef evaluate fill:#9C27B0,stroke:#333,color:#fff
    classDef memory fill:#607D8B,stroke:#333,color:#fff

    class SP profile
    class KA,RP analysis
    class PPT,QG,MM,CP,VS generate
    class LC,EV evaluate
    class SM memory
```"""
        return mermaid

    async def shutdown(self):
        """Gracefully shutdown all agents"""
        logger.info("Shutting down orchestrator...")
        for agent in self.agents.values():
            agent.state.status = "idle"
        self._initialized = False
        logger.info("Orchestrator shutdown complete")


# Singleton
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
