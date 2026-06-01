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
class Task_unexpected:         # [class] aperiodic / Sporadic task]
    task_id: str    # id
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

def load_task():        
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

def load_un_task():     
    task_set = []
    path = "input/aperiodic_n_sporadic.json"
    with open(path,'r') as f:
        data = json.load(f)
    for a_id, info in data["aperiodic"].items():
        task_set.append(Task_unexpected(
            task_id = a_id,
            r= info["r"],          
            e= info["e"],          
            d= info["d"],
            w= info["w"],          
            preempt= info["preempt"],
            type = 0
        ))
    for s_id, info in data["sporadic"].items():
        task_set.append(Task_unexpected(
            task_id= s_id,
            r= info["r"],          
            e= info["e"],          
            d= info["d"],
            w= info["w"],          
            preempt= info["preempt"],
            type = 1
        ))
    return task_set

def load_environment():       
    path_1 = "input/processor_settings.json"
    with open(path_1,'r') as f:
        data = json.load(f)
    
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
    
    path_2 = "input/price_72hr.json"
    with open(path_2,'r') as f:
        data = json.load(f)
    data_price = data["price"]
    price_72 = [entry["market_price"] for entry in data_price]
    print("[price 72 loading] success")
    
    return generator_set,storage_set,renewable_set,price_72

