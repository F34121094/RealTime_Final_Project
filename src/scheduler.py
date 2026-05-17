# 排程主程式入口
"""

"""
import json
from dataclasses import dataclass
from typing import List, Dict
import os

@dataclass
class Task:         #任務清單
    task_id: str    # id
    r: int          # Release Time
    p: int          # Period
    e: int          # Execution Time
    d: int          # Deadline
    d_count: int    # 新增特質 - deadline 倒數用於把任務從代辦清單中刪除 
    e_last: int     # 新增特質 - 剩下還需要的執行時間
    w: int          # energy demand (每個小時)
    preempt: int    # preemptable

@dataclass
class Generator:            # 傳統機組
    generator_id: str       # 編號
    output_min: int         # 最小出力
    output_max: int         # 最大出力
    ramp_up_rate: int       # 一個時間間隔 出力可增加的幅度
    ramp_down_rate: int     # 一個時間間隔 出力可減少的幅度
    min_up_time: int        # 最短開機時間
    min_down_time: int      # 最短關機時間
    cost_fixed: int         # 每小時的固定成本
    cost_variable: int      # 發出 1 MWh 的 成本
    initial_on_time: int    # 排程前機組已經連續開機的時間 
    initial_off_time: int   # 排程前機組已經連續關機的時間
    initial_energy: int     # 機組在 t = 0 時可供應的電量
    on_off: int             # 新增變數 - 0:關機 1:開機
    current_energy: int     # 新增變數 - 目前出力

@dataclass
class Storage:              # 儲能設備
    storage_id: str         # 編號
    soc_min: int            # 必須保留的最低電能量
    soc_max: int            # 可以儲存的最高電能量
    discharge_max: int      # 最大放電功率
    charge_max: int         # 最大充電功率
    soc_init: int           # 初始存量

@dataclass
class Renewable:            # 再生能源
    renewable_id: str       # 單一再生能源的編號
    capacity: int           # 再生能源的最大出力
    pv_forecast: list       # 太陽能預測出力百分比

def load_task() -> List[Task]:
    task_set = []
    path = "output/task_set.json"
    with open(path,'r') as f:
        data = json.load(f)
    for task_id,info in data.items():
        task_set.append(Task(
            task_id= task_id,    
            r= info["r"],          
            p= info["p"],
            e= info["e"],          
            d= info["d"],
            d_count = info["d"],
            e_last = info["e"],
            w= info["w"],          
            preempt= info["preempt"]    
        ))
    return task_set

def load_environment() -> List[Task]:
    path_1 = "input/processor_settings.json"
    with open(path_1,'r') as f:
        data = json.load(f)
    # 傳統機組
    generator_set = []
    for info in data["generator"]:
        generator_set.append(Generator(
            generator_id= info["generator_id"],       
            output_min= info["output_min"],         
            output_max= info["output_max"],         
            ramp_up_rate= info["ramp_up_rate"],       
            ramp_down_rate= info["ramp_down_rate"],     
            min_up_time= info["min_up_time"],        
            min_down_time= info["min_down_time"],      
            cost_fixed= info["cost_fixed"],         
            cost_variable= info["cost_variable"],      
            initial_on_time= info["initial_on_time"],    
            initial_off_time= info["initial_off_time"],   
            initial_energy= info["initial_energy"],
            on_off = 0
        ))
    print("[generator loading] success")
    
    # 儲能設備
    storage_set = []
    for info in data["storage"]:
        storage_set.append(Storage(
                storage_id =  info["storage_id"],         
                soc_min =  info["soc_min"], 
                soc_max =  info["soc_max"], 
                discharge_max =  info["discharge_max"], 
                charge_max =  info["charge_max"], 
                soc_init =  info["soc_init"]
        ))
    print("[storage loading] success")

    # 再生能源
    renewable_set = []
    for info in data["renewable_capacity"]:
        id = info["renewable_id"]
        c = info["capacity"]

        forecast = []
        for forecast_group in data["renewable_forecast"]:
            if id in forecast_group:
                forecast = [hour["pv_forecast"] for hour in forecast_group[id]]
        
        renewable_set.append(Renewable(
            renewable_id = id,
            capacity= c,
            pv_forecast= forecast
        ))
    print("[renewable loading] success")
    
    # 72 小時的價格
    path_2 = "input/price_72hr.json"
    with open(path_2,'r') as f:
        data = json.load(f)
    data_price = data["price"]
    price_72 = [entry["market_price"] for entry in data_price]
    print("[price 72 loading] success")
    
    return generator_set,storage_set,renewable_set,price_72

