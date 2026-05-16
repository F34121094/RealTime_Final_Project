# Real-Time Scheduling System

## 1. 專案架構與檔案說明 (Project Structure)
> 說明：本專案採用高度解耦架構，將參數輸入、資料模型、演算法核心與結果輸出徹底分離，以確保模組間的獨立性與結果的決定性。

```text
VPP_RealTime_Scheduler/
├── input/                          # 外部環境參數 (唯讀，不可更動)
│   ├── processor_settings.json     # 機組與儲能參數
│   └── price_72hr.json             # 72小時電價表
│
├── output/                         # 各模組產出的結果 (API 合約交集區)
│   ├── task_set.json               # task_generator 產出的測資
│   ├── schedule_result.json        # scheduler 排程結果產出
│   ├── evaluation_results.json     # evaluator 算分與效能產出
│   └── acceptance_test_log.json    # (Level 2) 動態任務接收測試日誌
│
├── src/                            # 核心程式碼模組
│   ├── task_generator.py           # 週期性任務生成器
│   ├── scheduler.py                # 核心排程演算法 (處理日前靜態排程與資源分配)
│   ├── evaluator.py                # 效能評估器 (計算 Miss rate, 成本與收益)
│   └── models.py                   # [領域模型] 封裝發電機、電池、電價等環境資料結構
│
├── .gitignore                      # 避免快取與編譯環境被推上版控
├── README.md                       # 專案說明與執行指南 (本檔案)
└── requirements.txt                # 統一的 Python 套件依賴清單
```

## 2. 開發進度表 (Project Progress) 
* [x] **Phase 0: 專案基礎建設**
    * [x] 確立 Git 版控與協作流程
    * [x] 建立符合自動評分腳本的目錄結構
* [x] **Phase 1: 測資生成 (Task Generator)**
    執行檔案 `src/task_generator.py`, 結果 `output/task_set.json`
    * [x] 實作週期任務基礎參數範圍限制
    * [x] 實作死線 (Deadline) 特殊分佈限制
    * [x] 實作高壓系統負載密度驗證 (Dw >= 0.7)
* [ ] **Phase 2: 環境建構 (Data Models & Parsers)**
    * [ ] 實作發電機組 (Processor/Generator) 資料結構與限制式
    * [ ] 實作儲能設備 (Battery) 資料結構
    * [ ] 實作電價表 (Price Table) 解析邏輯
* [ ] **Phase 3: 核心排程器 (Static Scheduler)**
    * [ ] 實作基礎 Clock-driven 靜態排程框架
    * [ ] 實作電力負載分配演算法 (平行多工處理)
    * [ ] 產出合規的 schedule_result.json
* [ ] **Phase 4: 效能評估器 (Evaluator)**
    * [ ] 實作 Miss Rate 與 Tardiness 計算
    * [ ] 實作發電成本與收益計算模型
* [ ] **Phase 5: 動態排程進階挑戰 (Dynamic Scheduler) - Optional**
    * [ ] 實作 Aperiodic/Sporadic 任務之 Acceptance Test



