# V4 Additional Library Backfill Request

状态：`COMPLETE`（请求规格已完成；真实数据包尚未提供，因此没有进入 archive，也没有开始训练）。

本请求用于从 ChatGPT Library 获取更多可审计的历史官方竞彩来源，随后按 V4 规则独立重新摄取。它不是 archive 批准，也不是训练授权。

## 数量门槛

- 至少 `99` 场 distinct matches。
- 按时间分成 `TRAIN 45`、`VALIDATION 27`、`HOLDOUT 27`，按 match group 做严格时间切分。
- 最低新增 eligible samples：`OUTCOME 33`、`HANDICAP 33`、`GOALS 88`、`HTFT 99`。
- class support、feature availability、leakage、lineage 和来源质量门槛保持不变。

## 优先扫描范围

优先扫描 2026-08-05、2026-08-13、2026-08-21、2026-08-23；随后扫描 8 月下旬和 2026-09-05 至 2026-09-06。早期报告中提到的 Library 文件 id 在真实导出前一律记为 `UNKNOWN_UNTIL_LIBRARY_EXPORT`，不会伪造。

收集优先级是完整 HTFT 覆盖、完整总进球覆盖、可独立验证的 RQSPF 截止时刻/让球线，以及可追溯的 SPF。实际 class 缺口必须在重新摄取后依据真实标签统计，不能用 V4 预测或概率挑样本。

## 每场必须保留

原始官方截图或 source bytes、Library file id/external ref、原始文件 hash、canonical match identity、league、kickoff、prediction cutoff、source availability、各玩法覆盖状态、独立的赛后 final/halftime labels，以及 created/upload/source/capture/publication/observed/ingested 的分别语义。未知时间明确写 `UNKNOWN`，不能把 upload time 冒充 source time。

V3-era raw factual source 或既有结构化 extraction 只能作为候选，必须独立 V4 re-ingestion；V3 predictions/models/parameters、post-match features、猜测赔率和合成比赛均禁止。

## 接入边界

下一批包应使用 `verified-historical-backfill-export-package@1.1.0`，先进入 `approved_data/historical_backfill_staging` 的 append-only 新 revision 目录。验证、去重、identity mapping 通过后，仍需单独 governance/intake 许可才能写入 historical archive。当前状态仍为 `REAL_LIBRARY_EXPORT_OR_AUDITABLE_SOURCE_PACKAGE_REQUIRED`。
