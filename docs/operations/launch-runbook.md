# EduAgent 灰度上线与回滚运行手册

本文定义步骤 10 的发布操作、证据和停止条件。它不把本地测试、Mock API、单进程指标或一次成功请求当成真实生产灰度的证明。

## 1. 适用范围与职责

- 发布负责人：确认制品、变更单、灰度比例和回滚决定。
- 值班工程师：观察告警、保存每个窗口的证据，并执行停止或回滚。
- 数据负责人：确认学习事件与掌握度归因完整，批准数据库变更。
- 安全负责人：确认凭据事件已经处置，安全扫描不存在未接受的高危项。
- 产品验收人：使用内部测试账号在真实 staging 后端完成 P1 学习流程。

生产灰度、真实用户开放、告警触发和回滚演练必须在外部部署环境完成。本地仓库无法证明这些动作已经发生，禁止用本地测试结果代替外部证据。

## 2. 凭据事件处置

仓库历史曾包含服务器登录凭据，协作记录中也曾暴露过第三方 API 密钥。发布前必须完成以下动作，且不得在工单或日志中复述秘密值：

1. 立即吊销和轮换服务器登录凭据、第三方 API 密钥、JWT 签名密钥、ops token 及受影响的数据库凭据。
2. 禁用服务器 root 密码登录，改用独立、可撤销、带来源限制的 SSH key；检查异常登录、sudo、部署和密钥使用日志。
3. 删除工作树中的明文秘密，并使用 `git filter-repo` 或等价工具清理所有远端 Git 历史；轮换必须先于历史清理。
4. 作废历史部署压缩包和缓存制品，重新从已审计提交构建不可变镜像。
5. 在秘密扫描通过后再开放推送和部署。证据记录只保存密钥标识、轮换时间、负责人和工单号，不保存密钥内容。

## 3. 发布前检查

每次发布从一个已保护分支的确定提交开始。发布负责人逐项确认：

- Python、前端 lint、typecheck、Vitest、Playwright、axe 和依赖审计全部通过。
- secret scan、Python 依赖审计、SAST、容器镜像扫描和只读 DAST 已通过；高危项必须关闭或有书面风险接受。
- 镜像由 CI 构建并按 digest 部署，例如 `registry/eduagent@sha256:...`。将该完整引用写入 `EDUAGENT_IMAGE`，并配置精确的 `EDUAGENT_COSIGN_IDENTITY` 与 `EDUAGENT_COSIGN_OIDC_ISSUER` 后使用 `deploy.sh`；脚本拒绝 tag、验证 keyless 签名，并禁止在目标主机执行 `docker compose up --build`。
- 生产必须提供非默认的 Postgres、Redis、Neo4j、MinIO、JWT 和 ops 凭据；Sentry 或同类前端监控必须配置并验证事件可达。
- `/api/health` 只证明进程存活；`/api/ready` 必须验证生产配置、Postgres 和共享 Redis，返回 `200 {"status":"ready"}` 后才能接收流量。
- 兼容/调试接口在无 ops token 时返回 404；生产指标接口在无 ops token 时返回 404。
- 测试用户、假进度、历史部署包和本地数据不得进入生产数据库或运行镜像。
- 已生成数据库备份并完成一次可验证的恢复检查；记录备份 ID、校验和、恢复环境和耗时。
- 数据库变更采用 expand/migrate/contract，当前版本和上一版本必须能同时使用 expand 阶段的 schema。
- 代码执行 sandbox 在 staging 中真实可用；没有隔离执行器时保持代码练习 rollout 为 0，禁止宿主机降级执行。
- Nginx 对正式 Tutor SSE 路径关闭 buffering/cache，验证首 token 延迟、断流重试和 300 秒以内的合理超时。

任何检查项缺证据均视为未完成，而不是默认通过。

### 3.1 安全镜像发布

镜像只能通过 [`.github/workflows/release-image.yml`](../../.github/workflows/release-image.yml) 手工发布。发起人必须选择仓库默认分支，同时输入精确的 `PUBLISH` 和该次运行所选的完整 40 位 commit SHA；任一输入不匹配都会在 checkout 和 registry 登录前失败。工作流从 `github.repository` 派生全小写 GHCR 名称，只发布 `sha-<完整 commit>` 标签，不创建或移动 `latest`。

发布按不可绕过的两个 job 执行：

