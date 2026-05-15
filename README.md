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
│   ├── task_set.json               # Generator 產出
│   ├── schedule_result.json        # Scheduler 產出
│   └── evaluation_results.json     # Evaluator 產出
│
├── src/                            # 核心程式碼
│   ├── task_generator/             # 週期性任務生成器
│   │   ├── __init__.py
│   │   └── main.py                 
│   │
│   ├── scheduler/                  # 核心排程器
│   │   ├── __init__.py
│   │   ├── main.py                 # 排程主程式入口
│   │   ├── static_scheduler.py     # 處理日前固定排程 (Periodic Tasks)
│   │   └── dynamic_scheduler.py    # 處理 Acceptance Test (Sporadic/Aperiodic)
│   │
│   ├── evaluator/                  # 效能評估器
│   │   ├── __init__.py
│   │   └── main.py                 # 計算 Miss rate, Tardiness, 成本與收益
│   │
│   ├── models/                     # [領域模型] 資料物件定義區
│   │   ├── __init__.py
│   │   └── data_classes.py         # 封裝 Task, Generator, Battery 等資料結構
│   │
│   └── utils/                      # [共用工具] 
│       ├── __init__.py
│       ├── file_io.py              # 專門處理 JSON 讀寫與驗證
│       └── math_tools.py           # 共用數學計算與轉換模組
│
├── .gitignore                      # 避免快取與虛擬環境推上版控
├── README.md                       # 專案說明與執行指南
├── requirements.txt                # 統一的套件依賴清單
└── run_pipeline.py                 # 全局執行腳本 (一鍵依序執行全系統)