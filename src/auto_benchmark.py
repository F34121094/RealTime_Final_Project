import subprocess
import csv
import re
import time
import json
import os
from datetime import datetime

# ==========================================
# 1. 配置區 (請確認這些檔名與你的檔案一致)
# ==========================================
FILE_GENERATE = "task_generate.py"  # 產生任務的腳本
FILE_LEVEL1 = "scheduler_v1_1.py"        # Level 1 腳本
FILE_LEVEL2 = "scheduler_v2_0.py"             # Level 2 腳本
FILE_EVALUATE = "evaluator.py"
FILE_READ = "evaluation_results.json"
OUTPUT_CSV = "benchmark_results.csv" # 輸出的報表名稱

TOTAL_RUNS = 500  # 你想要執行的總次數 (睡覺前可以設 500 或 1000)

def remove_stale_file(filepath):
    """防止讀到上一輪的舊成績，執行前先刪除舊檔案"""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

def read_evaluation():
    if not os.path.exists(FILE_READ):
        return None
    try:
        with open(FILE_READ, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return None
    
# ==========================================
# 3. 主循環
# ==========================================
def main():
    
    # 紀錄是否已經寫入過 CSV 的標題 (Header)
    header_written = False
    fieldnames = []

    # 使用 utf-8-sig 確保 Excel 打開不會亂碼
    with open(OUTPUT_CSV, mode='a', newline='', encoding='utf-8-sig') as csvfile:
        writer = None

        for i in range(1, TOTAL_RUNS + 1):
            print(f"\n[Iteration {i} / {TOTAL_RUNS}] {datetime.now().strftime('%H:%M:%S')}")
            
            # 這回合要寫入 CSV 的一整列資料
            row_data = {
                'Iteration': i, 
            }

            # --------------------------------------------------
            # 步驟 A：產生新任務
            # --------------------------------------------------
            subprocess.run(["python", FILE_GENERATE], capture_output=True)

            # --------------------------------------------------
            # 步驟 B：執行 Level 1 並評估
            # --------------------------------------------------
            print("  -> Level 1")
            remove_stale_file(FILE_READ) # 清除舊成績
            subprocess.run(["python", FILE_LEVEL1], capture_output=True)   # 跑 L1
            subprocess.run(["python", FILE_EVALUATE], capture_output=True) # 評估 L1
            
            l1_data = read_evaluation()
            if l1_data:
                # 動態將 JSON 裡面的所有 key 加上 L1_ 前綴存起來
                for k, v in l1_data.items():
                    row_data[f"L1_{k}"] = v
            else:
                row_data["L1_Status"] = "Failed"

            # --------------------------------------------------
            # 步驟 C：執行 Level 2 並評估 (使用相同的任務)
            # --------------------------------------------------
            print("  -> Level 2")
            remove_stale_file(FILE_READ) # 清除 L1 的成績
            subprocess.run(["python", FILE_LEVEL2], capture_output=True)   # 跑 L2
            subprocess.run(["python", FILE_EVALUATE], capture_output=True) # 評估 L2
            
            l2_data = read_evaluation()
            if l2_data:
                # 動態將 JSON 裡面的所有 key 加上 L2_ 前綴存起來
                for k, v in l2_data.items():
                    row_data[f"L2_{k}"] = v
            else:
                row_data["L2_Status"] = "Failed"

            # --------------------------------------------------
            # 步驟 D：動態建立 CSV 標題並寫入
            # --------------------------------------------------
            # 如果是第一次成功拿到 L1 和 L2 的完整資料，就利用它們來生成 CSV 欄位名稱
            if not header_written and l1_data and l2_data:
                fieldnames = ['Iteration', 'Timestamp']
                fieldnames += [f"L1_{k}" for k in l1_data.keys()]
                fieldnames += [f"L2_{k}" for k in l2_data.keys()]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # 檢查檔案是否是空的，是的話才寫入標題，避免續傳時重複寫入標題
                if os.path.getsize(OUTPUT_CSV) == 0:
                    writer.writeheader()
                header_written = True

            # 寫入資料 (如果還沒成功建立 Header 就先跳過寫入，直到有成功的一輪)
            if writer:
                # 只保留存在於 fieldnames 裡面的資料，如果遇到 failed，填補 N/A
                safe_row = {k: row_data.get(k, "N/A") for k in fieldnames}
                writer.writerow(safe_row)
                csvfile.flush() # 立刻存檔！就算你睡覺不小心踢到電源線，前面的資料都在
                
                # 簡單印個重點讓你看進度 (如果 json 裡面有 objective_value 的話)
                l1_obj = row_data.get("L1_objective_value", "N/A")
                l2_obj = row_data.get("L2_objective_value", "N/A")
                print(f"  [Complete] L1 obj : {l1_obj} | L2 obj: {l2_obj}")

            # 讓 CPU 喘息一小下，避免 IO 衝突
            time.sleep(0.1)

if __name__ == "__main__":
    main()