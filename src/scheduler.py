# 排程主程式入口
"""

"""
import json
from dataclasses import dataclass
from typing import List, Dict
import os
import pulp

@dataclass
class Task:         # [class] 任務清單
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
class Generator:            # [class] 傳統機組
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
class Storage:              # [class] 儲能設備
    storage_id: str         # 編號
    soc_min: int            # 必須保留的最低電能量
    soc_max: int            # 可以儲存的最高電能量
    discharge_max: int      # 最大放電功率
    charge_max: int         # 最大充電功率
    soc_init: int           # 初始存量
    used: int               # 新增變數 - 放過電 1 / 沒放過 0

@dataclass
class Renewable:            # [class] 再生能源
    renewable_id: str       # 單一再生能源的編號
    capacity: int           # 再生能源的最大出力
    pv_forecast: list       # 太陽能預測出力百分比

def load_task() -> List[Task]:      # [FUNC] 將 task_set.json 檔載入
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

def load_environment() -> List[Task]:       # [FUNC] 將 input 中的 json 檔載入
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
            current_energy = 0,
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
                soc_init =  info["soc_init"],
                used = 0
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

def environment_check(generator_set,storage_set,renewable_set,price_72):        # [FUNC] 用來檢查 Json 檔是否載入正確 (不會用到)
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

def task_timelines(task_set):       # [FUNC] 先把 Perodic task 展開成 72小時 (可知哪個小時被排成任務最多)
    timeline = []
    task_can_be_exe = []
    for t in range(72):
        for task in task_set:
            # 把任務加進來 - 只有release time可以加進來
            # 把任務刪除 - 當d_count < e 的時候(代表做不完了)
            # release time 只可能會 >= 目前的時間
            # 刪除
            # Notation : 只要 execution time > relative deadline 就做不完
            if task in task_can_be_exe:
                if task.d_count < task.e or (71 - t) < task.e:
                    task_can_be_exe.remove(task)
                    task.d_count = task.d     #刪除後還原 d_count
                else:    
                    task.d_count -= 1
            
            # 加入
            # [FIX] : 將 release time - 1 確保在 index正確的位置完成
            if task.r - 1 == t and (72 - t) >= task.e:             
                task_can_be_exe.append(task)
                      
                task.r += task.p        # 加入之後更新下一次的release time
                task.d_count -= 1       # 這個回合會是他的第一個回合
        timeline.append(list(task_can_be_exe))
    return timeline

def renewable_generate(renewable_set):      # [FUNC] renewable 72小時產量計算 (可以知道哪個時間點可能不用產那麼多電)
    hourly_renewable = [0.0] * 72

    for re in renewable_set:
        for t in range(72):
            hourly_power = float(re.capacity) * float(re.pv_forecast[t])
            hourly_renewable[t] += hourly_power
        
    return hourly_renewable

def generator_switch(g):        # [FUNC] generator 的開機與關機
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

def battery_dis_charge(system_energy,demand,storage_set,price):     # [FUNC] 總供電、輸電 + 電池輸入輸出 + 賣給台電計算
    # Notation :  用目前電池水位的邏輯來分配
    money = 0
    if system_energy >= demand:
        surplus = system_energy - demand
        storage_set.sort(key = lambda b : b.soc_init / b.soc_max)
        for b in storage_set:
            if surplus <= 0:
                break 
            available_space = b.soc_max - b.soc_init
            actual_charge = min(surplus, b.charge_max, available_space)
            if actual_charge > 0:
                b.soc_init += actual_charge
                surplus -= actual_charge
        if surplus > 0:
            money += surplus * price
        
    else:
        deficit = demand - system_energy
        storage_set.sort(key = lambda b : b.soc_init / b.soc_max, reverse = True)
        for b in storage_set:
            if deficit <= 0:
                break
            available_power = b.soc_init - b.soc_min
            actual_discharge = min(deficit, b.discharge_max, available_power)
            if actual_discharge > 0:
                b.soc_init -= actual_discharge
                deficit -= actual_discharge
        if deficit > 0:
            print(f"這回合失敗，仍需要 ${deficit}")
    for s in storage_set:
        print(f"電池_{s.storage_id} 電量 : {s.soc_init} / {s.soc_max}")
    return money

