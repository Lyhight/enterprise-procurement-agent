# 系统架构

## 业务流程

1. 接收采购申请并校验字段。
2. 根据品类、合规状态和风险等级筛选供应商。
3. 综合供应商评分、交付能力、合作年限和报价计算推荐分。
4. 根据总金额与高风险信号确定审批等级。
5. 输出推荐清单、决策理由和需要人工关注的警告。

## 模块边界

- `domain/`：业务模型与确定性采购政策，不依赖 HTTP 或数据库。
- `application/`：需求解析、供应商评分、权限校验和工作流用例。
- `agents/`：LangGraph 状态图与 Agent 节点编排。
- `infrastructure/`：CSV/SQLite 仓储、知识库和外部系统适配层。
- `api/routers/`：按需求、申请、报价、审批、知识库和审计分类的 HTTP 接口。
- `interfaces/`：命令行等非 HTTP 用户入口。
- `core/`：配置及跨模块基础能力。
- `frontend/`：React + TypeScript 采购管理控制台，通过同源 `/api/v1` 调用后端。
- `scoring.py`：供应商多维评分算法。
- `workflow.py`：编排完整采购分析过程。
- `api.py`：对外 HTTP 接口。

## 管理控制台

`frontend/` 使用 Vite 构建单页管理控制台，页面按运营总览、需求录入、多轮需求澄清、采购申请、Agent 运行、订单履约、OA/ERP 集成和审计治理分类。控制台直接调用真实 FastAPI 接口，可完成需求解析与提交、对话式字段补全、询价建单、供应商报价录入、Agent 分析与检查点恢复、人工审批、来源证明验证、供应商定标、外部系统同步、订单状态推进和收货记录追踪。开发环境由 Vite 代理 `/api`；生产构建由 FastAPI 挂载到 `/app/`，Docker 使用多阶段构建生成同一静态产物。Bearer Token 只保存在浏览器本地存储，不写入前端源码或构建文件。

开发环境通过源码位置推断项目根目录。普通 wheel 或容器安装通过 `PROJECT_ROOT` 显式定位 `data/`、`evals/` 和 `frontend/dist/`；Docker 镜像固定使用 `/app`，避免安装到 `site-packages` 后错误解析资源路径。

## Agent 节点

核心执行图是可循环的：`plan → execute_tool → plan`，上下文充分后依次进入 `validate_decision → finalize`。本地 Planner 根据当前 State 中缺失的事实动态选择申请、供应商、报价或制度工具；每次执行结果写回 State，下一轮基于新观察重新规划。`max_iterations` 防止错误 Planner 无限调用。

每次运行还会把 `run_started_at` 和 `run_deadline_at` 写入 LangGraph State。计划、工具和最终生成阶段都检查墙钟时间预算；工具返回时若已超时，该步骤标记为 `BUDGET` 失败且不自动重试，checkpoint 与 Trace 保留现场。人工显式恢复会分配新的时间窗口，但不会重新执行已完成步骤。

`infrastructure/execution_control.py` 保存幂等的执行取消请求。运行图在工具调用前后和重规划边界读取取消信号；已经开始的同步工具允许完成，但结果不会继续驱动采购决策。取消后的 State 标记为 `CANCELLED`，Trace 使用独立的 `RUN_CANCELLED` 终态，避免把人为停止误计为系统失败。

OpenAI Planner 的输出必须通过步骤、工具映射、依赖顺序和事实就绪校验。模型超时、返回结构错误或选择非法步骤时，系统回退到本地确定性 Planner；首次模型失败会打开本次运行级熔断，后续 Replan 不再反复等待同一故障模型。每次规划的实际来源、是否真实调用模型和降级原因写入 `planner_events`、调用/失败/降级计数及持久化 Trace，因此配置了模型不等于默认宣称模型成功参与了决策。

`agents/context/security.py` 把采购申请、工具观察、RAG 文档和长期记忆统一视为不可信业务数据。上下文在发送给模型 Replanner 前会先经过长度约束、敏感字段脱敏和指令型内容扫描；检测到角色伪造、指令覆盖或密钥提取语句时，本轮不调用外部模型，直接采用本地确定性计划，并把不含原始恶意文本的风险类别与字段路径写入 Planner 降级 Trace。本次运行随后打开已有的 Planner 熔断，避免同一污染上下文被重复外发。

最终业务决策轨迹按 `load_request → validate_request → screen_suppliers → collect_quotations → rank_suppliers → check_policy → retrieve_policy → validate_decision → finalize` 输出，便于审计人员理解；底层同时保存每轮工具、参数、规划理由和观察结果。

