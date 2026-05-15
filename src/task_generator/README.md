# Periodic Task Generator

本模組負責生成符合虛擬電廠 (VPP) 排程系統數學限制的週期性任務集合 (Periodic Task Set)。

## 規格對應 (Specification Mapping)
本模組的演算法邊界與輸出格式，嚴格遵循作業說明書之規範，開發時可對照以下頁數：
* **開發規格與數學限制**：參考第 10 頁（包含任務數量、Frame size、工作負載密度 $D_w$ 等嚴格限制）。
* **API 輸出格式**：參考第 21 頁（附錄 F 範例，確保 JSON Key 值完全一致）。
* **名詞與符號定義**：參考第 4 ~ 5 頁（$r_j$, $e_j$, $period_j$ 等模型參數定義）。

## 1. 核心邏輯 (Generation Strategy)
> 說明你採用的生成策略（例如：反向構造法先定 Frame Size，或是暴力生成加拒絕抽樣法）。
* 確保工作負載密度 $D_w \ge 0.7$
* 確保至少有 30 個展開後的 jobs
* 確保 Frame size 滿足所有排程邊界條件

## 2. 執行方式 (How to Run)
在專案根目錄下執行：
```bash
python src/task_generator/main.py