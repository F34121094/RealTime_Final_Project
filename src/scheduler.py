import json
from dataclasses import dataclass
from typing import List, Dict
import pulp
# pulp 是一個專門用來解決線性規劃問題的函式庫

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
class Task_unexpected:         # [class] aperiodic / Sporadic task
    r: int          # Release Time
    e: int          # Execution Time
    d: int          # Deadline
    w: int          # energy demand (每個小時)
    preempt: int    # preemptable
    type: int       # 新增特質 : 1 sporadic(hard)/ 0 aperiodic(soft)


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

def load_task():        # [FUNC] 將 task_set.json 檔載入
    task_set = []
    path = "output/task_set.json"
    with open(path,'r') as f:
        data = json.load(f)
    for task_id,info in data["periodic"].items():
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

def load_un_task():     # [FUNC] 將 aperiodic_n_sporadic.json 檔載入
    task_set = []
    path = "input/aperiodic_n_sporadic.json"
    with open(path,'r') as f:
        data = json.load(f)
    for info in data["aperiodic"].items():
        task_set.append(Task(
            r= info["r"],          
            e= info["e"],          
            d= info["d"],
            w= info["w"],          
            preempt= info["preempt"],
            type = 0
        ))
    for info in data["sporadic"].items():
        task_set.append(Task(
            r= info["r"],          
            e= info["e"],          
            d= info["d"],
            w= info["w"],          
            preempt= info["preempt"],
            type = 1
        ))
    return task_set

def load_environment():       # [FUNC] 將 input 中的 json 檔載入
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

def renewable_generate(renewable_set):      # [FUNC] renewable 72小時產量計算 (可以知道哪個時間點可能不用產那麼多電)
    hourly_renewable = [0.0] * 72

    for re in renewable_set:
        for t in range(72):
            hourly_power = float(re.capacity) * float(re.pv_forecast[t])
            hourly_renewable[t] += hourly_power
        
    return hourly_renewable