`agents/guardrails.py` 是独立于 Planner 和工具输出的确定性发布闸门。它在生成最终结果前交叉复核候选供应商准入、报价申请及供应商归属、推荐唯一性和金额、审批等级、路由以及制度证据。结构正确但跨工具事实互相矛盾的结果会触发 `DecisionGuardrailError`，写入 `DECISION_VALIDATION_FAILED` 与 `RUN_FAILED` Trace，且不会发布为成功决策。

每次执行除了返回节点级业务 `trace`，还会把运行开始、规划、工具调用、重规划、失败、恢复和完成事件追加写入 SQLite。事件包含统一 `run_id`、步骤、耗时和脱敏后的上下文，可重建稳定的执行时间线。

Trace 事件使用 SHA-256 构建逐运行哈希链，并在独立链头表中保存最终哈希与事件数量。写事件时通过 `BEGIN IMMEDIATE` 原子更新事件和链头，可检测内容修改、中间删除、顺序变化及尾部截断。旧数据库首次初始化会只为尚未签链的历史事件补链；已有哈希不会自动重算，因此后续篡改不会被初始化流程掩盖。该机制用于数据库内的篡改检测，不替代外部 WORM 存储或独立时间戳签名。

`agents/provenance.py` 对工具参数、完整工具输出、事实快照和最终决策执行规范化 JSON 哈希。最终 `AnalysisResult.provenance` 固化系统 Prompt 版本、Planner 来源和工具契约版本；相同版本与相同事实应得到相同指纹，供应商、报价、制度证据或决策输出变化会产生不同指纹。运行编号、时间和耗时不进入决策指纹，避免非业务噪声破坏复现比较。

来源指纹由申请、合格供应商、有效报价和制度检索工具的参数/输出哈希清单生成。来源验证会从最终结果的 `tool_calls` 重建清单，API 还会从防篡改 Trace 独立重放同一清单，并联合检查 Trace 哈希链。结果内工具证据、持久化执行证据或最终结论任一侧不一致，来源证明均不会通过。

`domain/ruleset.py` 是确定性采购规则的版本化清单，审批金额阈值、最低询价数、供应商准入条件、风险分和评分权重均由该清单驱动，不再散落为魔法数字。规则版本及清单指纹进入决策指纹；历史结果校验接口会分别报告决策内容完整性以及 Prompt、工具契约、规则集与当前部署是否一致。

`/metrics` 同时暴露进程内 HTTP 指标和基于持久化 Trace 聚合的 Agent 指标，包括运行成功/失败、恢复成功/失败、工具失败率、Planner 降级决策数和终态平均耗时。Agent 指标在 API 服务重启后仍可从 SQLite 恢复。

`procurement-agent-maintenance` 执行 Trace 与长期记忆的数据保留策略。命令默认为 dry-run；只清理超过保留期且已经终止的执行，不会删除仍在运行的 checkpoint 现场。失败运行和人工审批决定默认受保护，删除这些证据必须通过单独的显式参数开启。

L2、L3 或带有合规警告的运行进入 `AWAITING_APPROVAL`。审批接口将其推进到 `COMPLETED` 或 `REJECTED`；服务重启后仍可通过 `run_id` 恢复查询。

自然语言需求在字段完整时写入 SQLite，并通过组合数据仓库与模拟 CSV 数据统一查询。询价创建操作只选择同品类、合格且非高风险的供应商，并以数据库唯一约束保证重复请求不会重复建单。

供应商报价与询价单一一对应，数据库同时限制同一申请下同一供应商只能提交一份报价。动态报价会自动进入 Agent 的价格评分。审批前校验员工审批等级并禁止申请人审批自己的申请，关键操作写入不可变审计事件表。

多轮需求澄清由 `application/conversation.py` 管理业务状态，由 SQLite 保存会话、草稿和消息。用户可以分多条消息补齐信息，服务重启后继续同一会话，完整后再生成正式采购申请。

定标与订单执行由 `application/orders.py` 管理。订单使用显式状态机限制非法跳转，收货数量必须与验收结果一致，累计收货完成后自动进入 `DELIVERED`；所有状态变化和收货动作同时进入审计链路。

自然语言理解通过 `application/ports/language_model.py` 定义端口。默认使用本地规则实现；配置 OpenAI 后由 `infrastructure/llm/openai_understanding.py` 使用 Responses API Structured Outputs 返回受 Pydantic 模型约束的字段。模型只负责理解输入，金额审批、供应商风险、定标和订单状态仍由确定性业务代码控制。

Agent 可调用能力集中在 `agents/tools/`，工具同时供确定性图节点和后续 LLM tool calling 使用。`prompts/` 保存带版本号的系统提示词和任务提示词。LangGraph 在制度检查后根据推荐结果与警告动态路由到正常审批、人工复核或扩展寻源分支。

