# Phase 3.3 发布完整性审计

## BESIII 结果

`science-besiii-2026-11-07-rc1` 是 `blocked` Release Candidate，不是授权发布物。

- Draft：`Draft`
- Semantic review：`pending_review`
- Claims：3 条均为 `unreviewed`
- Evidence：3 条均为 L1 摘要级
- APS 全文：未访问，历史记录为代理 403
- `publication_eligible`：`false`
- `release_authorized`：`false`

## 实现边界

发布资格检查器同时检查结构化 Evidence、语义审核、全部 Article 状态、重复 DOI 和 Draft fingerprint。它从不信任 JSON 中的 `approved`、`reviewerId` 或 `authorized` 为可信人类授权。真正的发布授权仍需 GitHub 受保护 Environment、Required Reviewers 或等效的外部可信机制，并绑定 Candidate fingerprint 与 source commit。

`publish_science.py` 仅支持 `--dry-run`；输出计划始终声明不写入 Edition、不更新 Manifest、不创建发布提交。正式原子发布与发布后校验只定义了安全前置条件，尚未启用。
