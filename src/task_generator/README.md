# Periodic Task Generator

本模組負責生成符合虛擬電廠 (VPP) 排程系統數學限制的週期性任務集合 (Periodic Task Set)。

## 規格對應 (Specification Mapping)
本模組的演算法邊界與輸出格式，嚴格遵循作業說明書之規範，開發時可對照以下頁數：
* **開發規格與數學限制**：參考第 10 頁（包含任務數量、Frame size、工作負載密度 $D_w$ 等嚴格限制）。
* **API 輸出格式**：參考第 21 頁（附錄 F 範例，確保 JSON Key 值完全一致）。
* **名詞與符號定義**：參考第 4 ~ 5 頁（ $r_j$, $e_j$, $period_j$ 等模型參數定義）。

## 1. 核心邏輯 (Generation Strategy)
本生成器目前採用**「Hybrid Constructive & Rejection Sampling」**來產出高壓的 MVP 測資：

* **局部條件強制綁定**：針對作業中「至少需要 N 個」的分佈限制（如 $w_j \ge 14$ 或 Non-preemptive），直接在迴圈前期（強制 $i \le 2$ 時）配發符合規範的數值，保證基礎條件絕對合法。其餘任務則在規範邊界內進行隨機生成。
* **全域條件驗證 (Rejection Sampling)**：單一 Task 生成完畢後，進行整體集合的防呆檢查：
    * 確保展開後的 jobs 總數 $> 30$。
    * 確保工作負載密度 $D_w \ge 0.7$。
    * 若上述任一條件不符，則整組測資作廢並重新生成（因採用強制綁定策略，通常極高機率能一次命中合法解）。
* **當前版本限制 (MVP 狀態)**：為了初期開發與資料流串接順利，目前版本**暫未加入 Frame Size 的聯立數學限制檢查**。優先提供高負載密度的測資，以供 Scheduler 模組進行壓力測試。

## 2. 執行方式 (How to Run)
在專案根目錄下執行：
```bash
python src/task_generator/main.py