1. Buildx 构建并推送镜像，同时生成 SPDX SBOM 和 SLSA provenance。后续步骤只使用 Buildx 返回的 `sha256:` digest，并从 registry 取回 SBOM、provenance 和原始 manifest 作为证据。
2. Trivy 对 `<小写 GHCR 名称>@sha256:<digest>` 扫描 OS 和应用依赖。任何 `HIGH` 或 `CRITICAL` 漏洞都会使 job 失败；失败时仍上传已有扫描证据，但签名 job 不会启动。
3. 只有扫描 job 成功后，独立签名 job 才获得 `id-token: write`，使用 GitHub OIDC 和 Cosign keyless 模式签署同一 digest，并按当前 workflow identity 和 `https://token.actions.githubusercontent.com` issuer 立即验证签名。

成功运行会产生 `release-image-build-scan-<run>-<attempt>` 和 `release-image-signature-<run>-<attempt>` 两个 artifact，包含镜像坐标、manifest、SBOM、provenance、Trivy JSON、Cosign bundle、签名验证结果和文件校验和。artifact 目录由工作流显式列出，不得加入环境转储、Docker 登录配置、token、secret、应用数据或日志正文。签名和 artifact 不是部署授权；发布负责人仍需核对 commit、digest、扫描、签名 identity 及本节其余发布前证据，再把完整 digest 写入 `EDUAGENT_IMAGE`。

## 4. 内部账号与 allowlist

1. 使用已有的专用内部测试账号，不允许 smoke 脚本注册账号或打印访问令牌。
2. 账号必须加入 `EDUAGENT_APP_ACCESS_ROLLOUT_ALLOWLIST`。需要验证代码练习时，同时加入 `EDUAGENT_CODE_PRACTICE_ROLLOUT_ALLOWLIST`。
3. denylist 优先于 allowlist；发布前检查同一账号没有同时存在于两者。
4. 访问令牌通过受控登录流程生成，作为 CI/staging secret 注入。不得写入命令行参数、GitHub 日志、截图或 JSON 证据。
5. 内部账号的课程、节点和复习数据必须可清理且与真实用户隔离。

## 5. 真实后端 P1 流程

以下流程必须连接真实 staging Postgres、Redis、反向代理、Tutor SSE 和隔离代码执行器，禁止使用 Playwright Mock API 或 monkeypatch：

1. 登录，验证 5 秒内出现可执行的下一学习任务。
2. 搜索课程、查看详情、加入课程并确认切课。
3. 打开学习节点，刷新页面，确认课程、节点、学习视图、滚动位置和草稿恢复。
4. 查看讲解和示例，逐题选择并提交答案，确认尝试次数、提示使用和解析被保存。
5. 编写代码，依次运行、查看公开失败用例、修改并提交；核对隐藏测试、运行时间、内存和结构化判题结果。
6. 制造一次真实未达标结果，确认进入“错因 -> 推荐材料 -> 相似题 -> 复测 -> 掌握度更新”的补救闭环。
7. 打开复习队列，完成定向练习和复测，确认错误类型、原答案、正确答案、解析、节点、下次复习时间和状态持久化。
8. 向 Tutor 发送概念和代码调试问题，确认 context type、代码、错误消息及 `tutor_question` 事件可追溯。
9. 对登录、选课、资源、Tutor SSE、答题、代码 run/submit、复习和复测分别注入一次 5xx 或断流，确认原位重试、输入保留和幂等结果。
10. 退出并重新登录，确认最近课程、学习资产、复习任务和诊断报告恢复。

每一步保存：release ID、UTC 时间、脱敏账号标识、request ID、session/course/node/resource/question/event ID、预期结果、实际结果及截图或测试报告。不得保存令牌、答案密钥或学习内容全文。

## 6. 可重复 staging smoke

工具为 [`scripts/release_smoke.py`](../../scripts/release_smoke.py)。它只从环境读取地址和令牌，不创建账号、不写学习事件、不跟随重定向，也不输出响应正文或请求头。

支持的秘密环境变量：

- `EDUAGENT_SMOKE_BASE_URL` 或 `BASE_URL`
- `EDUAGENT_SMOKE_ACCESS_TOKEN` 或 `ACCESS_TOKEN`
- `EDUAGENT_SMOKE_OPS_TOKEN`、`EDUAGENT_OPS_TOKEN` 或 `OPS_TOKEN`

可选的真实恢复读检查：

