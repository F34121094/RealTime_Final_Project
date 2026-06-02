import json
import random
import os

def generate_unexpected_tasks(output_path="input/aperiodic_n_sporadic.json"):
    # 確保資料夾存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 依照規則決定任務數量
    num_sporadic = random.randint(4, 7)
    num_aperiodic = random.randint(7, 13)

    sporadic_list = []
    for _ in range(num_sporadic):
        e = random.randint(1, 3)             # 執行時間 1~3 小時
        w = random.randint(5, 20)            # 用電需求 5~20 MWh
        
        # Deadline 通常 >= 執行時間 (這裡設定為 e 到 e+2 之間)
        d = random.randint(e, e + 2)         
        
        # 確保任務在 72 小時前能合法結束 (r + d - 1 <= 72)
        max_r = 72 - d + 1
        r = random.randint(1, max_r)
        
        preempt = random.choice([0, 1])      # 隨機決定是否可中斷
        
        sporadic_list.append({"r": r, "e": e, "d": d, "w": w, "preempt": preempt})

    aperiodic_list = []
    for _ in range(num_aperiodic):
        e = random.randint(1, 4)             # 執行時間 1~4 小時
        w = random.randint(5, 15)            # 用電需求 5~15 MWh
        
        d = random.randint(e, e + 2)         
        max_r = 72 - d + 1
        r = random.randint(1, max_r)
        
        preempt = random.choice([0, 1])
        
        aperiodic_list.append({"r": r, "e": e, "d": d, "w": w, "preempt": preempt})

    # 根據 Arrival time (r) 進行排序，讓輸出到 JSON 時按照時間先後排列
    sporadic_list.sort(key=lambda x: x["r"])
    aperiodic_list.sort(key=lambda x: x["r"])

    # 組裝成最終要求的 JSON 格式
    final_data = {
        "aperiodic": {f"a{i+1}": task for i, task in enumerate(aperiodic_list)},
        "sporadic": {f"s{i+1}": task for i, task in enumerate(sporadic_list)}
    }

    # 寫入檔案
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    generate_unexpected_tasks()