def build_pulp_model(generator_set, task_set, renewable_set, time_horizon=72):
    
    model = pulp.LpProblem("Scheduling",pulp.LpMinimize)    # 目標是要最小化
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
    # 2 任務變數與限制式
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
    
    # task 在時間 t 是否有被執行
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
        
        # [constraint 2] 不在可以執行的範圍時，強制 x = 0
        for t in time_steps:
            if t < r or t > abs_deadline:
                model += x[j, t] == 0, f"OutWindow_{j}_{t}"

        # [constraint 5] non-preemptive 需要連續執行
        if job["preempt"] == 0 :
            z_vars = []
            for t in time_steps:
                z = pulp.LpVariable(f"z_diff_{j}_{t}", lowBound=0, cat='Continuous')
                z_vars.append(z)

                x_current = x[j,t]
                x_prev = x[j, t-1] if t > 1 else 0

                model += z >= x_current - x_prev, f"AbsPos_{j}_{t}"
                model += z >= x_prev - x_current, f"AbsNeg_{j}_{t}"
            
            model += pulp.lpSum(z_vars) <= 2, f"ContinuousExe_{j}"


    # ==========================================
    # 3 儲能設備
    # ==========================================
    # 宣告儲能變數
    storage_ids = [s.storage_id for s in storage_set]

    # 充電量 (Continuous, >= 0)
    P_ch = pulp.LpVariable.dicts("Charge", ((s, t) for s in storage_ids for t in time_steps), lowBound=0, cat='Continuous')
    # 放電量 (Continuous, >= 0)
    P_dis = pulp.LpVariable.dicts("Discharge", ((s, t) for s in storage_ids for t in time_steps), lowBound=0, cat='Continuous')
    
    # 蓄電池電量 SOC
    SOC = pulp.LpVariable.dicts("SOC", ((s, t) for s in storage_ids for t in [0] + time_steps), lowBound=0, cat='Continuous')

    # 設定 t=0 的初始電量限制
    for s in storage_set:
        model += SOC[s.storage_id, 0] == s.soc_init, f"SOC_Init_{s.storage_id}"

    # ==========================================
    # 4 再生能源變數 & 限制式
    # ==========================================

    # 再生能源變數 P_res
    res_ids = [r.renewable_id for r in renewable_set]
    P_res = pulp.LpVariable.dicts("Power_Renew",
                             ((i,t) for i in res_ids for t in time_steps),
                             lowBound = 0,
                             cat = 'Continuous')
    
    # 售電變數 Sell
    Sell = pulp.LpVariable.dicts("Sell", time_steps, lowBound=0, cat='Continuous')

    all_sources = gen_ids + res_ids + storage_ids # 所有可以發電的設備 (傳統 + 再生)
    
    # job 在 時間點t 從 i發電 拿了多少電
    k = pulp.LpVariable.dicts("k",
                              ((j, i, t) for j in job_ids for i in all_sources for t in time_steps),
                              lowBound=0, cat='Continuous')
    
    IsCh = pulp.LpVariable.dicts("IsCharging", ((s, t) for s in storage_ids for t in time_steps), cat='Binary')
    
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

        # [新增] 儲能設備自身的物理約束
        for s in storage_set:
            sid = s.storage_id
            
            # 1. 充放電功率不能超過硬體極限
            model += P_ch[sid, t] <= s.charge_max * IsCh[sid, t], f"ChargeMax_{sid}_{t}"
            model += P_dis[sid, t] <= s.discharge_max * (1 - IsCh[sid, t]), f"DischargeMax_{sid}_{t}"
            
            # [constraint 1] 電池電量不能低於大限（保護電池）或高於容量上限
            model += SOC[sid, t] >= s.soc_min, f"SOC_Min_{sid}_{t}"
            model += SOC[sid, t] <= s.soc_max, f"SOC_Max_{sid}_{t}"
            
            # 3. 核心：SOC 狀態轉移方程 (考慮充放電效率 efficiency)
            # 本小時電量 = 上一小時電量 + 充電 - 放電 
            model += SOC[sid, t] == SOC[sid, t-1] + P_ch[sid, t] - P_dis[sid, t] , f"SOC_Dynamics_{sid}_{t}"

        # [constraint 20] 發電設備的分配上限
        for i in gen_ids:
            model += pulp.lpSum(k[j, i, t] for j in job_ids) <= P[i, t], f"GenDistLimit_{i}_{t}"
        for i in res_ids:
            model += pulp.lpSum(k[j, i, t] for j in job_ids) <= P_res[i, t], f"ResDistLimit_{i}_{t}"

        # [constraint 23] 系統全局能量平衡
        total_generate = pulp.lpSum(P[i, t] for i in gen_ids) + pulp.lpSum(P_res[i, t] for i in res_ids) + pulp.lpSum(P_dis[sid,t] for sid in storage_ids)
        total_consume = pulp.lpSum(k[j, i, t] for j in job_ids for i in all_sources) + pulp.lpSum(P_ch[sid,t] for sid in storage_ids)
        
        model += total_generate == total_consume + Sell[t], f"GlobalBalance_{t}"
    
    return model, P, U, x, k, Sell, P_res, jobs, P_ch, P_dis, SOC



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

    model, P, U, x, k, Sell, P_res, jobs, P_ch, P_dis, SOC = build_pulp_model(generator_set, task_set, renewable_set) 

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
    total_revenue = pulp.lpSum(Sell[t] * price_72[t-1] for t in time_steps)
    
    # 把目標函數加進 model 中 (沒有 <=, >= 或 ==，這就是目標函數！)
    model += total_gen_cost - total_revenue

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
        storage_ids = [s.storage_id for s in storage_set]
        all_sources = gen_ids + res_ids  + storage_ids
        # 遍歷 72 小時
        for t in time_steps:
            time_step_data = {
                "t": t,
                "P": {},
                "k": {},
                "sell": 0.0,
                "soc": {},                
                "missed_aperiodic": [],   
                "rejected_sporadic": []   
            }
            
            # 1. 填寫 P 矩陣 (發電機與再生能源出力)
            for i in gen_ids:
                val = round(pulp.value(P[i, t]), 2)
                time_step_data["P"][i] = val
            
            for i in res_ids:
                val = round(pulp.value(P_res[i, t]), 2)
                time_step_data["P"][i] = val
                
            for i in [r.renewable_id for r in renewable_set]:
                val = round(pulp.value(P_res[i, t]), 2)
                time_step_data["P"][i] = val
            
            # 2. 填寫 k 矩陣 (每個 Job 從每個設備拿了多少電)
            for job in jobs:
                j = job["job_id"]
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
            
            for sid in storage_ids:
                time_step_data["soc"][sid] = {
                    "energy": round(pulp.value(SOC[sid, t]), 2),     # 當下電量
                    "charge": round(pulp.value(P_ch[sid, t]), 2),    # 當下充電功率
                    "discharge": round(pulp.value(P_dis[sid, t]), 2) # 當下放電功率
                }

            # 將這個小時的狀態加入清單
            final_output["schedule_result"].append(time_step_data)
            
        # 4. 匯出檔案
        output_path = "output/schedule_result.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)
            
        print(f"Json 寫入至 {output_path}")
    else:
        print("Infeasible!")