- `EDUAGENT_SMOKE_SESSION_ID`
- `EDUAGENT_SMOKE_NODE_ID`

在 CI secret store 中注入变量后运行：

```bash
python scripts/release_smoke.py preflight
```

`preflight` 验证 liveness、readiness、调试面隐藏、指标私有、用户接口鉴权，以及内部账号的课程、摘要、资料和设置。提供 session ID 后还会只读验证会话、事件账本、学习资产、复习队列和节点资源恢复。

退出码：

- `0`：全部通过。
- `1`：远端检查或指标失败。
- `2`：配置不安全、参数无效或指标 schema 无效。
- `3`：指标样本不足，保持当前 cohort 并继续采样，禁止扩容。

工具输出一行 JSON，可直接保存为发布证据。输出不会包含 token 或响应正文。

## 7. 受控 GET 压测

压测必须同时满足：

- 显式执行 `load` 子命令。
- 环境变量 `EDUAGENT_SMOKE_ALLOW_LOAD=true`。
- 目标为 loopback、`.test`、`.internal` 或 hostname label 明确含 `staging`；特殊 staging 域名需在 `EDUAGENT_SMOKE_LOAD_HOST_ALLOWLIST` 中精确列出。
- 远程目标使用 HTTPS；HTTP 仅允许 loopback。
- 路径属于脚本固定的只读 GET allowlist。

示例：

```bash
export EDUAGENT_SMOKE_ALLOW_LOAD=true
export EDUAGENT_SMOKE_LOAD_PATH=/api/ready
export EDUAGENT_SMOKE_LOAD_REQUESTS=100
export EDUAGENT_SMOKE_LOAD_CONCURRENCY=5
python scripts/release_smoke.py load
```

默认上限为 200 请求、10 并发和 30 秒单请求超时。输出包含吞吐、p50、p95、p99、5xx、429、transport error 和非预期状态比例。默认门槛为：

- 5xx `< 1%`
- transport error `= 0%`
- 非预期状态 `= 0%`
- 429 `<= 5%`，可通过 `EDUAGENT_SMOKE_LOAD_MAX_429_RATE` 收紧
- p95 `<= 2000 ms`，可通过 `EDUAGENT_SMOKE_LOAD_MAX_P95_MS` 调整

此工具用于可重复的有界 smoke，不是生产容量认证。更高负载必须使用经审批的隔离压测环境和专用工具，并设置流量、时长和停止上限。

## 8. 发布指标闸门

运行：

```bash
export EDUAGENT_SMOKE_MIN_SAMPLES=200
export EDUAGENT_SMOKE_FRONTEND_SESSIONS=200
python scripts/release_smoke.py gates
```

`EDUAGENT_SMOKE_FRONTEND_SESSIONS` 必须来自与指标快照同一发布、cohort 和时间窗口的可信分析系统。直接读取当前单进程累计端点时，分母还必须覆盖同一次进程启动以来的相同区间；生产窗口应由外部指标系统计算。脚本使用以下门槛：

| 指标 | 推进门槛 | 说明 |
|---|---:|---|
| 刷新恢复成功率 | `>= 99%` | success / (success + failure) |
| 登录后 5 秒内下一任务就绪 | `>= 99%` | within_5s / total |
| 登录基础设施失败率 | `< 1%` | 仅 storage/session persistence，排除密码错误、验证码和 holdback |
| 资源生成失败率 | `< 1%` | 真实请求 5xx/失败结果 |
| 代码执行基础设施失败率 | `< 1%` | 只看 sandbox/infrastructure，不把学生 wrong answer 视为服务故障 |
| 前端异常会话率 | `< 1% sessions` | authenticated exception count / trusted session denominator |
| 掌握度归因完整率 | `100%` | 每次 mastery mutation 均有真实 event ID，unattributed 必须为 0 |

闸门状态：

- `PASS`：达到门槛且样本足够，可以结合其他证据决定推进。
- `FAIL`：保持当前比例；连续窗口失败时回滚。
- `INSUFFICIENT`：保持比例继续采样，禁止把空样本当 0 或成功。
- `INVALID`：观测链路或 schema 故障，阻断推进。

当前 `/api/ops/metrics` 是单进程累计快照，不含全局 window、release 或 cohort 聚合。它适合 staging smoke，不足以单独证明生产灰度达标。生产推进必须使用 Prometheus、OpenTelemetry 或等价外部系统按 release/cohort 计算窗口指标。