def environment_check(generator_set,storage_set,renewable_set,price_72):
    print("\n--- generator_set ---")
    for i in generator_set:
        print(f"id : {i.generator_id}")
        print(f"ramp_up_rate: {i.ramp_up_rate}")
        print(f"initial_on_time : {i.initial_on_time}\n")

    print("\n--- storage_set ---")
    for i in storage_set:
        print(f"id : {i.storage_id}")
        print(f"soc_min: {i.soc_min}")
        print(f"charge_max : {i.charge_max}\n")
    
    print("\n--- renewable_set ---")
    for i in renewable_set:
        print(f"id : {i.renewable_id}")
        print(f"capacity: {i.capacity}")
        print(f"pv_forecast (first 20):")
        for p in range(20):
            print(f"hour{p+1} : {i.pv_forecast[p]}")
        print()

    print("\n--- price_72(first 10) ---")
    for i in range(10):
        print(f"hour{i+1} = {price_72[i]}")
    print()

def task_timelines(task_set):
    timeline = []
    task_can_be_exe = []
    for t in range(72):
        for task in task_set:
            # 把任務加進來 - 只有release time可以加進來
            # 把任務刪除 - 當d_count < e 的時候(代表做不完了)
            # release time 只可能會 >= 目前的時間
            
            # 加入
            if task.r == t:
                task_can_be_exe.append(task.task_id)      #加入之後更新下一次的release time
                task.r += task.p
                continue
            
            #刪除
            if task.task_id in task_can_be_exe:
                if task.d_count <= task.e or (71 - t) < task.e:
                    task_can_be_exe.remove(task.task_id)
                    task.d_count = task.d     #刪除後還原 d_count
                else:    
                    task.d_count -= 1
        timeline.append(list(task_can_be_exe))
    return timeline

def renewable_generate(renewable_set):
    hourly_renewable = [0.0] * 72
    cumulative_renewable = [0.0] * 72
    running_total = 0.0

    for re in renewable_set:
        for t in range(72):
            hourly_power = float(re.capacity) * float(re.pv_forecast[t])
            hourly_renewable[t] += hourly_power
        
    return hourly_renewable

def generator_switch(g):
    if(g.on_off == 0):          # 關機 -> 開機
        if(g.min_down_time <= g.initial_off_time):
            g.on_off = 1
            g.initial_off_time = 0
            return
        else:
            print("開機條件不合")
            return 
    else:                       # 開機 -> 關機
        if(g.min_up_time <= g.initial_on_time):
            g.on_off = 0
            g.initial_on_time = 0
            return
        else:
            print("關機條件不合")
            return 

def main_loop(task_set,generator_set,storage_set,renewable_set,price_72):
    result = []
    for t in range(72):
        round_e_g = 0       # 這個不要加 battery 的因為這邊是可以直接用的
        
        # ===================== 產出部分 =====================
        # 再生能源
        print(f"----- hour {t + 1} -----")
        print(f"renewable : {renewable_set[t]}")
        round_e_g += renewable_set[t]
        
        # 傳統機組
        for g in generator_set:
            if g.on_off == 0:   # 第一版直接開機開機
                generator_switch(g)
            else:               # 開機的這個回合還不能產出任何電力
                if g.current_energy < g.output_max:             # 假設起始的電力是從 0 開始
                    g.current_energy += g.ramp_up_rate          # 一次增加就是增加一個 ramp_up
                    if(g.current_energy > g.output_max): g.current_energy = g.output_max    # 絕對不能超過 最大出力
            print(f"generator_{g.generator_id} : {g.current_energy}")
            round_e_g += g.current_energy       # 反正沒開機這個也是 0 
        
        # 電池電量
        for s in storage_set:
            print(f"battery_{s.storage_id} : {s.soc_init}(目前的電量)")
        
        # ===================== 輸出部分 =====================
        for job in task_set[t]:
            


if __name__ == "__main__":
    try:
        task_set = load_task()
        print("[task loading] success")
    except Exception as e:
        print(f"[task loading] fail:{e}")
    try:
        generator_set,storage_set,renewable_set,price_72 = load_environment()
        # environment_check(generator_set,storage_set,renewable_set,price_72)
        print("[environment loading] success")
    except Exception as e:
        print(f"[environment loading] fail:{e}")

    task_timeline = task_timelines(task_set)
    hourly_renewable = renewable_generate(renewable_set)
    main_loop(task_set,generator_set,storage_set,renewable_set,price_72, renewable_set)

# version 1
# 完全不管成本，有多少就生產多少，然後盡可能做越多任務越好