def main_loop(task_timeline,generator_set,storage_set,renewable_set,price_72):      # [FUNC] 排程的主要迴圈
    # NOTATION : 這個版本是直接把傳統機組的發電直接完全開滿的情況，任務也是不管能不能做就直接全部做完(但基本上都可以做完)
    # 然後如果電力過剩先存入電池中，電池滿了賣給台電
    # 如果遇到電力不夠的情況的選擇: 
    # 1.目前任務擱置 
    # 2.代辦清單任務擱置
    # 3.由電池放電
    total_earn = 0
    total_cost = 0
    current_job = []

    # json 檔的list
    scheduler_result = {
        "schedule_result": []
    }

    for t in range(72):

        time_step_data = {
            "t": t + 1,
            "P": {},  # 每個發電設備的發電
            "k": {},  # 各個耗電任務從哪取得發電
            "sell": 0.0,    # 售電量 
            "soc": {},      # 儲能設備剩餘電量
            "missed_aperiodic": [],     # 逾期的 aperiodic
            "rejected_sporadic": []     # 拒絕的 sporadic
        }

        system_energy = 0       # 不包括電池供電
        cost = 0
        # ===================== 發電 =====================
        
        # [發電] 再生能源
        print(f"----- hour {t} -----")
        print(f"renewable 發電 : {renewable_set[t]}")
        system_energy += renewable_set[t]
        
        # [發電] 傳統機組
        for g in generator_set:
            # TODO [generator] : 什麼時候開機 與 關機 
            if g.on_off == 0:       # 關機
                generator_switch(g)

            # FIXED : [助教回信] - 發電機在開機當下就可以開始供電
            # output 由 0 開始加，但發電量至少要 >= output_min ( 假設output_min 跟 ramp_up 皆為 15，這樣第一個時間點的供電只能是15 )
            if g.on_off == 1:       # 開機  
                g.current_energy = max(g.output_min,min(g.current_energy + g.ramp_up_rate, g.output_max))       # TODO [generator] : ramp_up ramp_down 的設計(現在是一直加到滿)
                print(f"generator_{g.generator_id} 發電 : {g.current_energy}")
                cost += g.current_energy * g.cost_variable + g.cost_fixed
                system_energy += g.current_energy       
            time_step_data["P"] = {

            }
        print()
        # ===================== 輸電 =====================  
        
        demand = 0
        for job in current_job[:]:
            if(job.e_last == 0):
                job.e_last = job.e
                current_job.remove(job)
                print(f"[task remove]{job.task_id}")
                index = t
                while(1):
                    if(job in task_timeline[index]):
                        task_timeline[index].remove(job)
                        index += 1
                    else: break
            else:
                demand += job.w
                job.e_last -= 1
                print(f"[task info]{job.task_id} 剩餘時間 : {job.e_last} 單位成本{job.w}")

        for job in task_timeline[t]:
            if job not in current_job and job.e_last > 0:
                current_job.append(job)
                print(f"[task add]{job.task_id}, 須執行時間 : {job.e_last}")
                demand += job.w
                job.e_last -= 1
                print(f"[task info]{job.task_id} 剩餘時間 : {job.e_last} 單位成本{job.w}")
        
        print(f"\n總電量需求 : {demand}")
        
        earning = battery_dis_charge(system_energy,demand,storage_set,price_72[t])
        print(f"\n回合成本 : {cost}")
        print(f"回合獲利 : {earning}\n")
        total_earn += earning
        total_cost += cost

        scheduler_result["schedule_result"].append(time_step_data)

    print(f"總成本 {total_cost}")
    print(f"總獲利 {total_earn}")

    with open("output/schedule_result.json", "w", encoding="utf-8") as f:
        json.dump(scheduler_result, f, indent=4, ensure_ascii=False)
    
    return