真实节点完成率必须从唯一 `lesson_opened` 与唯一 `lesson_completed` 的事件漏斗计算。`node_completions.rate` 只是 terminal event 接口接受率，禁止把它当学习完成率。

## 9. 灰度顺序与连续窗口

严格按以下顺序推进，不允许跳级：

| 阶段 | 最小合格样本 | 连续合格窗口 | 窗口长度 |
|---|---:|---:|---:|
| 内部 allowlist | 20 条完整 P1 路径证据 | 2 | 15 分钟 |
| 1% | 每个闸门 200 个合格样本 | 2 | 15 分钟 |
| 5% | 每个闸门 500 个合格样本 | 2 | 30 分钟 |
| 25% | 每个闸门 1000 个合格样本 | 3 | 30 分钟 |
| 50% | 每个闸门 2000 个合格样本 | 3 | 30 分钟 |
| 100% | 每个闸门 5000 个合格样本 | 4 | 30 分钟 |

每次只修改一个变量：应用访问比例或单个功能比例。窗口内发布版本、配置和 cohort 算法保持不变。

- 一个窗口 `FAIL`：停止推进，调查但保持当前 cohort。
- 两个连续窗口 `FAIL`：回滚至上一 digest，并将相关 rollout 调回 0 或上一稳定比例。
- `INSUFFICIENT`：继续当前比例，不推进、不因样本不足自动回滚。
- `INVALID`：视为监控失明，立即停止推进。
- 数据完整性、安全边界、秘密泄露、跨用户访问、无依据掌握度变化或 sandbox 逃逸：不等待连续窗口，立即停止流量并回滚。

## 10. 原位重试闸门

P1 故障矩阵中所有核心操作必须保留原页面、原输入和关联 ID，并允许同一动作重试：

- 登录、验证码和令牌刷新
- 课程目录、加入、退出和切换
- 会话、节点和资源恢复
- Tutor SSE 断流
- 逐题提交和诊断提交
- 代码运行、提交和学习事件补记
- 复习队列、定向练习和复测

每个动作至少验证一次 429、一次 5xx 或 transport failure；有幂等键的接口必须证明重试不会重复计分、重复 mastery mutation 或创建重复复习项。任一 P1 动作不能原位重试时禁止扩大 cohort。

## 11. 回滚

发布前记录 `CURRENT_DIGEST`、`PREVIOUS_DIGEST`、配置版本、数据库迁移版本和 rollout 值。回滚流程：

1. 立即停止扩大 cohort，将应用/功能 rollout 调回 0 或上一稳定比例。
2. 将负载均衡流量切回 `PREVIOUS_DIGEST`，禁止在主机重新构建“上一版”。
3. 等待上一版本 `/api/ready` 成功，再执行只读 preflight 和内部账号 P1 恢复检查。
4. 确认登录、资源、代码基础设施、前端异常、刷新和 5 秒就绪指标恢复。
5. 保留失败版本日志、request IDs、event IDs 和指标窗口，创建事故记录。

数据库迁移必须向后兼容。常规应用回滚不得自动执行 schema downgrade。若发生数据损坏，由数据负责人依据已验证备份单独批准恢复，并记录恢复点、丢失窗口和一致性检查。

至少每季度在 staging 演练一次“新 digest -> 触发闸门 -> 切回上一 digest -> 验证状态恢复”。真实生产回滚演练必须由生产变更单授权，不能在本机伪造完成。

## 12. 外部证据记录

每个阶段保存一份不可变发布记录，至少包含：

- release ID、Git commit、镜像 digest、SBOM 和签名验证结果
- staging/production 环境标识、开始与结束 UTC 时间、审批人
- rollout 配置版本、比例、allowlist/denylist 变更摘要，不保存用户明文列表
- readiness、preflight、真实 P1、load、安全扫描和依赖扫描结果
- 每个闸门的 numerator、denominator、rate、最小样本、窗口和 dashboard 查询链接
- 掌握度变更对应的 event ID 抽样和 100% 归因查询结果
- 原位重试故障矩阵、幂等验证和刷新恢复结果
- 数据库备份 ID、恢复验证、迁移兼容性结论
- 回滚决定、上一 digest、执行时间、恢复时间和复盘链接

只有外部证据完整、连续窗口达标、P1 真后端流程通过，才能把该阶段标记为完成。