`agents/tool_registry.py` 是模型或规划器调用企业数据的安全边界，仅允许登记的只读工具，并在执行前通过 `ToolAccessPolicy` 检查调用主体角色。`agents/local_tool_agent.py` 使用受限系统主体完成不外发企业数据的本地规划与多工具调用，并保存每次调用的参数和输出摘要。外部模型适配器必须在部署方明确允许企业数据外发后才能启用。

`agents/tool_contracts.py` 为每个白名单工具定义严格的 Pydantic 输入和输出契约。未知参数、空标识、越界检索数量、畸形业务对象或不符合声明的工具返回值会在进入 Agent State 前被拒绝，并以 `ToolContractError` 写入 Trace，避免模型参数漂移或下游服务异常数据污染检查点。

`agents/core/errors.py` 将工具故障划分为瞬时故障、契约错误、权限拒绝、数据不存在、输入错误和内部错误。只有超时与连接中断自动消耗重试额度；确定性故障立即终止并保留 checkpoint，避免重复调用。错误类别和 `retryable` 标志同时进入执行计划、对外恢复视图和持久化 Trace，运维人员仍可在修复根因后显式恢复失败执行。

`core/auth.py` 只在内存中保存 Bearer 令牌摘要，`api/security.py` 完成身份解析和角色检查。受保护的工具 Agent API 只允许 `PROCUREMENT` 角色调用，并把认证得到的员工身份写入审计记录，不信任请求体传入的操作者身份。

当 `AUTH_ENABLED=true` 时，认证中间件覆盖全部 `/api/v1` 业务接口。Agent 审批、会话恢复、订单授标、状态变更和收货接口还会执行角色检查及“认证员工＝操作人”校验。生产环境未正确配置认证时，`/health/ready` 返回未就绪。

OA/ERP 集成通过应用端口隔离。`INTEGRATION_MODE=mock` 用于本地开发；`http` 模式使用 Bearer 凭证、连接超时和稳定的 `Idempotency-Key` 调用企业端点。只有部署方显式配置目标地址与密钥时才会向外部系统发送数据。

`integration_jobs.py` 提供 SQLite 持久化任务队列。Worker 使用 `BEGIN IMMEDIATE` 原子领取任务，避免多个进程重复处理；失败任务按指数退避重试，超过上限进入 `FAILED`，成功记录关联的集成结果。业务幂等键和集成记录唯一约束共同提供至少一次执行下的去重保护。

供应商询价使用独立 Outbox 表和发送 Worker。每张询价单只有一个发送任务，HTTP 网关携带稳定幂等键。报价回调不使用员工 Bearer Token，而是校验原始请求体的 HMAC-SHA256、时间窗口和唯一事件编号；重复事件直接返回第一次生成的报价，避免供应商重试造成重复数据。

`agents/interactive_graph.py` 在采购分析图外提供可持久化执行层。每个执行使用独立 `thread_id`，状态由 LangGraph `SqliteSaver` 写入 SQLite；当审批等级或风险要求人工处理时，通过原生 `interrupt()` 暂停。API 收到有权限的审批决定后使用 `Command(resume=...)` 从同一检查点恢复，而不是重新执行整条流程。

普通 Plan-and-Execute 运行同样使用 SQLite checkpoint。调用方可传入稳定 `execution_id`；工具重试耗尽后，执行计划和失败原因仍保留。运维人员排除外部依赖故障后，可从唯一失败步骤恢复，已完成工具不会重复执行。对外状态视图不会返回完整工具观察和长期记忆，避免把内部上下文暴露为诊断接口。

`infrastructure/memory.py` 保存分析结论和人工审批决定，并提供精确申请、品类和部门三级相关性召回、内容去重、遗忘与保留上限。所有成功的普通运行和故障恢复运行都会自动沉淀决策摘要；记忆写入失败只记录 Trace，不会反向破坏已完成的采购分析。`agents/context/` 把短期工具观察、长期记忆和计划修订压缩成有界且脱敏的 Replanner 上下文，历史记忆只能辅助判断，不能覆盖本次工具事实。

制度知识检索位于 `infrastructure/rag/`。检索器同时计算 BM25 词项相关度和本地稠密向量余弦相似度，并返回原始文档、章节、内容与分数；因此 Agent 的制度判断保留可审计引用。默认嵌入完全本地运行，不要求外部 API。

`evals/cases.json` 保存版本化 Agent 与 RAG 基准案例，`evaluation/runner.py` 检查审批等级、推荐数量、路由、证据引用、制度来源和章节命中率。评测失败会返回非零退出码，可直接接入 CI。

## 后续演进

- 将制度文档切分、向量化并建立带出处的 RAG 检索。
- 使用 LangGraph 增加需求澄清、询价、比价、审批和异常处理节点。
- 接入 PostgreSQL、ERP/SAP、OA 和消息系统。
- 增加统一身份认证、细粒度工具调用权限和生产数据库迁移。

