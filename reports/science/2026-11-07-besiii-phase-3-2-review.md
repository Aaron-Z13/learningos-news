# BESIII Phase 3.2 语义审核报告

## 当前结论

稿件 `drafts/science/2026-11-07-besiii-ai-pilot.json` 仍为 `Draft`。语义审核记录为 `pending_review`，3 条 Claim 均为 `unreviewed`；系统没有把字符串相似、同 DOI 或摘要转录自动判定为 `supported`。

## 证据边界

- `besiii-e1`、`besiii-e2`、`besiii-e3`：均为 L1（同 DOI 的 OpenAlex 转录摘要），不是 L2/L3。
- Crossref：只用于 DOI、标题、期刊、作者和年份元数据。
- APS HTML/PDF：当前 Cloud 网络代理返回 403，未完成全文访问；没有声明 Full-text Verified。
- 定量 Claim 的数值、单位、统计/系统误差、比较对象和实验条件尚未由人工逐条复核。

## 编辑门

自动 Quality Gate 只产生 `draft_valid` 和结构/元数据/证据一致性结果。Phase 3.2 审核器另外验证审核记录是否绑定当前 Draft 指纹、覆盖全部 Claim/Evidence、包含真实 reviewer/timestamp，并计算 `publication_eligible`。当前结果为 `false`：没有人工 Reviewer，Claim 未审核，且稿件仍不是 `ApprovedForHumanReview`。

本次 Cloud 本地结果：`draft_valid=true`、`semantic_review_valid=true`、`publication_eligible=false`。29 项测试通过。

任何 Claim 进入 `unsupported`、`contradicted` 或 `insufficient_evidence`，都不能批准；稿件或证据变更会使旧审核指纹失效。