class VPPScheduler:
    def __init__(self, generator_set, storage_set, renewable_set, price_72, time_horizon=72):
        self.generator_set = generator_set
        self.storage_set = storage_set
        self.renewable_set = renewable_set
        self.price_72 = price_72
        self.time_horizon = time_horizon
        self.time_steps = list(range(1, time_horizon + 1))
        
        self.gen_ids = [g.generator_id for g in generator_set]
        self.res_ids = [r.renewable_id for r in renewable_set]
        self.storage_ids = [s.storage_id for s in storage_set]
        self.all_sources = self.gen_ids + self.res_ids + self.storage_ids
        
        self.model = pulp.LpProblem("VPP_Scheduling", pulp.LpMinimize)
        self.jobs = []            
        self.job_ids = []         
        self.periodic_jobs = []   

        self.acceptance_log = []  
        self.locked_time = 0
        
        self.vars = {}            
        
        self.missed_aperiodic = []
        self.rejected_sporadic = []

        self.missed_at_t = {t: [] for t in self.time_steps}
        self.rejected_at_t = {t: [] for t in self.time_steps}

    def init_base_model(self, periodic_task_set):
        for task in periodic_task_set:  
            current_t = task.r
            instance = 1
            while current_t + task.e - 1 <= self.time_horizon:
                job_id = f"{task.task_id}_{instance}"
                job_dict = {
                    "job_id": job_id, "w": task.w, "e": task.e, 
                    "r": current_t, "d": task.d, "preempt": task.preempt, 
                    "type": "periodic"
                }
                self.jobs.append(job_dict)
                self.periodic_jobs.append(job_dict)
                current_t += task.p
                instance += 1
        self.job_ids = [j["job_id"] for j in self.jobs]

        v = self.vars
        v["P"] = pulp.LpVariable.dicts("Power", ((i, t) for i in self.gen_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        v["U"] = pulp.LpVariable.dicts("Status", ((i, t) for i in self.gen_ids for t in self.time_steps), cat='Binary')
        v["P_res"] = pulp.LpVariable.dicts("Power_Renew", ((i, t) for i in self.res_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        v["Sell"] = pulp.LpVariable.dicts("Sell", self.time_steps, lowBound=0, cat='Continuous')
        
        v["P_ch"] = pulp.LpVariable.dicts("Charge", ((s, t) for s in self.storage_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        v["P_dis"] = pulp.LpVariable.dicts("Discharge", ((s, t) for s in self.storage_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        v["SOC"] = pulp.LpVariable.dicts("SOC", ((s, t) for s in self.storage_ids for t in [0] + self.time_steps), lowBound=0, cat='Continuous')
        v["IsCh"] = pulp.LpVariable.dicts("IsCharging", ((s, t) for s in self.storage_ids for t in self.time_steps), cat='Binary')

        v["k"] = pulp.LpVariable.dicts("k", ((j, i, t) for j in self.job_ids for i in self.all_sources for t in self.time_steps), lowBound=0, cat='Continuous')
        v["x"] = pulp.LpVariable.dicts("TaskExe", ((j, t) for j in self.job_ids for t in self.time_steps), cat='Binary')

        self._build_generator_constraints()
        self._build_storage_constraints()
        for job in self.periodic_jobs:
            self._build_job_constraints(job)
        self._update_objective()

    def _build_generator_constraints(self):
        v = self.vars
        for g in self.generator_set:
            i = g.generator_id
            assert g.output_min <= g.ramp_up_rate
            u_initial = 1 if (g.initial_on_time > 0 or g.initial_energy > 0) else 0

            if u_initial == 1 and 0 < g.initial_on_time < g.min_up_time:
                for t in range(1, min(self.time_horizon, g.min_up_time - g.initial_on_time) + 1):
                    self.model += v["U"][i, t] == 1
            if u_initial == 0 and 0 < g.initial_off_time < g.min_down_time:
                for t in range(1, min(self.time_horizon, g.min_down_time - g.initial_off_time) + 1):
                    self.model += v["U"][i, t] == 0

            for t in self.time_steps:
                u_prev = v["U"][i, t-1] if t > 1 else u_initial
                
                up_win = min(self.time_horizon - t + 1, g.min_up_time) 
                if up_win > 0:
                    self.model += pulp.lpSum(v["U"][i, tau] for tau in range(t, t + up_win)) >= up_win * (v["U"][i, t] - u_prev)    
                
                down_win = min(self.time_horizon - t + 1, g.min_down_time)
                if down_win > 0:
                    self.model += pulp.lpSum(v["U"][i, tau] for tau in range(t, t + down_win)) <= down_win - down_win * (u_prev - v["U"][i, t])
                
                self.model += v["P"][i, t] >= g.output_min * v["U"][i, t]
                self.model += v["P"][i, t] <= g.output_max * v["U"][i, t]
                
                if t == 1:
                    self.model += v["P"][i, t] - g.initial_energy <= g.ramp_up_rate
                    self.model += g.initial_energy - v["P"][i, t] <= g.ramp_down_rate
                else:
                    self.model += v["P"][i, t] - v["P"][i, t-1] <= g.ramp_up_rate
                    self.model += v["P"][i, t-1] - v["P"][i, t] <= g.ramp_down_rate

    def _build_storage_constraints(self):
        v = self.vars
        for s in self.storage_set:
            self.model += v["SOC"][s.storage_id, 0] == s.soc_init 

        for t in self.time_steps:
            for s in self.storage_set:
                sid = s.storage_id
                self.model += v["P_ch"][sid, t] <= s.charge_max * v["IsCh"][sid, t]
                self.model += v["P_dis"][sid, t] <= s.discharge_max * (1 - v["IsCh"][sid, t])
                
                self.model += v["SOC"][sid, t] >= s.soc_min
                self.model += v["SOC"][sid, t] <= s.soc_max
                
                self.model += v["P_dis"][sid, t] <= v["SOC"][sid, t-1] - s.soc_min
                
                self.model += v["SOC"][sid, t] == v["SOC"][sid, t-1] + v["P_ch"][sid, t] - v["P_dis"][sid, t]
            
            for re in self.renewable_set:
                self.model += v["P_res"][re.renewable_id, t] <= re.capacity * re.pv_forecast[t-1]

    def _build_job_constraints(self, job_dict):
        v = self.vars
        j = job_dict["job_id"]
        r = job_dict["r"]
        e = job_dict["e"]
        
        abs_deadline = r + job_dict["d"] - 1

        if job_dict["type"] == "aperiodic":
            v[f"Miss_{j}"] = pulp.LpVariable(f"Miss_{j}", cat='Binary')     
            v[f"Drop_{j}"] = pulp.LpVariable(f"Drop_{j}", cat='Binary')
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, self.time_horizon + 1)) == e * (1 - v[f"Drop_{j}"])
            
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, min(abs_deadline, self.time_horizon) + 1)) >= e * (1 - v[f"Miss_{j}"])
                
            for t in range(1, r): 
                self.model += v["x"][j, t] == 0

        elif job_dict["type"] == "sporadic":
            v[f"Reject_{j}"] = pulp.LpVariable(f"Reject_{j}", cat='Binary')
            abs_deadline = r + job_dict["d"] - 1
            
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, min(abs_deadline , self.time_horizon) + 1)) == e * (1 - v[f"Reject_{j}"])
                
            for t in self.time_steps:
                if t < r or t > abs_deadline:
                    self.model += v["x"][j, t] == 0

        else: 
            self.model += pulp.lpSum(v["x"][j, t] for t in self.time_steps) == e                    
            for t in self.time_steps:
                if t < r or t > abs_deadline:
                    self.model += v["x"][j, t] == 0
                    
        if job_dict["preempt"] == 0:
            z_vars = []
            if job_dict["type"] == "aperiodic": check_end = self.time_horizon
            else: check_end = min(self.time_horizon, abs_deadline + 1) 
            
            for t in range(r , check_end + 1):
                z = pulp.LpVariable(f"z_{j}_{t}", lowBound=0, cat='Continuous')
                z_vars.append(z)
                x_curr = v["x"].get((j , t) , 0)
                x_prev = v["x"].get((j , t-1) , 0)
                self.model += z >= x_curr - x_prev
                self.model += z >= x_prev - x_curr

            self.model += pulp.lpSum(z_vars) <= 2
            
        for t in self.time_steps:
            self.model += pulp.lpSum(v["k"][j, i, t] for i in self.all_sources) == job_dict["w"] * v["x"][j, t]

    def _apply_dynamic_balance(self):
        v = self.vars
        for t in self.time_steps:

            names_to_remove = [f"GlobalBal_{t}", f"NoBat2Bat_{t}"]
            for i in self.gen_ids: names_to_remove.append(f"GenLimit_{i}_{t}")
            for i in self.res_ids: names_to_remove.append(f"ResLimit_{i}_{t}")
            for sid in self.storage_ids: names_to_remove.append(f"StoLimit_{sid}_{t}")

            for name in names_to_remove:
                if name in self.model.constraints:
                    del self.model.constraints[name]

            for i in self.gen_ids:
                self.model += pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids) <= v["P"][i, t], f"GenLimit_{i}_{t}"
            for i in self.res_ids:
                self.model += pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids) <= v["P_res"][i, t], f"ResLimit_{i}_{t}"
            for sid in self.storage_ids:
                self.model += pulp.lpSum(v["k"].get((j, sid, t), 0) for j in self.job_ids) <= v["P_dis"][sid, t], f"StoLimit_{sid}_{t}"

            gen_res = self.gen_ids + self.res_ids
            task_use = pulp.lpSum(v["k"].get((j, src, t), 0) for j in self.job_ids for src in gen_res)
            avail_power = pulp.lpSum(v["P"][i, t] for i in self.gen_ids) + pulp.lpSum(v["P_res"][i, t] for i in self.res_ids) - task_use
            self.model += pulp.lpSum(v["P_ch"][sid, t] for sid in self.storage_ids) <= avail_power, f"NoBat2Bat_{t}"

            total_gen = pulp.lpSum(v["P"][i, t] for i in self.gen_ids) + pulp.lpSum(v["P_res"][i, t] for i in self.res_ids) + pulp.lpSum(v["P_dis"][sid,t] for sid in self.storage_ids)
            total_con = pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids for i in self.all_sources) + pulp.lpSum(v["P_ch"][sid,t] for sid in self.storage_ids)
            self.model += total_gen == total_con + v["Sell"][t], f"GlobalBal_{t}"

    def _update_objective(self):
        v = self.vars
        cost_var_dict = {g.generator_id: g.cost_variable for g in self.generator_set}
        cost_fixed_dict = {g.generator_id: g.cost_fixed for g in self.generator_set}
        
        total_gen_cost = pulp.lpSum(v["P"][i, t] * cost_var_dict[i] + v["U"][i, t] * cost_fixed_dict[i] for i in self.gen_ids for t in self.time_steps)
        total_revenue = pulp.lpSum(v["Sell"][t] * self.price_72[t-1] for t in self.time_steps)
        
        miss_vars = [val for key, val in v.items() if key.startswith("Miss_")]
        reject_vars = [val for key, val in v.items() if key.startswith("Reject_")]
        drop_vars = [val for key, val in v.items() if key.startswith("Drop_")] 
        
        penalty = (10000 * pulp.lpSum(miss_vars) if miss_vars else 0) + \
                  (1000000 * pulp.lpSum(reject_vars) if reject_vars else 0) + \
                  (1000000 * pulp.lpSum(drop_vars) if drop_vars else 0) 

        self.model.setObjective(total_gen_cost - total_revenue + penalty)
    
    def run_base_schedule(self):
        print("\n--- 正在計算 Base Schedule (Periodic) ---")
        
        self._apply_dynamic_balance()                       
        self.model.solve(pulp.PULP_CBC_CMD(msg=False))      
        
        if pulp.LpStatus[self.model.status] == "Optimal":
            print("=> Base Schedule 成功建立！")
            self.lock_scheduled_jobs(self.periodic_jobs)
            return True
        else:
            print("=> Base Schedule 無解！請檢查參數。")
            return False

    def lock_scheduled_jobs(self, current_jobs_to_lock):    
        for job_dict in current_jobs_to_lock:
            j = job_dict["job_id"]
            for t in self.time_steps:
                fixed_x = round(pulp.value(self.vars["x"][j, t]))
                self.model += self.vars["x"][j, t] == fixed_x

    def process_unexpected_jobs(self, unexpected_tasks):    
        
        v = self.vars
        unexpected_tasks.sort(key=lambda t: t.r)
        
        self.base_u_states = {}     # 新增鎖定 開關機狀態
        for i in self.gen_ids:
            for t in self.time_steps:
                val = pulp.value(v["U"][i, t])
                self.base_u_states[(i, t)] = round(val) if val is not None else 0

        for task in unexpected_tasks:
            print(f" t = {task.r} => {task.task_id}") 
            self._lock_past_states(task.r)

            
            job_dict = {
                "job_id": task.task_id, "w": task.w, "e": task.e, "r": task.r,
                "d": task.d, "preempt": task.preempt, 
                "type": "sporadic" if task.type == 1 else "aperiodic"
            }
            
            self.job_ids.append(job_dict["job_id"])
            self.jobs.append(job_dict)
            v["x"].update(pulp.LpVariable.dicts("TaskExe", ((job_dict["job_id"], t) for t in self.time_steps), cat='Binary'))
            v["k"].update(pulp.LpVariable.dicts("k", ((job_dict["job_id"], i, t) for i in self.all_sources for t in self.time_steps), lowBound=0, cat='Continuous'))
            
            self._build_job_constraints(job_dict)
            self._apply_dynamic_balance()
            self._update_objective()

            # ==========================================
            # === [Step 2-2 核心：加入 Frame 時間窗邊界] ===
            # ==========================================
            abs_deadline = task.r + task.d - 1
            
            # 初始化為新任務本身的 deadline
            dynamic_window_end = abs_deadline 
            
            # 遍歷目前系統中所有的任務 (包含 Periodic 與已經 Accept 的 Sporadic/Aperiodic)
            for job in self.jobs:
                # 排除掉自己
                if job["job_id"] == job_dict["job_id"]:
                    continue
                    
                job_r = job["r"]
                job_abs_d = job["r"] + job["d"] - 1
                
                # 判斷時間窗是否重疊 (交集檢查)：
                # (既有任務的釋放時間 <= 新任務的 deadline) 且 (既有任務的 deadline >= 新任務的釋放時間)
                if job_r <= abs_deadline and job_abs_d >= task.r:
                    # 如果有重疊，且該任務的 deadline 更晚，就撐大 window_end
                    if job_abs_d > dynamic_window_end:
                        dynamic_window_end = job_abs_d
            
            # 確保不會超出排程總時長 (72)
            window_end = min(self.time_horizon, dynamic_window_end) 
            
            self._apply_window_boundaries(task.r, window_end)
            # ==========================================

            # ==========================================
            # === [Step 1-3 修改開始] 兩階段求解邏輯 ===
            # ==========================================
            print(f" [Phase 1] 嘗試局部調度 (不開新機組)...")
            self._lock_all_U()
            self.model.solve(pulp.PULP_CBC_CMD(msg=False)) 
            
            need_phase_2 = False
            status_str = pulp.LpStatus[self.model.status]
            
            if status_str in ["Optimal", "Not Solved"]:
                if task.type == 1:
                    reject_val = pulp.value(v[f"Reject_{job_dict['job_id']}"])
                    if reject_val is not None and round(reject_val) == 1:
                        need_phase_2 = True # 資源枯竭，被迫 Reject，需要救援！
                else:
                    drop_val = pulp.value(v[f"Drop_{task.task_id}"])
                    if drop_val is not None and round(drop_val) == 1:
                        need_phase_2 = True # 資源枯竭，被迫 Drop，需要救援！
            else:
                need_phase_2 = True # Infeasible，連解都找不到，需要救援！

            # 啟動 Phase 2 救援
            if need_phase_2:
                print(f" [Phase 2] 局部資源不足，解開未來機組狀態進行全域救援！")
                self._unlock_future_U(task.r) # Phase 2: 拔掉未來的 U 鎖定
                # 解開了 Binary 變數，給求解器 8 秒去想辦法
                self.model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=12)) 
                status_str = pulp.LpStatus[self.model.status]
            # ==========================================
            
            self.model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=8))
            
            if pulp.LpStatus[self.model.status] == "Optimal":
                if task.type == 1: 
                    reject_val = pulp.value(v[f"Reject_{job_dict["job_id"]}"])
                    is_rejected = True if reject_val is None else (round(reject_val) == 1)
                    
                    if not is_rejected:
                        print("ACCEPTED (Sporadic)")
                        scheduled_times = [t for t in self.time_steps if round(pulp.value(v["x"][job_dict["job_id"], t])) == 1]
                        
                        self.acceptance_log.append({
                            "job_id": task.task_id,
                            "status": "Accepted",
                            "scheduled_time_steps": scheduled_times,
                            "reason": "Sufficient resources available",
                            "constraint_violation": False
                        })
                        self.lock_scheduled_jobs([job_dict])
                    else:
                        print(f" t = {task.r} => {task.task_id} REJECTED (Sporadic)")
                        self.rejected_sporadic.append(task.task_id)
                        self.rejected_at_t[task.r].append(task.task_id)

                        abs_deadline = task.r + task.d - 1
                        time_window = abs_deadline - task.r + 1
                        
                        if time_window < task.e:
                            detailed_reason = f"Insufficient time window: Task requires {task.e} units of execution time, but only {time_window} units are available from arrival (t={task.r}) to deadline (t={abs_deadline})."
                        elif abs_deadline > self.time_horizon and (self.time_horizon - task.r + 1) < task.e:
                            detailed_reason = f"Horizon limit reached: Task requires {task.e} units of time, but only {self.time_horizon - task.r + 1} units remain before the scheduling horizon ends (t={self.time_horizon})."
                        elif task.preempt == 0:
                            detailed_reason = f"Continuity and resource conflict: This task is non-preemptive. The system cannot allocate {task.e} continuous units of sufficient power capacity within the timeframe (t={task.r} to {abs_deadline})."
                        else:
                            detailed_reason = f"Power supply bottleneck: During the task timeframe (t={task.r} to {abs_deadline}), generators are at maximum capacity or storage is depleted. Total remaining available power is insufficient to meet the {task.e}-unit requirement."

                        self.acceptance_log.append({
                            "job_id": task.task_id,
                            "status": "Rejected",
                            "scheduled_time_steps": [],
                            "reason": detailed_reason,
                            "constraint_violation": False 
                        })
                        self.model += v[f"Reject_{job_dict["job_id"]}"] == 1
                        for t in self.time_steps:
                            self.model += v["x"][job_dict["job_id"], t] == 0
                else:
                    drop_val = pulp.value(v[f"Drop_{task.task_id}"])
                    is_dropped = True if drop_val is None else (round(drop_val) == 1)
                    
                    if is_dropped:
                        print(f" t = {task.r} => {task.task_id} DROPPED (Aperiodic)")
                        self.model += v[f"Drop_{task.task_id}"] == 1
                        for t in self.time_steps:
                            self.model += v["x"][task.task_id, t] == 0
                    else: print(f" t = {task.r} => {task.task_id} SCHEDULED (Aperiodic)")

            else:
                print(f"  => {task.task_id} FATAL INFEASIBLE!")
                if task.type == 1:
                    self.rejected_sporadic.append(task.task_id)
                    self.rejected_at_t[task.r].append(task.task_id)
                    self.acceptance_log.append({
                        "job_id": task.task_id,
                        "status": "Rejected",
                        "scheduled_time_steps": [],
                        "reason": "Solver infeasible due to extreme resource conflict.",
                        "constraint_violation": True
                    })
                    self.model += v[f"Reject_{task.task_id}"] == 1
                    for t in self.time_steps:
                        self.model += v["x"][task.task_id, t] == 0
                else:
                    self.model += v[f"Drop_{task.task_id}"] == 1
                    for t in self.time_steps:
                        self.model += v["x"][task.task_id, t] == 0
            print()
            self._remove_window_boundaries()

    def _lock_all_U(self):  # 新增lock function
        v = self.vars
        for i in self.gen_ids:
            for t in self.time_steps:
                name = f"Phase1_U_Lock_{i}_{t}"
                if name not in self.model.constraints:
                    self.model += v["U"][i, t] == self.base_u_states[(i, t)], name

    def _unlock_future_U(self, current_r):  # 新增 unlock function
        for i in self.gen_ids:
            for t in range(current_r, self.time_horizon + 1):
                name = f"Phase1_U_Lock_{i}_{t}"
                if name in self.model.constraints:
                    del self.model.constraints[name]

    def _lock_past_states(self, current_r):                 
        v = self.vars
        
        for t in range(self.locked_time + 1, current_r):
            
            for i in self.gen_ids:
                u_val = pulp.value(v["U"][i, t])
                if u_val is not None:
                    self.model += v["U"][i, t] == round(u_val), f"TimeLock_U_{i}_{t}"
                
                p_val = pulp.value(v["P"][i, t])
                if p_val is not None:
                    p_val = max(0.0, p_val) 
                    self.model += v["P"][i, t] >= p_val - 1e-3, f"TimeLock_P_lb_{i}_{t}"
                    self.model += v["P"][i, t] <= p_val + 1e-3, f"TimeLock_P_ub_{i}_{t}"
            
            for sid in self.storage_ids:
                isch_val = pulp.value(v["IsCh"][sid, t])
                if isch_val is not None:
                    self.model += v["IsCh"][sid, t] == round(isch_val), f"TimeLock_IsCh_{sid}_{t}"
                
                ch_val = pulp.value(v["P_ch"][sid, t])
                if ch_val is not None:
                    ch_val = max(0.0, ch_val)
                    self.model += v["P_ch"][sid, t] >= ch_val - 1e-3, f"TimeLock_Pch_lb_{sid}_{t}"
                    self.model += v["P_ch"][sid, t] <= ch_val + 1e-3, f"TimeLock_Pch_ub_{sid}_{t}"
                    
                dis_val = pulp.value(v["P_dis"][sid, t])
                if dis_val is not None:
                    dis_val = max(0.0, dis_val)
                    self.model += v["P_dis"][sid, t] >= dis_val - 1e-3, f"TimeLock_Pdis_lb_{sid}_{t}"
                    self.model += v["P_dis"][sid, t] <= dis_val + 1e-3, f"TimeLock_Pdis_ub_{sid}_{t}"
        
        self.locked_time = max(self.locked_time, current_r - 1)    

    def _apply_window_boundaries(self, task_r, window_end):
        v = self.vars
        self.active_window_constraints = [] 

        # 1. 鎖死 window_end 之後的 Periodic Tasks
        for job in self.periodic_jobs:
            # 如果這個 Periodic 任務是在 window_end 之後才 release，就把它鎖死在「上一輪算出的排程」
            if job["r"] > window_end:
                j = job["job_id"]
                for t in range(window_end + 1, self.time_horizon + 1):
                    x_val = pulp.value(v["x"][j, t])
                    if x_val is not None:
                        name = f"Window_x_Lock_{j}_{t}_{task_r}"
                        self.model += v["x"][j, t] == round(x_val), name
                        self.active_window_constraints.append(name)
                        
        # 2. SOC 邊界防護：確保局部重排不會榨乾未來的電池
        for sid in self.storage_ids:
            expected_soc = pulp.value(v["SOC"][sid, window_end])
            if expected_soc is not None:
                name = f"Window_SOC_Bound_{sid}_{task_r}"
                self.model += v["SOC"][sid, window_end] >= expected_soc - 1e-3, name
                self.active_window_constraints.append(name)

        # 3. 傳統機組 Ramp-up 銜接：確保 window_end 的出力可以順利過渡到未來的排程
        if window_end < self.time_horizon:
            for g in self.generator_set:
                i = g.generator_id
                next_p = pulp.value(v["P"][i, window_end + 1])
                if next_p is not None:
                    name1 = f"Window_RampUp_{i}_{task_r}"
                    name2 = f"Window_RampDown_{i}_{task_r}"
                    self.model += next_p - v["P"][i, window_end] <= g.ramp_up_rate, name1
                    self.model += v["P"][i, window_end] - next_p <= g.ramp_down_rate, name2
                    self.active_window_constraints.append(name1)
                    self.active_window_constraints.append(name2)

    def _remove_window_boundaries(self):
        # 任務處理完畢後，把剛剛加的局部邊界拆掉，迎接下一個時間點的新任務
        if hasattr(self, 'active_window_constraints'):
            for name in self.active_window_constraints:
                if name in self.model.constraints:
                    del self.model.constraints[name]
            self.active_window_constraints = []

