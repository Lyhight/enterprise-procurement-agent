# GitHub 发布检查清单

## 已完成

- [x] 后端、前端、测试、评估和文档按目录分类
- [x] `.env.example` 不含真实凭证
- [x] 虚拟环境、数据库、缓存、前端依赖和构建产物已加入 `.gitignore`
- [x] GitHub Actions 执行后端测试、Agent/RAG 评估和前端生产构建
- [x] GitHub Workflow 与 Issue Form YAML 语法检查通过
- [x] README 包含架构、快速开始、接口和验证命令
- [x] LICENSE、CONTRIBUTING、SECURITY 和 CHANGELOG 已提供
- [x] Python wheel 构建及包内 Prompt 资源检查通过
- [x] TypeScript 类型检查及生产构建通过
- [x] 后端测试 76 项通过，Agent/RAG 评估 6/6 通过
- [x] 真实 Uvicorn 进程验证 `/health/ready`、`/docs`、`/app/` 和 Agent 能力接口
- [x] 提供 Windows 一键发布验证脚本

## 发布仓库前

- [ ] 确认仓库名称、简介和维护者联系方式
- [ ] 根据发布者身份确认 LICENSE 中的版权主体
- [ ] 添加不含敏感数据的控制台截图
- [ ] 执行首次 Commit 并推送到 GitHub
- [ ] 确认 GitHub Actions 在远程环境运行成功

## 发布容器前

- [ ] 在装有 Docker 的环境运行 `docker compose build`
- [ ] 使用生产密钥管理系统配置认证和外部系统凭证
- [ ] 验证持久卷备份、恢复和升级流程
- [ ] 完成真实 OA/ERP/SSO 的联调与安全评审
