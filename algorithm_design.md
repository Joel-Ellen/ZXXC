# "EduAgent" —— 个性化资源生成与学习多智能体系统 核心技术文档

> **第十五届"中国软件杯"大赛 A 组 · 科大讯飞出题**
> 
> **赛题**：《基于大模型的个性化资源生成与学习多智能体系统开发》
> 
> **版本**: v2.0 | **日期**: 2026-06-13 | **作者**: Joel-Ellen

---

## 目录

1. [系统概览与架构总览](#一系统概览与架构总览)
2. [技术栈与依赖体系](#二技术栈与依赖体系)
3. [多智能体协同网络 —— LangGraph 编排引擎](#三多智能体协同网络--langgraph-编排引擎)
4. [核心主算法一：Profiler Agent —— 汤普森采样与遗忘曲线画像构建](#四核心主算法一profiler-agent--汤普森采样与遗忘曲线画像构建)
5. [核心主算法二：Path Planner & Content Mesh —— 拓扑路径规划与异步资源生成](#五核心主算法二path-planner--content-mesh--拓扑路径规划与异步资源生成)
6. [核心主算法三：Evaluator Agent —— 异构流门控清洗与 PID 控制评估](#六核心主算法三evaluator-agent--异构流门控清洗与-pid-控制评估)
7. [底层辅助算法一：版面感知切片与知识图谱自动构建](#七底层辅助算法一版面感知切片与知识图谱自动构建)
8. [底层辅助算法二：基于双极门控的防幻觉验证](#八底层辅助算法二基于双极门控的防幻觉验证)
9. [底层辅助算法三：冷启动情境探针启发式追问](#九底层辅助算法三冷启动情境探针启发式追问)
10. [底层辅助算法四：WFQ 特权队列与马尔可夫预测性缓存](#十底层辅助算法四wfq-特权队列与马尔可夫预测性缓存)
11. [数据层架构 —— AgentState / Neo4j / Milvus / Elasticsearch](#十一数据层架构--agentstate--neo4j--milvus--elasticsearch)
12. [LLM 集成层 —— 双后端大模型统一客户端](#十二llm-集成层--双后端大模型统一客户端)
13. [加分项一：Tutor Agent —— 三轨多模态智能辅导](#十三加分项一tutor-agent--三轨多模态智能辅导)
14. [加分项二：Assessment Node —— EMA 能力雷达与迟滞环策略](#十四加分项二assessment-node--ema-能力雷达与迟滞环策略)
15. [测试体系与质量保障](#十五测试体系与质量保障)
16. [附录：完整文件目录映射](#十六附录完整文件目录映射)

---

## 一、系统概览与架构总览

### 1.1 项目定位

EduAgent 是一个**基于大模型的多智能体协同学习系统**，将学生的完整学习生命周期建模为**闭环反馈控制系统**。系统采用 LangGraph 有向图框架协调 7 个专业化 AI Agent 协同工作，完成从冷启动画像采集 → 路径规划 → 多模态资源生成 → 防幻觉校验 → 学习效果评估 → 动态重寻路的完整闭环。

### 1.2 核心设计理念

本系统采用**前后端分离架构**，核心后端逻辑完全由多智能体协同网络驱动。关键设计原则：

- **大模型只做语义感知与内容生成**，路径控制、画像演进和策略刹车全部交给毫秒级的传统确定性算法（图论、控制论、概率论）
- **工业级控制论基础**：将学习过程建模为 PID 反馈控制系统，具备抗饱和、无扰切换、自适应增益调度等工程特性
- **多模态异步分层生成**：消除富媒体生成的长尾白屏延迟
- **双重防幻觉机制**：符号实体硬匹配 + NLI 语义蕴含度并行校验

### 1.3 系统架构全景图

```
                           ┌──────────────────────────────────────┐
                           │          LangGraph StateGraph         │
                           │         (AgentState 全局上下文)        │
                           └──────────────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         │                                    │                                    │
         v                                    v                                    v
   ┌───────────┐     ┌───────────┐     ┌───────────┐     ┌───────────┐     ┌───────────┐
   │ Evaluator │────>│ Profiler  │────>│  Planner  │────>│  Tutor    │────>│  Content  │
   │  (PID)    │     │  (MAB)    │     │(Dijkstra) │     │ (3-Track) │     │   Mesh    │
   └───────────┘     └───────────┘     └───────────┘     └───────────┘     └───────────┘
         ^                                                                       │
         │                                                                       v
         │                                                               ┌───────────┐
         │                                                               │ Validator │
         │                                                               │ (NLI)     │
         │                                                               └───────────┘
         │                                                                       │
         │                                                                       v
         └───────────────────────────────────────────────────────────────┌───────────┐
                            (条件边: re_plan_triggered?)                  │Assessment │
                                                                         │ (EMA雷达) │
                                                                         └───────────┘
```

**7 个 Agent Node 职责**：

| Agent | 文件位置 | 核心职责 |
|-------|----------|---------|
| **Evaluator** | `src/agents/evaluator_node.py` | 行为非线性门控清洗 + PID 控制平滑评估 |
| **Profiler** | `src/agents/profiler_node.py` | MAB 汤普森采样 + 艾宾浩斯遗忘曲线衰减 |
| **Planner** | `src/agents/planner_node.py` | Neo4j DAG-Dijkstra 最短路径规划 |
| **Tutor** | `src/agents/tutor_node.py` | 三轨多模态智能辅导答疑（加分项） |
| **Content Mesh** | `src/agents/content_mesh_node.py` | WFQ 调度 + 5 类资源卡片生成 + 马尔可夫预生成 |
| **Validator** | `src/agents/validator_node.py` | 双极防幻觉校验（AST/LaTeX + NLI） |
| **Assessment** | `src/agents/assessment_node.py` | EMA 5 维能力雷达 + 迟滞环策略决策（加分项） |

### 1.4 端到端流程

```
[冷启动] → [PID评估] → [MAB画像更新] → [DAG路径规划]
    ↓                                           ↓
[资源卡片生成 (WFQ)] ← [Tutor答疑(可选)] ←───┘
    ↓
[双极防幻觉校验] → [EMA能力评估] → [迟滞环策略决策]
    ↓                                    ↓
[下一轮迭代] ←────────── [重寻路触发?] ──→ [Planner重规划]
```

---

## 二、技术栈与依赖体系

### 2.1 核心技术栈

| 层级 | 技术选型 | 版本 | 用途 |
|------|---------|------|------|
| **多智能体编排** | LangGraph | ≥0.2.0 | 有向图驱动的 Agent 协同框架 |
| **LLM 后端（双引擎）** | 阿里云 DashScope (Qwen) / 讯飞星火 Spark v4.0 | - | 内容生成、辅导答疑、NLI 推理 |
| **图数据库** | Neo4j | ≥5.20 | 专业知识图谱存储与 Cypher 查询 |
| **向量数据库（双引擎）** | Milvus / Elasticsearch | ≥2.3 / ≥8.17 | 语义检索、混合检索 (BM25 + HNSW + RRF) |
| **数据校验** | Pydantic v2 | ≥2.5 | 全局状态强类型校验 |
| **嵌入模型** | BAAI/bge-small-zh-v1.5 (sentence-transformers) | ≥5.0 | 中文文本向量化 |
| **数学计算** | NumPy | - | Beta 分布采样、随机数生成 |
| **异步/流式** | aiohttp / sse-starlette / starlette | ≥3.9 / ≥1.8 / ≥0.36 | HTTP 与 SSE 流式输出 |
| **测试框架** | pytest / pytest-asyncio | ≥7.4 / ≥0.21 | 单元测试与集成测试 |
| **容错重试** | tenacity | ≥8.2 | API 调用指数退避重试 |
| **文本分割** | langchain-text-splitters | ≥0.3 | Markdown 感知的文档切片 |

### 2.2 依赖清单 (`requirements.txt`)

```
langgraph>=0.2.0,<1.0.0
langchain-core>=0.3.0,<1.0.0
neo4j>=5.20.0,<6.0.0
pymilvus>=2.3.0,<3.0.0
elasticsearch>=8.17.0,<9.0.0
pydantic>=2.5.0,<3.0.0
langchain-text-splitters>=0.3.0,<1.0.0
pytest>=7.4.0,<9.0.0
pytest-asyncio>=0.21.0,<1.0.0
aiohttp>=3.9.0,<4.0.0
sentence-transformers>=5.0.0,<6.0.0
sse-starlette>=1.8.0,<2.0.0
starlette>=0.36.0,<1.0.0
python-dotenv>=1.0.0,<2.0.0
tenacity>=8.2.0,<9.0.0
```

---

## 三、多智能体协同网络 —— LangGraph 编排引擎

### 3.1 编排文件

**主控文件**: [`src/orchestration.py`](src/orchestration.py)

### 3.2 EduAgentGraph 类

`EduAgentGraph` 是 LangGraph StateGraph 的封装类，负责：

1. **注册 7 个 Agent Node** 到有向图
2. **配置条件边**实现智能路由
3. **LLM 依赖注入**：将真实大模型客户端注入各 Agent Node，替换 Mock 实现
4. **流式运行**：支持 `run()` 和 `stream()` 两种执行模式

```python
class EduAgentGraph:
    def __init__(self):
        self._evaluator = EvaluatorNode()
        self._profiler = ProfilerNode()
        self._planner = PlannerNode()
        self._tutor = TutorAgentNode()
        self._mesh = ContentMeshNode()
        self._validator = ValidatorNode()
        self._assessment = AssessmentReporterNode()
```

### 3.3 图拓扑结构

```
START → evaluator → profiler → planner → [条件边]
                                              ├─(has tutor_query?)→ tutor → content_mesh
                                              └─(no query)→ content_mesh
                                                              ↓
                                                          validator
                                                              ↓
                                                         assessment
                                                              ↓
                                                          [条件边]
                                              ├─(re_plan)→ planner
                                              ├─(continue)→ evaluator
                                              └─(end)→ END
```

### 3.4 条件路由逻辑

**Tutor 路由** (`_tutor_routing`):
- 若 `latest_behavior.tutor_query` 非空 → 路由到 Tutor Node 进行答疑
- 否则 → 直接进入 Content Mesh 资源生成

**重寻路/终止路由** (`_route_decision`):
- `target_node_id` 掌握度 ≥ 0.85 且无重寻路需求 → 终止 (`"end"`)
- `active_path` 为空且无重寻路需求 → 终止 (`"end"`)
- `iteration ≥ 100` → 终止 (`"end"`)
- `re_plan_triggered == True` → 回到 Planner 重寻路 (`"replan"`)
- 否则 → 进入下一轮评估 (`"continue"`)

### 3.5 冷启动编排器 (`ColdStartOrchestrator`)

在进入主 LangGraph 图之前，`ColdStartOrchestrator` 负责：
1. 调用 `handle_cold_start_interaction` 逐轮收集 6 维画像
2. 冷启动完成后触发 Planner 初始路径规划
3. 将就绪的 AgentState 注入主图

---

## 四、核心主算法一：Profiler Agent —— 汤普森采样与遗忘曲线画像构建

### 4.1 赛题对应要求

支持通过自然语言对话自动抽取特征，构建包含不少于 6 个维度的动态学生画像，并支持画像的随学随新。

### 4.2 算法核心逻辑

画像被解耦为**慢变特征空间（贝塔概率分布）**与**快变特征向量（时变状态矩阵）**：
- **慢变特征**：利用多臂老虎机（MAB）的汤普森采样动态纠偏
- **快变特征**：通过结合遗忘曲线的增量方程更新，并设置心理学干预门控防止掌握度塌陷的负反馈死循环

### 4.3 实现文件

[`src/agents/profiler_node.py`](src/agents/profiler_node.py)

### 4.4 核心数据结构

**CognitiveStyleDistribution** — 认知风格 Beta 分布参数（`src/state/agent_state.py`）：

```python
class CognitiveStyleDistribution(BaseModel):
    visual_alpha: float = 1.0      # 视觉型 α 超参数
    visual_beta: float = 1.0       # 视觉型 β 超参数
    textual_alpha: float = 1.0     # 文本型 α 超参数
    textual_beta: float = 1.0      # 文本型 β 超参数
    practical_alpha: float = 1.0   # 实践型 α 超参数
    practical_beta: float = 1.0    # 实践型 β 超参数
```

### 4.5 核心数学公式

#### 4.5.1 慢变维度（学习风格）汤普森采样

每次推送资源时，从各风格的 Beta 分布中进行随机采样，选取采样值 θ 最大的风格作为推送策略：

$$\theta_{\text{style}} \sim \text{Beta}(\alpha_{\text{style}}, \beta_{\text{style}})$$

- 交互正向埋点时执行：$\alpha_{\text{style}} = \alpha_{\text{style}} + \text{reward}$
- 负向埋点时执行：$\beta_{\text{style}} = \beta_{\text{style}} + (1 - \text{reward})$

#### 4.5.2 快变维度（知识掌握度）干预更新方程

$$K_i^{(t)} = \max \left( K_{\text{floor}}, \lambda \cdot \left( K_i^{(t-1)} \cdot e^{-\frac{\Delta t}{S_i}} \right) + (1 - \lambda) \cdot \Delta E_v \cdot \gamma \right)$$

$$\gamma = \begin{cases} 1 & \text{if } C_{\text{fail}} < 3 \\ \theta \cdot \text{cognitive\_shift}() & \text{if } C_{\text{fail}} \ge 3 \end{cases}$$

- $\Delta t$：遗忘衰减时间
- $\Delta E_v$：即时测试得分
- $C_{\text{fail}}$：连续失败计数器
- $K_{\text{floor}} = 0.15$：最低掌握度保底
- 当 $C_{\text{fail}} \ge 3$ 时，门控 $\gamma$ 强行触发 `cognitive_shift()`，临时将资源切向非当前风格

### 4.6 实现细节

#### 4.6.1 ThompsonSampler 类

```python
class ThompsonSampler:
    ARM_NAMES = ["visual", "textual", "practical"]
    SUCCESS_THRESHOLD = 0.6

    def sample(self) -> Tuple[str, Dict[str, float]]:
        """从各臂的 Beta(α, β) 中采样，选择最大值。"""
        samples = {}
        for name in self.ARM_NAMES:
            alpha, beta = self._params[name]
            samples[name] = float(self._rng.beta(alpha, beta))
        best_style = max(samples, key=samples.get)
        return best_style, samples

    def update(self, style: str, reward: float):
        """按比例更新 Beta 参数 — reward ≥ 0.6 则 α+=reward，否则 β+=(1-reward)。"""
        alpha, beta = self._params[style]
        if reward >= self.SUCCESS_THRESHOLD:
            alpha += reward
        else:
            beta += (1.0 - reward)
        self._params[style] = (max(0.01, alpha), max(0.01, beta))
```

#### 4.6.2 EbbinghausForgettingEngine 类

遗忘曲线公式：$m(t) = m_0 \cdot e^{-\lambda \cdot \Delta t}$，其中 $\lambda = 1/S$（S 为记忆强度）。

- 每次成功交互：$S \leftarrow S \times 1.5$
- 每次失败交互：$S \leftarrow S \times 0.8$
- S 钳位范围：$[0.5, 20.0]$

```python
class EbbinghausForgettingEngine:
    MASTERY_FLOOR = 0.15
    DEFAULT_STRENGTH = 10.0  # 约 24 小时半衰期
    SUCCESS_STRENGTH_MULT = 1.5
    FAILURE_STRENGTH_MULT = 0.8

    def apply_decay(self, node_id, mastery, last_updated_ts, current_ts):
        elapsed_hours = max(0.0, current_ts - last_updated_ts) / 3600.0
        strength = self.get_strength(node_id)
        lambd = 1.0 / strength
        decay_factor = math.exp(-lambd * elapsed_hours)
        decayed_mastery = max(self.MASTERY_FLOOR, mastery * decay_factor)
        return ForgettingCurveResult(...)
```

#### 4.6.3 ProfilerNode 主流程

```
1. 从 AgentState 加载 Beta 先验 → 初始化 MAB 采样器
2. 检查 C_fail ≥ 3 → 触发硬切换干预（排除当前风格，强制选择次优）
3. 正常汤普森采样 → 选择推送风格
4. 根据 Evaluator 反馈更新 Beta 参数（reward = 1 - |PID_error|）
5. 更新遗忘引擎的记忆强度
6. 对当前知识点应用艾宾浩斯遗忘衰减
7. 将 MAB 参数写回 AgentState
```

---

## 五、核心主算法二：Path Planner & Content Mesh —— 拓扑路径规划与异步资源生成

### 5.1 赛题对应要求

为学生规划科学、动态的个性化学习路径，明确学习步骤和顺序；由不同角色的智能体协作完成至少 5 种类型的个性化资源生成。

### 5.2 算法核心逻辑

拒绝纯大模型盲目规划路径，将高校课程图谱作为硬性拓扑边界约束。寻路目标重构为"寻找一条覆盖所有未掌握前置节点且全局认知负荷最均衡的拓扑激活序列"。生成层采用两阶段分层流水线，消除富媒体生成带来的长尾白屏延迟。

### 5.3 Path Planner 实现

**实现文件**: [`src/infrastructure/path_planner.py`](src/infrastructure/path_planner.py)
**Agent 封装**: [`src/agents/planner_node.py`](src/agents/planner_node.py)

#### 5.3.1 四种路径规划策略

| 策略 | 枚举值 | 说明 |
|------|--------|------|
| TOPO_MIN_WEIGHT | `topo_min_weight` | 拓扑约束下的最小总权重路径（Dijkstra on DAG） |
| TOPO_MIN_HOPS | `topo_min_hops` | 拓扑约束下的最小跳数路径（BFS on DAG） |
| TOPO_BALANCED | `topo_balanced` | 难度方差最小化路径 |
| COLD_START_HEURISTIC | `cold_start_heuristic` | 冷启动启发式（探索-利用平衡） |

#### 5.3.2 拓扑激活路径代价函数

$$Cost(u, v) = \left( 1 - K_u \right) \cdot \text{Prerequisite\_Weight}(u, v) + \omega \cdot \text{Difficulty}(v)$$

- $K_u$：前置节点 $u$ 的画像掌握度
- 当 $K_u \to 1$（已掌握）时，前置激活代价趋近于 0
- 若未掌握，引入认知阻力开销，迫使 Path Planner 生成树状激活序列

#### 5.3.3 PathPlanner 核心实现

**Kahn 拓扑排序** ($O(V+E)$)：
```python
def compute_topological_order(self):
    indegree = dict(self._indegree)
    queue = deque(nid for nid, deg in indegree.items() if deg == 0)
    topo = []
    while queue:
        u = queue.popleft()
        topo.append(u)
        for v, _ in self._adj.get(u, []):
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)
    if len(topo) != len(self._node_map):
        raise ValueError("知识图谱中存在有向环 (非 DAG)！")
    return topo
```

**DAG 单源最短路径** ($O(V+E)$)：
```python
def _dag_sssp(self, source_id, weight_fn):
    topo = self.compute_topological_order()
    dist = {nid: float("inf") for nid in self._node_map}
    pred = {nid: None for nid in self._node_map}
    dist[source_id] = 0.0
    start_idx = self._topo_rank.get(source_id, -1)
    for i in range(start_idx, len(topo)):
        u = topo[i]
        if dist[u] == float("inf"):
            continue
        for v, base_w in self._adj.get(u, []):
            w = weight_fn(u, v, base_w)
            if dist[v] > dist[u] + w:
                dist[v] = dist[u] + w
                pred[v] = u
    return dist, pred
```

**路径计算主流程** (`compute_path`):
```
1. 计算拓扑序 → 校验 DAG 合法性
2. 剪枝已掌握节点 (mastery ≥ threshold)
3. 确定源节点（current_node_id 或拓扑序第一个未掌握节点）
4. 自动选择策略（冷启动阶段强制 COLD_START_HEURISTIC）
5. 运行 DAG-SSSP
6. 路径回溯 + 长度/时间预算截断
7. 可行性校验（确保所有前置依赖已满足）
```

#### 5.3.4 Neo4j 图谱集成

**实现文件**: [`src/graph/neo4j_client.py`](src/graph/neo4j_client.py)

- 节点：`KnowledgeNode` (node_id, title, difficulty, estimated_hours, category)
- 边：`PREREQUISITE` 关系 (dependency_type: strict/recommended/optional, weight)
- 用户掌握度：`MASTERED` 关系 (mastery score, timestamp)
- 子图提取：支持 K-hop 邻域查询（上游/下游/双向）

### 5.4 Content Mesh 实现

**实现文件**: [`src/agents/content_mesh_node.py`](src/agents/content_mesh_node.py)

#### 5.4.1 两阶段异步分层生成流

**第一阶段（结构骨架流式输出）**：
- 总控 Supervisor 统一注入全局对齐变量
- Doc Agent 与 Mind Agent 优先并发启动
- 1~2 秒内通过 WebSocket 将 Markdown 文本流与 Mermaid 导图源码推送到前端流式渲染

**第二阶段（富媒体卡片异步注入 / Hydration）**：
- Quiz Agent、Code Agent、多模态 Video Agent 进入异步长轮询队列
- 前端骨架屏展现"生成进度追踪"
- 任何卡片若在 Validator 校验中连续 2 次重生成失败 → 启动降级策略，提取本地知识库标准预置模版

#### 5.4.2 5 种资源卡片类型

```python
class ResourceCard(BaseModel):
    resource_id: str
    node_id: str
    card_type: str  # concept_map | code_snippet | interactive_exercise | video_summary | diagnostic_quiz
    content: str    # Markdown 格式
    difficulty: float
    cognitive_style: str  # visual | textual | practical
```

---

## 六、核心主算法三：Evaluator Agent —— 异构流门控清洗与 PID 控制评估

### 6.1 赛题对应要求

实时跟踪学生的学习行为、练习测试情况、资源使用反馈等数据；依托大模型实现对学生学习效果的多维度、精准评估；并据此动态调整推送策略。

### 6.2 算法核心逻辑

构建包含作答正确率、代码通过率、交互时长比、提问频次的异构行为特征向量。经过非线性门控清洗剔除"挂机伪造时长"与"抄袭秒杀作弊"噪音。引入工业级 PID（比例-积分-微分）平滑控制器消除偶发性成绩波动带来的系统频繁重寻路震荡（Thrashing）。

### 6.3 Evaluator Node 实现

**实现文件**: [`src/agents/evaluator_node.py`](src/agents/evaluator_node.py)

#### 6.3.1 行为特征的非线性门控清洗

```python
def sanitize_behavior_stream(x1, x2, x3, x4):
    """
    x1: 答题正确率, x2: 代码运行通过率, 
    x3: 实际时长/预估时长, x4: 智能导师提问次数
    """
    # 门控一：挂机刷课噪音拦截
    if x3 > 3.0: 
        x3 = 1.0  # 强制折算为标准常态时长

    # 门控二：抄袭秒杀作弊清洗
    if (x1 > 0.9 or x2 > 0.9) and x3 < 0.05:
        # 正确率极高但交互时间极短 → 复制粘贴作弊
        x1_clean = x1 * 0.1
        x2_clean = x2 * 0.1
        x4_stealth = x4 + 3.0  # 隐性调高辅导阻碍系数
        return x1_clean, x2_clean, x3, x4_stealth

    return x1, x2, x3, x4
```

#### 6.3.2 BehaviorCleaner 多维非线性门控

实际实现包含 4 类异常检测：
1. **AFK 挂机检测**：时间比率 > 3.0 → 强制归一化
2. **抄袭秒杀检测**：正确率 > 0.9 AND 时间比率 < 0.05 → 重度惩罚
3. **行为矛盾检测**：高正确率 + 高求助次数 → sigmoid 软决策惩罚
4. **快速猜测检测**：时间比率 < 0.1 AND 正确率 < 0.5 → 摩擦系数降低

### 6.4 PID 控制器实现

**实现文件**: [`src/infrastructure/pid_controller.py`](src/infrastructure/pid_controller.py)

#### 6.4.1 控制论建模

| 控制论概念 | 对应学习系统变量 |
|-----------|----------------|
| 设定点 (Setpoint) $r(t)$ | 目标掌握度 = 1.0 |
| 过程变量 (PV) $y(t)$ | 实际掌握度 $\in [0, 1]$ |
| 误差 (Error) $e(t)$ | $r(t) - y(t)$ |
| 控制输出 (CO) $u(t)$ | 难度系数 / 资源粒度 / 步长 |

#### 6.4.2 PID 核心公式

定义当前清洗后的即时表现增量与历史画像掌握度之间的系统误差：

$$\text{Error}^{(t)} = \Delta E_v^{(t)} - K_i^{(t-1)}$$

计算经过比例、积分、微分平滑后的掌握度调整控制增量：

$$\Delta K_{\text{smooth}} = K_p \cdot \text{Error}^{(t)} + K_i \cdot \sum_{j=0}^{t} \text{Error}^{(j)} + K_d \cdot \left( \text{Error}^{(t)} - \text{Error}^{(t-1)} \right)$$

$$K_i^{(t)} = K_i^{(t-1)} + \Delta K_{\text{smooth}}$$

**阻尼防震荡机制**：$K_d$（微分项）计算误差的变化率，当发生偶然性考满分或挂科时，$K_d$ 产生强力的反向阻尼制动，平滑掉突变噪音。只有当累积的 $\Delta K_{\text{smooth}}$ 连续 $N$ 次滑出置信阈值边界时，系统才正式触发全局重寻路。

#### 6.4.3 五大工程特性

```python
class PIDController:
    """
    1. Anti-Windup (积分抗饱和)
       - 条件积分: |e| > threshold 时暂停积分累积
       - 输出钳位: 输出超限时反算削减积分项 (Back-Calculation)

    2. Derivative-on-Measurement (测量微分)
       - de/dt = -dy/dt (当 setpoint 恒定时)
       - 避免设定点突变引起的"微分冲击"

    3. Bumpless Transfer (无扰切换)
       - 增益调度时平滑过渡

    4. Adaptive Gain Scheduling (自适应增益调度)
       - C_fail >= 3 → K_p *= 1.5^(sqrt(ratio)), K_i *= 2.0^(sqrt(ratio))
       - K_d 不变 — 避免对噪声过度敏感

    5. 滑动窗口误差统计
       - 用于在线诊断与增益自动整定
    """
```

#### 6.4.4 PIDController 核心实现

```python
def step(self, inp: PIDStepInput) -> PIDStepResult:
    # 1. 恢复/初始化内部状态
    # 2. 自适应增益调度 (根据 C_fail)
    kp, ki, kd = self._compute_adaptive_gains(inp.continuous_fail_counter)
    # 3. 计算误差
    error = inp.setpoint - inp.current_mastery
    # 4. 比例项 P = Kp * e(t)
    p_term = kp * error
    # 5. 积分项 I — 条件积分 + 抗饱和钳位
    i_term = self._compute_integral_term(state, error, ki, inp.dt)
    # 6. 微分项 D — 测量微分 + 一阶低通滤波
    d_term = self._compute_derivative_term(state, inp.current_mastery, kd, inp.dt)
    # 7. 钳位输出
    control_output = clamp(p_term + i_term + d_term, output_min, output_max)
    # 8. 反算抗饱和
    # 9. 更新历史值
    # 10. 评估干预触发
    # 11. 持久化状态
```

#### 6.4.5 状态持久化

LangGraph Node 在每次 step 后通过 `sync_pid_state_to_agent_state()` 将 PID 内部状态序列化回 `AgentState.dynamic_profile.pid_errors` 字典，确保跨轮次的 PID 记忆不丢失。

---

## 七、底层辅助算法一：版面感知切片与知识图谱自动构建

### 7.1 赛题对应要求

参赛团队需自行构造至少一门完整高校专业课程的初始知识库/文档集作为系统输入。

### 7.2 实现文件

| 模块 | 文件 |
|------|------|
| 版面感知文档切片 | [`src/infrastructure/document_chunker.py`](src/infrastructure/document_chunker.py) |
| 知识图谱构建 | [`src/infrastructure/graph_builder.py`](src/infrastructure/graph_builder.py) |
| Elasticsearch 知识库 | [`src/vector/elasticsearch_knowledge_base.py`](src/vector/elasticsearch_knowledge_base.py) |
| Milvus 向量存储 | [`src/vector/milvus_client.py`](src/vector/milvus_client.py) |

### 7.3 核心算法逻辑

解决专业教材中公式、代码块易被截断的痛点。通过 Layout-Aware 版面分析标签和语义密度动态划分文档，并利用层次目录树先验与 Tarjan 算法实现图谱的 DAG 化和传递闭包剪枝。

### 7.4 版面感知切片流程

#### Step 1: 版面解析

`LayoutParser` 识别以下特殊区块并实施硬性禁止截断保护：
- LaTeX 公式块：`$$...$$`、`$...$`、`\[...\]`
- 代码围栏：` ``` ` 代码块
- Markdown 表格
- 标题层级

#### Step 2: 语义切片

计算相邻文本块的语义嵌入余弦相似度：

$$\text{Threshold} = \mu \cdot \text{Mean}(Sim) - \alpha \cdot \text{Std}(Sim)$$

低于动态阈值时执行切片。

#### Step 3: 父子块映射

| 块类型 | Token 大小 | 用途 |
|--------|-----------|------|
| 子块 (Child) | ~300 tokens | 高精度向量检索，提升召回率 |
| 父块 (Parent) | ~3000 tokens | 向大模型注入完整章节上下文，消除碎片化幻觉 |

**检索流程**：Child ANN 搜索 → 收集 parent_ids → Parent Lookup → 合并上下文

### 7.5 知识图谱自动构建

#### Step 1: 层次树实体消解

将大模型抽取的技术概念 $(u, v)$ 结合教材目录路径距离进行空间重合度解算：

$$\text{Alignment}(u, v) = w_1 \cdot \text{Cosine\_Sim}(\vec{E}_u, \vec{E}_v) + w_2 \cdot e^{-\| \text{Path}(u) - \text{Path}(v) \|}$$

当 $\text{Alignment} > 0.85$ 时在图谱中强行合并。

#### Step 2: Tarjan SCC 环检测与消除

```python
# Tarjan 强连通分量算法 — O(V+E) 线性时间
# 检测并消除知识图谱中可能导致寻路死锁的环路
```

#### Step 3: 传递闭包剪枝 (Transitive Reduction)

基于 BFS 的冗余边检测与移除：
- 若存在边 $A \to C$ 且存在路径 $A \to B \to C$，则 $A \to C$ 为冗余依赖边
- 剪枝后保留最精简的 DAG 结构

### 7.6 Elasticsearch 混合检索

**实现文件**: [`src/vector/elasticsearch_knowledge_base.py`](src/vector/elasticsearch_knowledge_base.py)

**核心特性**：
- **混合检索**：BM25（关键词匹配）+ HNSW（语义搜索）双路召回
- **RRF 融合**：Reciprocal Rank Fusion ($k=60$) 合并双路排序
- **字段级加权**：`content^4 > title_path^3 > headers^2`
- **双嵌入器**：HashingTextEmbedder（确定性、零依赖）和 SentenceTransformerEmbedder（BAAI/bge-small-zh-v1.5）

---

## 八、底层辅助算法二：基于双极门控的防幻觉验证

### 8.1 赛题对应要求

系统需具备完善的"防幻觉"与内容安全过滤机制，确保生成的学术内容无事实性错误、无敏感违规信息。

### 8.2 实现文件

[`src/agents/validator_node.py`](src/agents/validator_node.py)

### 8.3 算法核心逻辑

解决防幻觉深度校验引发的生成延迟长尾问题。构建**双极过滤门控机制**，将文本解耦为"学术事实轨"与"教学表述轨"独立审计，在保障流式极速响应的前提下实施严密事实核查。

### 8.4 双极门控机制

#### 第一极（符号实体与语法树硬匹配门控）

利用正则表达式和抽象语法树（AST）静态解析器，优先核对生成文本中的核心技术实体、专用函数和公式：
- **LaTeX 语法校验**：检测括号配对、命令合法性
- **Python AST 解析**：代码块语法正确性校验
- **通过则直接发放通行证** → 内容流式先行上屏展示（不阻塞 UX）

#### 第二极（带重叠区滑动窗口的异步 NLI 推理）

内容上屏的同时，后台启动带 64 Token 重叠区的滑动窗口（256 token 窗口），将文本句法完整切分后送入 NLI 模型，与知识库中的原始参考源 $C_r$ 进行蕴含度度量：

$$Score(p_j) = P(\text{Entailment} \mid p_j, C_r) + 0.5 \cdot P(\text{Neutral} \mid p_j, C_r) - 2.0 \cdot P(\text{Contradiction} \mid p_j, C_r)$$

#### 差异化控制与退避

| 内容轨道 | 校验策略 | 阈值 |
|---------|---------|------|
| 学术事实轨（公式、参数） | NLI 严格蕴含度 | $Score \ge 0.85$ |
| 教学表述轨（通俗比喻、修辞） | 放宽至向量相似度 | 较低阈值 |

**幻觉修复流程**：
1. 触发严重矛盾（Contradiction）→ 前端对该段文本高亮标记"*导师正在校准中...*"
2. 后台触发单点微观修正循环（Refinement Loop），最多 3 轮
3. 超过 3 轮仍未通过 → 提取本地知识库标准预置模版进行字面组装
4. 对接科大讯飞内容安全审查接口进行合规性硬阻断

---

## 九、底层辅助算法三：冷启动情境探针启发式追问

### 9.1 赛题对应要求

支持通过自然语言对话自动抽取特征，构建包含不少于 6 个维度的动态学生画像。

### 9.2 实现文件

[`src/infrastructure/cold_start.py`](src/infrastructure/cold_start.py)

### 9.3 算法核心逻辑

攻克冷启动交互阶段因用户发言极短导致的意图稀疏和画像死锁痛点，避免死循环式的机械问卷查户口，并引入贝叶斯先验自适应融合算法实现软着陆。

### 9.4 6 维画像槽位定义

| 维度 | 字段 | 可选值 |
|------|------|--------|
| 认知风格 | cognitive_style | visual / textual / practical |
| 学习动机 | motivation | academic_exam / skill_certification / project_driven / curiosity |
| 专业背景 | background | CS / EE / ME / math / physics / biology / business / liberal_arts / other |
| 学历层次 | education_level | high_school / bachelor / master / phd / self_taught |
| 时间预算 | time_budget_hours_per_week | 0.5 ~ 168.0 |
| 已有知识基础 | knowledge_base | 多选 8 类知识领域 |

### 9.5 核心状态机转移逻辑

```python
def handle_cold_start_interaction(user_input, current_state_vector):
    c_epoch += 1

    # 1. 调度 Agent 提取 6 维特征槽位
    extracted_slots = llm_slot_extract(user_input)
    current_state_vector.update(extracted_slots)

    # 2. 槽位完整 → 触发正式路径规划
    if filled_slots >= 6:
        return "TRIGGER_MAIN_PATH_PLANNING"

    # 3. 边界干预：3 轮硬上限 → 贝叶斯降级融合
    if c_epoch >= 3:
        fallback_profile = load_course_baseline_profile(context_env)
        final_profile = bayesian_blend_profile(
            current_state_vector, fallback_profile
        )
        return "FORCE_ENTER_STUDY_STAGE_WITH_BASELINE"

    # 4. 未达上限 → 下发技术情境探针
    return generate_next_situation_probe(current_state_vector)
```

### 9.6 技术情境探针设计

不直接询问维度名称，而是随机下发技术情境：

> *"假设生产服务器数据库变慢了，你倾向于先看生动的动画演示还是直接调试底层伪代码？"*

**单次回答可同时穿透解算 3 个维度**：知识基础、认知风格、易错偏好。未尽的纠偏任务移交给主算法中的 PID 平滑演进算法，在真实互动中逐步显影。

### 9.7 贝叶斯先验融合

当 c_epoch ≥ 3 且槽位未满时，激活贝叶斯降级融合：
- 使用条件概率表 (CPT) 推断缺失维度：$P(\text{background} \mid \text{cognitive\_style})$、$P(\text{education} \mid \text{cognitive\_style})$ 等
- MAP 估计 + 归一化
- 赋予较高的不确定性方差，在后续学习中逐步修正

---

## 十、底层辅助算法四：WFQ 特权队列与马尔可夫预测性缓存

### 10.1 赛题对应要求

多模态资源生成的响应效率需满足实际学习场景需求，提供"生成进度追踪"或"流式呈现"机制，避免长时间白屏等待。

### 10.2 实现文件

[`src/agents/content_mesh_node.py`](src/agents/content_mesh_node.py)

### 10.3 算法核心逻辑

防止多智能体并行生成至少 5 种个性化资源时，大模型高频并发导致底层 API 限流熔断或线程饥饿死锁。采用加权公平调度与马尔可夫拓扑分支预测，在时间轴上执行完美的削峰填谷。

### 10.4 带特权门控的加权公平队列（WFQ）

系统将并发网格解耦为两个级别的核心队列：

| 队列 | 令牌配额 | 服务对象 | 延迟目标 |
|------|---------|---------|---------|
| **特权队列** | 70% | 前屏骨架展示所需的轻量级流式资源（讲解文档、Mermaid 导图源码） | 1~2 秒 |
| **常规异步队列** | 30% | 大长尾、重资产的多模态教学视频、题库、实操案例 | 异步加载 |

**调度策略**：Virtual Finish Time（虚拟完成时间）调度。在任何全局高并发场景下，核心交互文本以流式绝对优先级输出。前端采用流式占位机制（Streaming Card Hydration）渲染带进度条追踪的卡片外壳。

### 10.5 基于马尔可夫转移矩阵的预测性缓存预生成

算法不等待用户点击"下一步"才启动生成。核心机制：

1. **转移矩阵**：利用全站历史路径转移日志训练轻量级马尔可夫状态转移矩阵
2. **Top-1 预测**：$P(v \mid u) \propto e^{-2.0 \cdot \text{edge\_cost}(u,v)}$
3. **影子预生成**：利用服务器闲置算力和常规异步队列的 30% 闲置令牌，在后台隐式启动对 $V_{k+1}$ 节点的重型富媒体资源的**影子预生成**
4. **缓存策略**：压入 Redis 局部高速缓存，LRU + TTL 淘汰
5. **毫秒级弹出**：学生点击切换时，资源卡片从缓存瞬间呈现

**重规划熔断**：一旦 Evaluator 触发全局路径重规划，调度层立即下发高优先级 `KILL_JOB` 信令，瞬间强行熔断废弃旧路径上的在途生成任务，回收令牌配额。

---

## 十一、数据层架构 —— AgentState / Neo4j / Milvus / Elasticsearch

### 11.1 全局状态模型 (AgentState)

**实现文件**: [`src/state/agent_state.py`](src/state/agent_state.py)

AgentState 是 LangGraph StateGraph 中流转的完整全局上下文，所有字段通过 Pydantic v2 严格校验。

#### 11.1.1 状态结构全景

```
AgentState
├── 标识字段
│   ├── user_id: str
│   ├── course_id: str
│   ├── current_node_id: Optional[str]
│   └── target_node_id: Optional[str]
├── static_profile: StaticProfile
│   ├── cognitive_style_distribution: CognitiveStyleDistribution
│   │   ├── visual_alpha/beta, textual_alpha/beta, practical_alpha/beta
│   ├── motivation: str (academic_exam|skill_certification|project_driven|curiosity)
│   ├── time_budget_hours_per_week: float
│   └── knowledge_base: List[str]
├── dynamic_profile: DynamicProfile
│   ├── knowledge_mastery: Dict[str, float]
│   ├── knowledge_mastery_records: Dict[str, KnowledgeMasteryRecord]
│   ├── error_type_distribution: ErrorTypeDistribution
│   │   ├── logic_flaw, syntax_error, boundary_miss
│   ├── continuous_fail_counter: int
│   ├── pid_errors: Dict[str, PIDErrorRecord]
│   ├── capability_radar: List[float] (5维)
│   ├── diagnostic_report_md: str
│   └── boundary_miss_ema_sequence: List[float]
├── active_path: List[str]
├── generated_resources: Dict[str, List[ResourceCard]]
├── latest_behavior: Optional[LatestBehavior]
├── c_epoch: int
├── re_plan_triggered: bool
├── pedagogical_strategy: str
├── recommended_resource_style: Optional[str]
├── tutor_response: Optional[Dict]
├── errors: List[str]
├── internal_state: Dict[str, Any]
├── session_start: str
└── iteration: int
```

#### 11.1.2 关键子结构

**LatestBehavior** — 最近交互行为数据包：
```python
class LatestBehavior(BaseModel):
    node_id: Optional[str]
    correctness: float        # 答题正确率 [0, 1]
    time_spent_ratio: float    # 实际/预估耗时比
    error_types: List[str]     # 本次错误类型
    resource_feedback: Dict[str, float]  # 资源评分 (1-5)
    help_request_count: int    # 求助次数
    # 加分项扩展
    tutor_query: Optional[str]  # Tutor答疑提问
    accuracy_rate: float       # 正确率
    code_pass_rate: float      # 代码通过率
    duration_ratio: float      # 耗时比率
```

**ResourceCard** — 多模态资源卡片：
```python
class ResourceCard(BaseModel):
    resource_id: str
    node_id: str
    card_type: str  # concept_map|code_snippet|interactive_exercise|video_summary|diagnostic_quiz
    content: str     # Markdown 格式
    difficulty: float
    cognitive_style: str
    parent_chunk_id: Optional[str]
```

### 11.2 Neo4j 知识图谱

**实现文件**: [`src/graph/neo4j_client.py`](src/graph/neo4j_client.py)

- **KnowledgeNode**：node_id, title, difficulty, estimated_hours, category, metadata
- **PREREQUISITE 关系**：dependency_type (strict/recommended/optional), weight
- **MASTERED 关系**：mastery score, timestamp（MERGE 语义，upsert）
- **子图提取**：K-hop 邻域查询，支持上游/下游/双向

### 11.3 Milvus 向量数据库

**实现文件**: [`src/vector/milvus_client.py`](src/vector/milvus_client.py)

| 集合 | 用途 | 块大小 |
|------|------|--------|
| Parent Collection | 大上下文块，提供完整学术语境 | 1000-2000 tokens |
| Child Collection | 小粒度块，高召回率向量检索 | 250-500 tokens |
| Video Slice Collection | 教学视频时序帧嵌入 | 按视频切片 |

**检索链路**：Child ANN → 收集 parent_ids → Parent Lookup → 合并上下文 → 注入 LLM

### 11.4 Elasticsearch 知识库

**实现文件**: [`src/vector/elasticsearch_knowledge_base.py`](src/vector/elasticsearch_knowledge_base.py)

- **索引映射**：dense_vector (HNSW cosine) + text fields
- **混合检索**：BM25 + HNSW → RRF 融合 (k=60)
- **字段加权**：content^4, title_path^3, headers^2
- **分块器**：MarkdownHeaderTextSplitter + 代码围栏保护 + 自然边界检测
- **双嵌入器**：HashingTextEmbedder + SentenceTransformerEmbedder

---

## 十二、LLM 集成层 —— 双后端大模型统一客户端

### 12.1 实现文件

[`src/llm/client.py`](src/llm/client.py)

### 12.2 双后端架构

| 后端 | 提供商 | 协议 | 认证方式 |
|------|--------|------|---------|
| DashScope | 阿里云 (Qwen) | OpenAI 兼容 REST API (`/chat/completions`) | Bearer Token |
| iFlyTek Spark | 讯飞星火 v4.0 | WebSocket → HTTP 代理 | HMAC-SHA256 (app_id + api_key + api_secret) |

### 12.3 LLMClient 统一接口

```python
class LLMClient:
    # Content Mesh 注入
    def generate_content(node_id, card_type, difficulty) -> str

    # Tutor (text track) 注入
    def generate_academic_explanation(query, reference_chunks) -> str

    # Tutor (diagram track) 注入
    def generate_mermaid_graph(query, text_explanation) -> str

    # Validator (Pole-2) 注入
    def compute_nli_entailment(text, ground_truth) -> float
```

### 12.4 注入机制

通过 `EduAgentGraph.inject_llm()` 方法将 LLMClient 统一注入到各 Agent Node：

```python
def inject_llm(self, llm_client):
    self._tutor = TutorAgentNode(
        milvus_client=None,
        llm_generator=llm_client,
    )
    self._mesh = ContentMeshNode(
        generate_fn=llm_client.generate_content,
    )
    self._validator = ValidatorNode(
        nli_fn=llm_client.compute_nli_entailment,
    )
```

---

## 十三、加分项一：Tutor Agent —— 三轨多模态智能辅导

### 13.1 实现文件

[`src/agents/tutor_node.py`](src/agents/tutor_node.py)

### 13.2 触发条件

当 `AgentState.latest_behavior.tutor_query` 非空时，LangGraph 条件边自动路由到 Tutor Node。

### 13.3 三轨答疑架构

| 轨道 | 内容 | 数据源 | 输出格式 |
|------|------|--------|---------|
| **Text Track** | 学术概念解释 | Milvus Parent Chunk 检索 + LLM 生成 | Markdown 文本 |
| **Mermaid Diagram Track** | 知识关系可视化 | LLM 生成 Mermaid `graph TD` 源码 | Mermaid 语法 |
| **Video Hydration Track** | 时序视频片段推荐 | Milvus Video Slice Collection 时序滑动窗口相似度搜索 | 视频片段元数据 |

### 13.4 MermaidSyntaxGuard

Tutor Node 内建 Mermaid 语法守护：
- 自动修复未闭合括号 `[` → `]`、`(` → `)`
- 过滤非法控制字符
- 补全缺失的 `graph TD` 声明

---

## 十四、加分项二：Assessment Node —— EMA 能力雷达与迟滞环策略

### 14.1 实现文件

[`src/agents/assessment_node.py`](src/agents/assessment_node.py)

### 14.2 5 维能力雷达

| 维度 | 指标 | 更新方式 |
|------|------|---------|
| 概念理解力 | concept_understanding | EMA (α=0.2) |
| 代码工程力 | code_engineering | EMA (α=0.2) |
| 逻辑推理力 | logical_reasoning | EMA (α=0.2) |
| 错题抗挫力 | error_resilience | EMA (α=0.2) |
| 时间管理力 | time_management | EMA (α=0.2) |

### 14.3 迟滞环策略控制器

双阈值带设计（$T_{\text{low}} = 0.40$，$T_{\text{high}} = 0.75$），防止策略频繁抖动：

| 当前状态 | 触发条件 | 目标状态 |
|---------|---------|---------|
| STANDARD_PATH | $A_{\text{mix}} < 0.40$ AND $C_{\text{fail}} \ge 2$ | SCAFFOLD_HELP |
| STANDARD_PATH | boundary_miss EMA 连续 3 次上升 | EDGE_CASE_DRILL |
| SCAFFOLD_HELP | $A_{\text{mix}} > 0.75$ | STANDARD_PATH |
| EDGE_CASE_DRILL | $A_{\text{mix}} > 0.75$ | STANDARD_PATH |

### 14.4 诊断报告

自动生成 Markdown 格式《多维度综合评估诊断报告》，包含：
- 各维度能力评估
- 学习策略建议
- 薄弱环节标识

---

## 十五、测试体系与质量保障

### 15.1 测试文件地图

| 测试文件 | 测试对象 |
|---------|---------|
| [`tests/test_e2e_integration.py`](tests/test_e2e_integration.py) | 端到端集成测试（10 阶段完整流程） |
| [`tests/test_evaluator_node.py`](tests/test_evaluator_node.py) | Evaluator Node 单元测试 |
| [`tests/test_profiler_node.py`](tests/test_profiler_node.py) | Profiler Node 单元测试 |
| [`tests/test_planner_node.py`](tests/test_planner_node.py) | Planner Node 单元测试 |
| [`tests/test_tutor_node.py`](tests/test_tutor_node.py) | Tutor Node 单元测试 |
| [`tests/test_assessment_node.py`](tests/test_assessment_node.py) | Assessment Node 单元测试 |
| [`tests/test_path_planner.py`](tests/test_path_planner.py) | PathPlanner 基础设施测试 |
| [`tests/test_pid_controller.py`](tests/test_pid_controller.py) | PIDController 基础设施测试 |
| [`tests/test_cold_start.py`](tests/test_cold_start.py) | 冷启动引擎测试 |
| [`tests/test_document_chunker.py`](tests/test_document_chunker.py) | 文档切片器测试 |
| [`tests/test_graph_builder.py`](tests/test_graph_builder.py) | 图谱构建器测试 |
| [`tests/test_elasticsearch_knowledge_base.py`](tests/test_elasticsearch_knowledge_base.py) | ES 知识库测试 |
| [`tests/test_e2e_live_llm.py`](tests/test_e2e_live_llm.py) | 真实 LLM 集成测试（需 API Key） |

### 15.2 E2E 集成测试覆盖的 10 个阶段

```
Phase 1:  冷启动画像采集
Phase 2:  正常学习交互
Phase 3:  作弊检测（高正确率 + 短时间）
Phase 4:  PID 阻尼防震荡
Phase 5:  C_fail 累积（连续失败 ≥ 3）
Phase 6:  硬切换干预触发
Phase 7:  全局重寻路触发
Phase 8:  资源卡片生成
Phase 9:  Validator 防幻觉校验
Phase 10: 收敛检测（mastery ≥ 0.85）
```

---

## 十六、附录：完整文件目录映射

```
EduAgent/
│
├── algorithm_design.md                     # 本文档 — 核心技术规范
├── DataStructures.md                       # 数据结构课程知识库 (1.17 MB)
├── requirements.txt                        # Python 依赖清单
│
├── scripts/
│   └── ingest_data_structure_kb.py         # ES 知识库数据注入脚本
│
├── src/
│   ├── orchestration.py                    # LangGraph 主编排器 + 冷启动编排器
│   │
│   ├── state/
│   │   ├── __init__.py                     # 导出 AgentState 及所有子模型
│   │   └── agent_state.py                  # Pydantic v2 全局状态定义 (含 10+ 子结构)
│   │
│   ├── llm/
│   │   ├── __init__.py                     # 导出 LLMClient, LLMConfig, Provider
│   │   └── client.py                       # 双后端 LLM (DashScope Qwen + 讯飞星火 Spark)
│   │
│   ├── agents/
│   │   ├── __init__.py                     # 导出全部 7 个 Agent Node
│   │   ├── evaluator_node.py               # 行为清洗 + PID评估 + 重寻路闸门
│   │   ├── profiler_node.py                # MAB汤普森采样 + 艾宾浩斯遗忘曲线
│   │   ├── planner_node.py                 # Neo4j DAG-Dijkstra 路径规划
│   │   ├── tutor_node.py                   # 三轨多模态智能辅导 (加分项)
│   │   ├── content_mesh_node.py            # WFQ调度 + 5类资源卡片 + 马尔可夫预生成
│   │   ├── validator_node.py               # 双极防幻觉校验 (AST/LaTeX + NLI)
│   │   └── assessment_node.py              # EMA能力雷达 + 迟滞环策略 (加分项)
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   └── neo4j_client.py                 # Neo4j CRUD + Cypher + 子图提取
│   │
│   ├── infrastructure/
│   │   ├── __init__.py                     # 导出全部基础设施服务
│   │   ├── pid_controller.py               # 工业级PID (抗饱和+无扰切换+自适应增益)
│   │   ├── path_planner.py                 # Kahn拓扑排序 + DAG-SSSP (4种策略)
│   │   ├── cold_start.py                   # 6维情境探针 + 贝叶斯先验融合
│   │   ├── document_chunker.py             # Layout-Aware 版面感知父子块切片
│   │   └── graph_builder.py                # Tarjan SCC + 传递闭包剪枝
│   │
│   └── vector/
│       ├── __init__.py
│       ├── milvus_client.py                # Parent-Child 双层向量检索
│       └── elasticsearch_knowledge_base.py # BM25 + HNSW + RRF 混合检索
│
├── tests/
│   ├── test_e2e_integration.py             # 主端到端集成测试 (10阶段)
│   ├── test_evaluator_node.py
│   ├── test_profiler_node.py
│   ├── test_planner_node.py
│   ├── test_tutor_node.py
│   ├── test_assessment_node.py
│   ├── test_path_planner.py
│   ├── test_pid_controller.py
│   ├── test_cold_start.py
│   ├── test_document_chunker.py
│   ├── test_graph_builder.py
│   ├── test_elasticsearch_knowledge_base.py
│   └── test_e2e_live_llm.py
│
└── venv/                                   # Python 虚拟环境
```

---

## 算法复杂度汇总

| 算法 | 实现文件 | 时间复杂度 | 空间复杂度 |
|------|---------|-----------|-----------|
| Kahn 拓扑排序 | `path_planner.py` | $O(V+E)$ | $O(V)$ |
| DAG-SSSP | `path_planner.py` | $O(V+E)$ | $O(V)$ |
| Tarjan SCC | `graph_builder.py` | $O(V+E)$ | $O(V)$ |
| 传递闭包剪枝 | `graph_builder.py` | $O(V \cdot (V+E))$ | $O(V^2)$ |
| 汤普森采样 | `profiler_node.py` | $O(K)$ (K=臂数) | $O(K)$ |
| PID step | `pid_controller.py` | $O(1)$ | $O(1)$ per node |
| RRF 融合 | `elasticsearch_knowledge_base.py` | $O(N \log N)$ | $O(N)$ |
| 滑动窗口 NLI | `validator_node.py` | $O(W)$ (W=窗口数) | $O(W)$ |
| EMA 更新 | `assessment_node.py` | $O(1)$ per dim | $O(1)$ |

---

> **文档版本**: v2.0  
> **最后更新**: 2026-06-13  
> **项目仓库**: https://github.com/Joel-Ellen/ZXXC  
> **许可证**: 本文档随 EduAgent 项目一同发布。
