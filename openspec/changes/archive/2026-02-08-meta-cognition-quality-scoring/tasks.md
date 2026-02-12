<!-- Author: msq -->

## 1. 依赖检查

- [x] 1.1 验证上游模块（ACH/叙事/KG/预测）输出已可读取
- [x] 1.2 缺失依赖时返回 pending_inputs，不计算伪分数

## 2. 核心服务

- [x] 2.1 新增 `services/confidence_scorer.py`
- [x] 2.2 新增 `services/bias_detector.py`
- [x] 2.3 新增 `services/blindspot_detector.py`

## 3. API 与报告

- [x] 3.1 新增 `POST /quality/score_judgment`
- [x] 3.2 新增 `GET /quality/judgments/{judgment_uid}`
- [x] 3.3 输出 `QualityReportV1`（json + markdown）

## 4. 测试与门禁

- [x] 4.1 新增 `test_meta_cognition_quality.py`
- [x] 4.2 增加质量评测 fixtures（偏见/盲区样例）
- [x] 4.3 固化质量阈值并接入回归门禁
