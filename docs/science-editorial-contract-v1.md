# Science Editorial Contract V1
## 状态
Draft → Reviewed → ApprovedForHumanReview → Published

只有结构校验、证据引用和元数据一致性全部通过，才能进入 ApprovedForHumanReview；该状态仍不等于科学事实已完成独立复核。

## 证据规则
- 每条 factual claim 必须引用 Evidence package 中同一 DOI 的 evidenceRef。
- 摘要来源只能支持“论文摘要报告/论文作者称”等有限表述。
- full_text 只有在 Evidence 明确记录为全文且定位可追踪时才能使用。
- preprint 不得描述为同行评审论文。
- 量化结果必须包含单位（如适用）和可追踪证据。
- 缺失、冲突或无法解析的证据一律 fail-closed。
- 关键词和期刊声誉只用于排序，不证明科学重要性。

## 选择评分
确定性预排序仅用于安排编辑顺序：
- scientificSignificanceHint：0–2（研究问题/潜在意义线索）
- noveltyHint：0–2（方法或结果新颖性线索）
- publicRelevanceHint：0–2（可能的公共关联线索）
- evidenceStrength：0–3（Crossref、摘要、全文入口）
- recency：0–1
- diversityBonus：0–1
总分不代表论文质量或重要性；最终选择必须由编辑结合原始论文判断。
