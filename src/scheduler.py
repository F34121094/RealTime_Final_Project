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
    w: int          # energy demand
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
            initial_energy= info["initial_energy"]
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
        