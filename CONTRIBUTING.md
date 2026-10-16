# Contributing

感谢参与 Enterprise Procurement Intelligence Agent。提交改动前，请确保变更可审计、可测试，并且不包含真实企业数据或凭证。

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

cd frontend
npm ci
```

复制 `.env.example` 为 `.env` 后按需配置。默认本地模式不需要外部大模型或企业系统凭证。

## 提交要求

1. 业务规则应放入领域规则或应用层，不应仅依赖 Prompt。
2. 新增工具必须提供明确的输入/输出契约、权限边界和 Trace 记录。
3. 涉及审批、定标、订单或外部同步的变更必须补充测试。
4. 不要提交 `.env`、数据库、构建产物、虚拟环境或 `node_modules`。
5. 提交前运行完整验证：

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m procurement_agent.evaluation.runner
cd frontend
npm run typecheck
npm run build
```

## Commit 与 Pull Request

建议使用简洁的动词开头提交信息，例如 `feat: add supplier risk review`。Pull Request 应说明业务背景、实现范围、验证结果以及潜在的数据迁移或权限影响。
