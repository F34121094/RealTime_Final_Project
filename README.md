# Real-Time Scheduling System

## 1. 專案架構與檔案說明
> 說明：本專案採用高度解耦架構，將參數輸入、資料模型、演算法核心與結果輸出徹底分離，以確保模組間的獨立性與結果的決定性。

```text
VPP_RealTime_Scheduler/
├── input/                          # 外部環境參數 (唯讀，不可更動)
│   ├── processor_settings.json     # 機組與儲能參數
│   ├── price_72hr.json             # 72小時電價表
|   └── aperiodic_n_sporadic.json   # 非週期 task set
│
├── output/                         # 各模組產出的結果 (API 合約交集區)
│   ├── task_set.json               # task_generator 產出的測資
│   ├── schedule_result.json        # scheduler 排程結果產出
│   ├── evaluation_results.json     # evaluator 算分與效能產出
│   └── acceptance_test_log.json    # (Level 2) 動態任務接收測試日誌
│
├── src/                            # 核心程式碼模組
│   ├── task_generator.py           # 週期性任務生成器
│   ├── scheduler.py                # Level 1 排程器
│   ├── evaluator.py                # 效能評估器
│   ├── advanced_scheduler.py       # Level 2 排程器
|   └── advanced_evaluator.py       # Level 2 效能評估器
│
├── README.md                       # 專案說明與執行指南 (本檔案)
└── report.pdf                      # 報告文件
```
## 2. 使用語言、版本與套件需求
本系統開發與測試皆在以下環境中完成，請確保執行環境符合要求：

* **程式語言**：Python 3.10+
* **核心最佳化套件**：`PuLP` (v2.8+) — 用於建構線性規劃模型與調用底層求解器。
* **底層求解器**：`CBC` (Coin-or branch and cut) — PuLP 內建之預設 MILP 求解器。
* **內建標準庫**：`json`, `os`, `time`, `csv`, `subprocess`, `dataclasses`, `datetime`, `statistics`
---

## 3. 程式編譯方式或環境設定
### 1. 無緩衝標準輸出設定
在執行所有系統腳本時，**強烈建議加上 `-u` 參數**（例如 `python -u src/advanced_scheduler.py`）。
* **物理意義**：此設定能強制關閉 Python 預設的標準輸出緩衝機制 (Buffering)，確保 Acceptance Test 的每小時調度日誌（如 `ACCEPTED`、`REJECTED`）能夠在觸發當下**立刻即時 Flush** 至終端機中。
* **必要性**：這能避免 Log 因記憶體緩衝產生延遲，確保自動批改系統能即時捕捉系統狀態，防止因 Buffering 延遲而被判定為超時 (Timeout)。

### 2. 必要依賴套件安裝
本系統的核心最佳化模型建構於 `PuLP` 套件之上，並自動調用其內建的 CBC 求解器。請於執行前透過 `pip` 完成安裝：
```bash
  pip install pulp
```

### ˇ. 環境變數路徑設定
為了確保從專案根目錄呼叫子資料夾內之腳本時，各模組（如 `checker` 或 `src` 底下的輔助函式）的參照路徑完全對齊，建議在執行前配置環境變數：
```bash
  export PYTHONPATH=$PYTHONPATH:$(pwd)/src
```

## 4. 程式執行流程
專案程式碼皆存放在 src/ 資料夾中，整體系統的標準執行流水線（Pipeline）如下：
```text
[步驟 1] 產生任務測試集 (task_generator.py)
   │
   ▼ 產出 output/task_set.json
[步驟 2] 執行排程器核心 (scheduler.py 或 advanced_scheduler.py)
   │      ├─ 階段一：日前排程 (Base Schedule)，鎖定 Periodic 任務
   │      └─ 階段二：時間推進，即時進行動態突發任務之 Acceptance Test
   │
   ▼ 產出 output/schedule_result.json & acceptance_test_log.json
[步驟 3] 執行進階評估器 (evaluator.py 或 advanced_evaluator.py)
   │      └─ 讀取排程結果，計算結果
   │
   ▼ 產出 output/evaluation_results.json (排程成績單)
```

## 5. 各程式輸入與輸出檔案說明
### 【輸入檔案】 (位於 input/ 資料夾)
1. **` processor_settings.json `**：發電機等等的基礎排程參數。
2. **` price_72hr.json `**：完整 72 小時的日前市場預測電價表。
3. **` aperiodic_n_sporadic.json `**：動態隨機抵達的突發非週期任務清單（Aperiodic 與 Sporadic 的 $r, e, d, w, preempt$ 參數）。

### 【輸出檔案】 (位於 output/ 資料夾)
1. **` task_set.json `**：生成的 72 小時 Periodic task set。
2. **` schedule_result.json `**：紀錄 1~72 小時中，每小時機組出力 $P$、任務電力分配 $k$、市場實際售電量 $sell$、電池電量 $SOC$，以及當前小時發生的 Missed/Rejected 任務日誌。
3. **` evaluation_results.json `**：由評估器算出的系統績效指標。
4. **` acceptance_test_log.json `**：詳細紀錄每個 Sporadic 任務觸發 Acceptance Test 時的判定結果（Accepted/Rejected）、將此任務排程在哪幾個時間點執行、與具體的物理資源衝突原因等。

## 6. 如何重現繳交的 output JSON
若要完全重現本專案最終提交於 `output/` 資料夾下的各項 JSON 成果，請依據以下標準流水線（Pipeline）順序，於專案根目錄下依序執行對應的指令：

### 1. 重現 `task_set.json`
* **執行腳本**：`task_generator.py`
* **執行指令**：
  ```bash
  python -u src/task_generator.py
  ```
### 2. 重現 `schedule_result.json` & `acceptance_test_log.json`
依據評分需求，本系統提供兩種排程模式：
* **Level 1 (靜態基準排程模式)：**：
  ```bash
  python -u src/scheduler.py
  ```
* **Level 2 (進階動態自適應排程模式)：**：
  ```bash
  python -u src/advanced_scheduler.py
  ```
### 3. 重現 `evaluation_results.json`
* Level 1
    * **執行腳本**：`evaluator.py`
    * **執行指令**：
        ```bash
        python -u src/evaluator.py
        ```
* Level 2
    * **執行腳本**：`advanced_evaluator.py`
    * **執行指令**：
        ```bash
        python -u src/advanced_evaluator.py
        ```

## 7. 補充說明
* ### Level 2 輸出 json 新增額外欄位
    **` schedule_result.json ` :** 
    1. **contract_sell** : 對應到放寬的 Assumptions 4 售電契約，紀錄完成periodic tasks 時每個小時規劃的售電量
    2. **price** : 對應到放寬的 Assumptions 4 售電契約，紀錄 72 小時真實買出的電量。
    3. **is_peak_hour** : 對應到放寬的 Assumptions 9 熱門時段售電獎勵，記錄熱門時段有 1.25 倍的電價加成。