# V4 TRAINING_DATA_EXPANSION_REQUIRED

当前没有任何已接受的 eligible historical archive record，4 个 engine role 均不能进入 formal fitting。现行 class support 门槛保持不变：train=5、validation=3、holdout=3。

## 量化下限

| Engine | Classes | Train | Validation | Holdout | 最低新增 matches 下限 |
|---|---:|---:|---:|---:|---:|
| OUTCOME | 3 | 15 | 9 | 9 | 33 |
| HANDICAP | 3 | 15 | 9 | 9 | 33 |
| GOALS | 8 | 40 | 24 | 24 | 88 |
| HTFT | 9 | 45 | 27 | 27 | 99 |

联合采集的最低下限是 99 个 distinct matches：TRAIN 45、VALIDATION 27、HOLDOUT 27；这是共享同一批 match 为各 engine 提供各自标签的理想下限，实际数量可能因 league、feature、cutoff 和来源质量门槛增加。

当前可推进 engine：无。当前所有 engine：`TRAINING_DATA_EXPANSION_REQUIRED`。

机器可读请求见 `V4_TRAINING_DATA_EXPANSION_REQUIRED.json`，包含日期桶规则、每类配额、必需字段和禁止输入。
