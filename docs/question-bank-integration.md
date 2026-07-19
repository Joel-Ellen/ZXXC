# 数据结构题库接入

## 运行链路

数据结构诊断测验沿用现有资源生成链路：

`本地题库 → 当前学习节点候选检索 → ResourceContext → LLM diagnostic_quiz → 本地校验/盲验 → 服务端验答`

题库候选只提供题型、场景和常见问法。它们不是可信指令，也不是已验证答案；LLM 必须依据当前节点的知识库证据重新确定唯一答案。无法确认答案、含缺图占位、题干不完整或多小问混合的候选不会进入生成上下文。

## 已导入数据

规范化文件位于 `src/question_bank/data_structures_questions.json`，其中保留：

- 12 份原始抽取文档的全文和 blocks，便于以后重新切题；
- 1706 条启发式 question candidates；
- 稳定题目 ID、题型、节点映射、质量问题和去重信息；
- 按节点建立的可生成候选索引；
- 内容摘要生成的 `collection_version`。

`题库_汇总.json` 与 12 份分章文档完全重复，导入器只读取顶层带 `question_candidates` 的分章文档，避免整库重复。

导入器拒绝路径穿越、符号链接、异常压缩比、超大成员、超过 20,000 条候选或规范化后超过 16 MiB 的题库；完全重复的分章会跳过，重复候选仍保留审计记录但使用唯一 ID 且不能进入生成索引。进入 LLM 的候选只保留有界白名单字段，任意对象型元数据不会进入 Prompt。

N18（动态规划）和 N19（贪心/回溯）在本题库中没有可靠覆盖。系统会仅根据对应学习节点的知识库内容调用 LLM 出题，不会从其他节点借题。

## 重新导入

```powershell
python scripts/import_question_bank.py "C:\path\to\题库_JSON.zip"
```

也可以用 `--output` 指定其他输出路径，再通过 `EDUAGENT_QUESTION_BANK_PATH` 配置。

相关环境变量：

```text
EDUAGENT_QUESTION_BANK_ENABLED=true
EDUAGENT_QUESTION_BANK_PATH=
EDUAGENT_QUESTION_BANK_MAX_CANDIDATES=6
EDUAGENT_QUIZ_SHUFFLE_SECRET=
```

多 worker 生产环境应为 `EDUAGENT_QUIZ_SHUFFLE_SECRET` 配置至少 32 字符、稳定且不可公开的随机值；未配置或长度不足时，每个进程会使用临时加密随机密钥。该密钥只用于打乱正确选项位置，不进入资源响应。

题库版本会合并进 `knowledge_index_version`，因此内容变化会自动隔离现有生成幂等键和资源缓存。

## 评分安全边界

- 公共资源响应不会下发 `answer_index`、`distractor_error_tags` 或提交前解析。
- 前端只提交题目 ID 和所选下标，分数、逐题结果和解析均以服务端响应为准。
- 正确选项位置使用服务端秘密 HMAC 排列，不能由公开的节点 ID、题序或测验轮次推导。
- 每题必须有四个非空且互不相同的选项，服务端答案和用户答案都必须在选项范围内。
- 同卷重复题目 ID、重复题干、未知题库来源 ID、`[OBJECT]` 占位题会在发布前被拒绝。
- 选项重排会同步重排干扰项错误标签。
- 只读缓存不会直接展示尚未绑定到当前会话的诊断测验；生成任务必须先把含服务端答案的完整副本恢复到会话，之后才会下发脱敏版本。
- LLM 输出仍需通过结构校验、节点证据约束和逐题盲答一致性检查。盲验服务请求协议为 `diagnostic-blind-v2`，响应必须逐题返回 `id` 和 `selected_index`；旧协议会拒绝 LLM 测验，并回退到服务端预验证模板，同时将质量状态标为降级。
- 互动练习与诊断测验使用隔离的 LLM 调用，题库候选只进入诊断测验 Prompt。
