# 🤖 AI Learning Assistant - 多智能体学习系统

**基于大模型的个性化资源生成与学习多智能体系统**

> 🏆 软件杯国家级竞赛项目 | 10 Agent协同 | 8类资源生成 | 5阶段学习路径

---

## 🎯 项目简介

「智学星辰」是一个面向高校学生的AI学习助手系统，利用大模型、多智能体协同、RAG知识库等技术，为学生提供个性化学习资源生成、学习辅导与学习路径规划服务。

## ✨ 核心功能

- 🎯 **对话式学习画像构建** - 自然语言对话自动构建8维学习画像
- 🤖 **10Agent多智能体协同** - 画像→分析→规划→生成→辅导→评估
- 📚 **8类个性化资源生成** - PPT/讲义/思维导图/题库/项目/笔记/视频脚本/动画脚本
- 🗺️ **5阶段学习路径规划** - 基础→核心→综合→项目→提升
- 🎓 **智能辅导系统** - 概念讲解/错题解析/代码调试/学习建议
- 📊 **学习效果评估** - 6维度评估+雷达图+改进建议

## 🏗️ 系统架构

```
前端 (Vue3 + Vite) → API网关 (FastAPI) → 多Agent编排器 → LLM/RAG/Chroma
```

## 📁 项目结构

```
AI_Learning_Assistant/
├── backend/           # FastAPI后端
│   ├── agents/        # 10个AI Agent
│   ├── models/        # 数据库模型
│   ├── services/      # LLM/RAG/Embedding服务
│   ├── routes/        # API路由
│   └── utils/         # 安全/工具
├── frontend/          # Vue3前端
│   └── src/
│       ├── views/     # 7个页面
│       ├── components/
│       ├── stores/    # Pinia状态管理
│       ├── router/    # Vue Router
│       └── api/       # API模块
├── data/              # 知识库数据
└── docs/              # 竞赛文档
```

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- SQLite（开发）/ PostgreSQL（生产）

### 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000/docs 查看API文档

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

### 配置LLM

```bash
# 设置环境变量（选择任一厂商）
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=your_api_key

# 或使用讯飞星火
export LLM_PROVIDER=spark
export SPARK_API_KEY=your_key
export SPARK_API_SECRET=your_secret
export SPARK_APP_ID=your_app_id
```

## 🤖 10个智能Agent

| Agent | 职责 | 依赖 |
|-------|------|------|
| StudentProfiler | 学生画像构建 | - |
| KnowledgeAnalysis | 知识点拆解 | Profiler |
| ResourcePlanner | 学习资源规划 | Profiler, Analysis |
| PPTGenerator | 课件生成 | Planner |
| QuestionGenerator | 题库生成 | Planner |
| MindMapGenerator | 思维导图生成 | Planner |
| CodingPractice | 代码实战生成 | Planner |
| VideoScript | 视频脚本生成 | Planner |
| LearningCoach | 学习指导 | Profiler, Analysis |
| Evaluation | 学习评估 | Profiler, Coach |

## 🔗 与原系统（智绘青春）的关系

本系统是「智绘青春」职业规划系统的拓展：
- **原系统**：帮你找到职业方向
- **新系统**：帮你学会所需技能
- **完整闭环**：职业目标→技能需求→学习路径→能力达成

## 📄 文档

- [竞赛完整方案文档](docs/竞赛方案文档_完整版.md)

## 📝 License

MIT