if __name__ == "__main__":
    try:
        task_set = load_task()
        print("[task loading] success")
    except Exception as e:
        print(f"[task loading] fail:{e}")
        task_set = []
        
    try:
        unexpected_set = load_un_task()
        print("[unexpected task loading] success")
    except Exception as e:
        print(f"[unexpected task loading] fail:{e}")
        unexpected_set = []

    try:
        generator_set, storage_set, renewable_set, price_72 = load_environment()
        print("[environment loading] success")
    except Exception as e:
        print(f"[environment loading] fail:{e}")
        generator_set, storage_set, renewable_set, price_72 = [], [], [], []

    scheduler = VPPScheduler(generator_set, storage_set, renewable_set, price_72)
    
    scheduler.init_base_model(task_set)
    success = scheduler.run_base_schedule()

    if success and unexpected_set:
        print("\n--- 開始處理動態任務 (Acceptance Test) ---")
        scheduler.process_unexpected_jobs(unexpected_set)


    status_str = pulp.LpStatus[scheduler.model.status]
    print(f"\n最終求解狀態: {status_str}")


    gen_ids = scheduler.gen_ids
    res_ids = scheduler.res_ids
    storage_ids = scheduler.storage_ids
    all_sources = scheduler.all_sources

    if status_str == "Optimal":
        v = scheduler.vars

        cost_var_dict = {g.generator_id: g.cost_variable for g in generator_set}
        cost_fixed_dict = {g.generator_id: g.cost_fixed for g in generator_set}
        real_gen_cost = sum(
            pulp.value(v["P"][i, t]) * cost_var_dict[i] + pulp.value(v["U"][i, t]) * cost_fixed_dict[i]
            for i in gen_ids for t in scheduler.time_steps
        )
        real_revenue = sum(pulp.value(v["Sell"][t]) * price_72[t-1] for t in scheduler.time_steps)
        real_net_cost = real_gen_cost - real_revenue

        for key, val in v.items():
            if key.startswith("Miss_") and pulp.value(val) is not None and round(pulp.value(val)) == 1:
                base_id = key.replace("Miss_", "")
                
                if base_id not in scheduler.missed_aperiodic:
                    scheduler.missed_aperiodic.append(base_id) 
                
                target_job = next(job for job in scheduler.jobs if job["job_id"] == base_id)
                abs_deadline = target_job["r"] + target_job["d"] - 1
                
                miss_log_time = min(abs_deadline + 1, scheduler.time_horizon)
                scheduler.missed_at_t[miss_log_time].append(base_id)

        print(f"預估發電總成本: $ {real_gen_cost:.2f}")
        print(f"預估售電總收益: $ {real_revenue:.2f}")
        print(f"系統真實淨成本 (不含虛擬罰款): $ {real_net_cost:.2f}")
        print(f"Rejected Sporadic 數量: {len(scheduler.rejected_sporadic)}")
        print(f"Missed Aperiodic 數量: {len(scheduler.missed_aperiodic)}")

        final_output = {
            "schedule_result": []
        }

        for t in scheduler.time_steps:
            time_step_data = {
                "t": t,
                "P": {},  
                "k": {},  
                "sell": 0.0,
                "soc": {},                
                "missed_aperiodic": scheduler.missed_at_t[t],   
                "rejected_sporadic": scheduler.rejected_at_t[t]  
            }
            
            for i in gen_ids:
                val = pulp.value(v["P"][i, t])
                time_step_data["P"][i] = round(val, 2)
            
            for i in res_ids:
                val = pulp.value(v["P_res"][i, t])
                time_step_data["P"][i] = round(val, 2)
                
            for sid in storage_ids:
                val = pulp.value(v["P_dis"][sid, t])
                time_step_data["P"][sid] = round(val, 2)
            
            for job in scheduler.jobs:
                j = job["job_id"]
                base_id = j.rsplit('_', 1)[0]

                task_k_dict = {}
                for i in all_sources:
                    k_var = v["k"].get((j, i, t))
                    if k_var is not None:
                        val = pulp.value(k_var)
                        if val is not None and val > 0:
                            task_k_dict[i] = round(val, 2)
                
                if task_k_dict:
                    time_step_data["k"][base_id] = task_k_dict
            
            remaining_power = {}
            for i in gen_ids + res_ids: 
                gen_p = time_step_data["P"].get(i, 0.0)
                used_p = 0.0
                for task_sources in time_step_data["k"].values():
                    used_p += task_sources.get(i, 0.0)
                remaining_power[i] = max(0.0, gen_p - used_p)
            
            for sid in storage_ids:
                chg_val = pulp.value(v["P_ch"][sid, t])
                if chg_val is not None and chg_val > 0:
                    chg_val = round(chg_val, 2)
                    chg_key = f"{sid}_chg"
                    time_step_data["k"][chg_key] = {}
                    
                    for i, avail in remaining_power.items():
                        if chg_val <= 0:
                            break
                        if avail > 0:
                            take = min(avail, chg_val)
                            take = round(take, 2)
                            if take > 0:
                                time_step_data["k"][chg_key][i] = take
                                chg_val = round(chg_val - take, 2)
                                remaining_power[i] -= take

            sell_val = pulp.value(v["Sell"][t])
            time_step_data["sell"] = round(sell_val, 2) if sell_val else 0.0
            
            for sid in storage_ids:
                soc_val = pulp.value(v["SOC"][sid, t])
                time_step_data["soc"][sid] = round(soc_val, 2) if soc_val else 0.0

            final_output["schedule_result"].append(time_step_data)

        output_path = "output/schedule_result_advanced.json"        # 這邊修改成 advanced 版的 scheduler_result_advanced.json
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True) 
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)
            
        print(f"\nJson 成功寫入至 {output_path}")

        log_output_path = "output/acceptance_test_log_advanced.json"    # 這邊修改成 advanced 版的 acceptance_test_log.json
        
        log_data = {
            "acceptance_test_log_advanced": scheduler.acceptance_log
        }
        
        with open(log_output_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)
            
        print(f"Acceptance Test Log 成功寫入至 {log_output_path}")
    else:
        print("Infeasible! 模型無解，請檢查輸入參數與限制式。")

   