def build_pulp_model(generator_set, task_set, renewable_set, time_horizon=72):
    
    model = pulp.LpProblem("Scheduling",pulp.LpMinimize)
    time_steps = list(range(1, time_horizon + 1))
    
    # ==========================================
    # 1 發電機變數與限制式
    # ==========================================

    # 發電量變數 P 
    gen_ids = [g.generator_id for g in generator_set]
    P = pulp.LpVariable.dicts("Power",
                             ((i,t) for i in gen_ids for t in time_steps),
                             lowBound = 0,
                             cat = 'Continuous')
    
    # 開關機變數 U
    U = pulp.LpVariable.dicts("Status", 
                              ((i, t) for i in gen_ids for t in time_steps), 
                              cat='Binary')
    
    # 這樣是同時對所有的 generator 在 72 個時間點下限制式
    for t in time_steps:
        for g in generator_set:
            i = g.generator_id
            
            # [constraint 6] 傳統機組出力上下限
            model += P[i,t] >= g.output_min * U[i,t]
            model += P[i,t] <= g.output_max * U[i,t]
            
            # [constraint 7] ramp_up/ramp_down 限制
            if t == 1:
                model += P[i, t] - g.initial_energy <= g.ramp_up_rate, f"RampUpInit_{i}"
                model += g.initial_energy - P[i, t] <= g.ramp_down_rate, f"RampDownInit_{i}"
            else:
                model += P[i, t] - P[i, t-1] <= g.ramp_up_rate, f"RampUp_{i}_{t}"
                model += P[i, t-1] - P[i, t] <= g.ramp_down_rate, f"RampDown_{i}_{t}"
    
    # ==========================================
    # 2. 任務變數與限制式 (你剛剛漏掉的在這裡！)
    # ==========================================
    jobs = []
    for task in task_set:
        current_t = task.r
        instance = 1
        while current_t + task.e - 1 <= time_horizon:
            jobs.append({
                "job_id": f"{task.task_id}_{instance}", 
                "w": task.w,
                "e": task.e,
                "r": current_t,
                "d": task.d,
                "preempt": task.preempt
            })
            current_t += task.p 
            instance += 1
    job_ids = [job["job_id"] for job in jobs]
    x = pulp.LpVariable.dicts("TaskExe", 
                              ((j, t) for j in job_ids for t in time_steps), 
                              cat='Binary')

    for job in jobs:
        j = job["job_id"]
        r = job["r"]
        e = job["e"]
        abs_deadline = r + job["d"] - 1

        # [constraint 3] 執行時間總和必須等於 e
        model += pulp.lpSum(x[j, t] for t in time_steps) == e, f"TotalExe_{j}"
        
        # [constraint 2] 不在區間內的時間，強制 x = 0
        for t in time_steps:
            if t < r or t > abs_deadline:
                model += x[j, t] == 0, f"OutWindow_{j}_{t}"

    # ==========================================
    # 3 再生能源變數 & 限制式
    # ==========================================

    # 再生能源變數 P_res
    res_ids = [r.renewable_id for r in renewable_set]
    P_res = pulp.LpVariable.dicts("Power_Renew",
                             ((i,t) for i in res_ids for t in time_steps),
                             lowBound = 0,
                             cat = 'Continuous')
    
    # 售電變數 Sell
    Sell = pulp.LpVariable.dicts("Sell", time_steps, lowBound=0, cat='Continuous')

    all_sources = gen_ids + res_ids  # 所有可以發電的設備 (傳統 + 再生)
    # job 在 時間點t 從 i發電 拿了多少電
    k = pulp.LpVariable.dicts("k",
                              ((j, i, t) for j in job_ids for i in all_sources for t in time_steps),
                              lowBound=0, cat='Continuous')
    for t in time_steps:
        # [constraint 13] 再生能源上限
        for re in renewable_set:
            i = re.renewable_id
            max_res = re.capacity * re.pv_forecast[t-1]
            model += P_res[i, t] <= max_res, f"RenewMax_{i}_{t}"

        # [constraint 1] 任務的能量滿足
        for job in jobs:
            j = job["job_id"]
            model += pulp.lpSum(k[j, i, t] for i in all_sources) == job["w"] * x[j, t], f"TaskDemand_{j}_{t}"

        # [constraint 20] 發電設備的分配上限
        for i in gen_ids:
            model += pulp.lpSum(k[j, i, t] for j in job_ids) <= P[i, t], f"GenDistLimit_{i}_{t}"
        for i in res_ids:
            model += pulp.lpSum(k[j, i, t] for j in job_ids) <= P_res[i, t], f"ResDistLimit_{i}_{t}"

        # [constraint 23] 系統全局能量平衡 (目前先不加儲能)
        total_generate = pulp.lpSum(P[i, t] for i in gen_ids) + pulp.lpSum(P_res[i, t] for i in res_ids)
        total_consume = pulp.lpSum(k[j, i, t] for j in job_ids for i in all_sources)
        
        model += total_generate == total_consume + Sell[t], f"GlobalBalance_{t}"
    
    return model, P, U, x, k, Sell, P_res, jobs



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

    # task_timeline = task_timelines(task_set)            # [BUG] : hour3 release task 會在 hour4 才出現
    # print(f"task_timeline 長度 = {len(task_timeline)}")
    
    # for i in range(len(task_timeline)):
    #     print(f"index{i} - hour{i+1}:{list(map(lambda job : job.task_id, task_timeline[i]))}")
    
    # hourly_renewable = renewable_generate(renewable_set)
    # main_loop(task_timeline,generator_set,storage_set,hourly_renewable,price_72)

    model, P, U, x, k, Sell, P_res, jobs = build_pulp_model(generator_set, task_set, renewable_set) 

    cost_var_dict = {g.generator_id: g.cost_variable for g in generator_set}
    cost_fixed_dict = {g.generator_id: g.cost_fixed for g in generator_set}

    # 2. 定義目標函數 (總成本 = 發電成本 - 售電收益)
    # [作業目標 2 & 3] 最小化發電成本，最大化售電收益
    gen_ids = [g.generator_id for g in generator_set]
    time_steps = list(range(1, 73))
    
    # 發電成本：變動成本 (P * cost_var) + 固定開機成本 (U * cost_fixed)
    total_gen_cost = pulp.lpSum(
        P[i, t] * cost_var_dict[i] + U[i, t] * cost_fixed_dict[i] 
        for i in gen_ids for t in time_steps
    )
    
    # 售電收益：Sell * 當時的電價 (price_72)
    # 注意：price_72 是 0~71 的 list，所以用 t-1 取值
    total_revenue = pulp.lpSum(Sell[t] * price_72[t-1] for t in time_steps)
    
    # 把目標函數加進 model 中 (沒有 <=, >= 或 ==，這就是目標函數！)
    model += total_gen_cost - total_revenue
    
    # 3. 召喚求解器 (Solver) 開始暴力破解！
    print("求解器運算中，請稍候...")
    # 可以加上 msg=True 來看求解器的思考過程
    model.solve(pulp.PULP_CBC_CMD(msg=True)) 
    
    # 4. 印出求解結果狀態
    status_str = pulp.LpStatus[model.status]
    print(f"\n求解完成!狀態: {status_str}")

    if status_str == "Optimal":
        print(f"預估發電總成本: $ {pulp.value(total_gen_cost):.2f}")
        print(f"預估售電總收益: $ {pulp.value(total_revenue):.2f}")
        print(f"系統淨成本 (目標函數值): $ {pulp.value(model.objective):.2f}")

        # 建立外層結構
        final_output = {
            "schedule_result": []
        }
        res_ids = [r.renewable_id for r in renewable_set]
        all_sources = gen_ids + res_ids
        # 遍歷 72 小時
        for t in time_steps:
            time_step_data = {
                "t": t,
                "P": {},
                "k": {},
                "sell": 0.0,
                "soc": {},                # Level 1 如果還沒做儲能，可以先留空 dict
                "missed_aperiodic": [],   # Aperiodic 是明天的任務，先留空 list
                "rejected_sporadic": []   # Sporadic 是明天的任務，先留空 list
            }
            
            # 1. 填寫 P 矩陣 (發電機與再生能源出力)
            for i in gen_ids:
                # 使用 round() 去除浮點數精度誤差 (如 0.000000001 -> 0.0)
                val = round(pulp.value(P[i, t]), 2)
                time_step_data["P"][i] = val
                
            for i in [r.renewable_id for r in renewable_set]:
                val = round(pulp.value(P_res[i, t]), 2)
                time_step_data["P"][i] = val
            
            # 2. 填寫 k 矩陣 (每個 Job 從每個設備拿了多少電)
            for job in jobs:
                j = job["job_id"]
                # 為了避免 JSON 產生巨大且無用的零矩陣，我們只記錄「大於 0」的供電分配
                task_k_dict = {}
                for i in all_sources:
                    val = round(pulp.value(k[j, i, t]), 2)
                    if val > 0:
                        task_k_dict[i] = val
                
                # 如果這個小時這個任務有拿到電，才加進 k 裡面
                if task_k_dict:
                    time_step_data["k"][j] = task_k_dict
                    
            # 3. 填寫售電量
            time_step_data["sell"] = round(pulp.value(Sell[t]), 2)
            
            # 將這個小時的狀態加入清單
            final_output["schedule_result"].append(time_step_data)
            
        # 4. 匯出檔案
        output_path = "output/schedule_result.json"
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)
            
        print(f"✅ JSON 排程結果已成功儲存至 {output_path}")
    else:
        print("警告：模型無解 (Infeasible)！請檢查限制式是否衝突。")


