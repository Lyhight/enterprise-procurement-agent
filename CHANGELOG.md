# Changelog

本项目遵循语义化版本思想记录重要变更。

## 0.1.0 - 2026-10-16

- 完成 LangGraph Plan-and-Execute/Replan 采购 Agent。
- 加入混合 RAG、版本化采购规则、工具契约和最终决策安全闸门。
- 实现短期上下文、长期记忆、SQLite checkpoint、取消与故障恢复。
- 实现 Trace 哈希链、决策来源重放、审计和运行指标。
- 完成需求澄清、询价报价、审批定标、OA/ERP 集成、订单与收货业务链路。
- 提供 React 管理控制台、FastAPI API、Docker Compose 和 GitHub Actions。
- 支持通过 `PROJECT_ROOT` 在普通 wheel 与容器安装中稳定定位业务资源。
- 建立 76 项自动化测试和 6 项 Agent/RAG 基准评估。
