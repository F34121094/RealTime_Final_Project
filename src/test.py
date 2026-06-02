import json
from dataclasses import dataclass
from typing import List, Dict
import pulp
import random
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
            pv_forecast= forecast,
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

class VPPScheduler:
    def __init__(self, generator_set, storage_set, renewable_set, price_72, time_horizon=72):
        self.generator_set = generator_set
        self.storage_set = storage_set
        self.renewable_set = renewable_set
        self.price_72 = price_72
        self.time_horizon = time_horizon
        self.time_steps = list(range(1, time_horizon + 1))
        
        # [新增] 預先整理好各設備的 ID 清單
        self.gen_ids = [g.generator_id for g in generator_set]
        self.res_ids = [r.renewable_id for r in renewable_set]
        self.storage_ids = [s.storage_id for s in storage_set]
        self.all_sources = self.gen_ids + self.res_ids + self.storage_ids
        
        self.model = pulp.LpProblem("VPP_Scheduling", pulp.LpMinimize)
        self.jobs = []            # 記錄系統內所有的 job 字典
        self.job_ids = []         # 記錄所有的 job_id
        self.periodic_jobs = []   # 單獨記錄 Periodic job

        self.acceptance_log = []  # 用來之後輸出程acceptance test log
        self.locked_time = 0
        
        self.vars = {}            # [新增] 用一個字典來統一管理所有的 PuLP 變數
        
        self.missed_aperiodic = []
        self.rejected_sporadic = []

        # [新增] 為了 JSON 輸出方法二準備的「按時間分類」字典
        self.missed_at_t = {t: [] for t in self.time_steps}
        self.rejected_at_t = {t: [] for t in self.time_steps}

    def init_base_model(self, periodic_task_set):
        for task in periodic_task_set:  # 將任務展開
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
        # 傳統機組 i 在時間點 t 的出力
        v["P"] = pulp.LpVariable.dicts("Power", ((i, t) for i in self.gen_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        # 傳統機組 i 在時間點 t 的開/關機
        v["U"] = pulp.LpVariable.dicts("Status", ((i, t) for i in self.gen_ids for t in self.time_steps), cat='Binary')
        # 再生能源 i 在時間點 t 的出力
        v["P_res"] = pulp.LpVariable.dicts("Power_Renew", ((i, t) for i in self.res_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        # 在時間點 t 賣給市場的電 [Constraint 22]
        v["Sell"] = pulp.LpVariable.dicts("Sell", self.time_steps, lowBound=0, cat='Continuous')
        
        # 電池 s 在時間點 t 的充電量 
        v["P_ch"] = pulp.LpVariable.dicts("Charge", ((s, t) for s in self.storage_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        # 電池 s 在時間點 t 的放電量
        v["P_dis"] = pulp.LpVariable.dicts("Discharge", ((s, t) for s in self.storage_ids for t in self.time_steps), lowBound=0, cat='Continuous')
        # 電池 s 在時間點 t 剩餘的電量
        v["SOC"] = pulp.LpVariable.dicts("SOC", ((s, t) for s in self.storage_ids for t in [0] + self.time_steps), lowBound=0, cat='Continuous')
        # 電池 s 在時間點 t 是充電還是放電狀態 [Constraint 19]
        v["IsCh"] = pulp.LpVariable.dicts("IsCharging", ((s, t) for s in self.storage_ids for t in self.time_steps), cat='Binary')

        #[level 2] 簽訂契約的變數
        v["Sell_Surplus"] = pulp.LpVariable.dicts("Sell_Surplus", self.time_steps, lowBound=0, cat='Continuous') 
        v["Sell_Deficit"] = pulp.LpVariable.dicts("Sell_Deficit", self.time_steps, lowBound=0, cat='Continuous')

        # 任務 j 在時間點 t 從發電設備 i 拿了多少電 
        v["k"] = pulp.LpVariable.dicts("k", ((j, i, t) for j in self.job_ids for i in self.all_sources for t in self.time_steps), lowBound=0, cat='Continuous')
        # 任務 j 在時間點 t 是否在執行
        v["x"] = pulp.LpVariable.dicts("TaskExe", ((j, t) for j in self.job_ids for t in self.time_steps), cat='Binary')

        # 呼叫下方的模組化函數來建立限制式
        self._build_generator_constraints()
        self._build_storage_constraints()
        for job in self.periodic_jobs:
            self._build_job_constraints(job)
        self._update_objective()

    def _build_generator_constraints(self):
        v = self.vars
        for g in self.generator_set:
            i = g.generator_id
            # [Constraint 8] : 最小出力 <= ramp up
            assert g.output_min <= g.ramp_up_rate
            u_initial = 1 if (g.initial_on_time > 0 or g.initial_energy > 0) else 0

            # [Constraint 11] : 排程前的關機時間限制
            if u_initial == 1 and 0 < g.initial_on_time < g.min_up_time:
                for t in range(1, min(self.time_horizon, g.min_up_time - g.initial_on_time) + 1):
                    self.model += v["U"][i, t] == 1
            # [Constraint 12] : 排程前的開機時間限制
            if u_initial == 0 and 0 < g.initial_off_time < g.min_down_time:
                for t in range(1, min(self.time_horizon, g.min_down_time - g.initial_off_time) + 1):
                    self.model += v["U"][i, t] == 0

            for t in self.time_steps:
                u_prev = v["U"][i, t-1] if t > 1 else u_initial
                
                # [Constraint 9] : 最小開機時數限制 
                up_win = min(self.time_horizon - t + 1, g.min_up_time) 
                if up_win > 0:
                    # 後面那個等於 up_win * 1 的時候代表 "從關機變成開機狀態" 前面要 >= 後面代表 "累積開機時數至少要 >= 最小開機時數"
                    self.model += pulp.lpSum(v["U"][i, tau] for tau in range(t, t + up_win)) >= up_win * (v["U"][i, t] - u_prev)    
                
                # [Constraint 10] : 最小關機時數限制
                down_win = min(self.time_horizon - t + 1, g.min_down_time)
                if down_win > 0:
                    # 這邊的限制是是因為關機狀態會是0，所以其實是在限制接下來的時間都要是 0
                    self.model += pulp.lpSum(v["U"][i, tau] for tau in range(t, t + down_win)) <= down_win - down_win * (u_prev - v["U"][i, t])
                
                # [Constraint 6] : 最大/最小出力的上下限
                self.model += v["P"][i, t] >= g.output_min * v["U"][i, t]
                self.model += v["P"][i, t] <= g.output_max * v["U"][i, t]
                
                # [Constraint 7] : ramp_up / ramp_down 的限制
                if t == 1:
                    self.model += v["P"][i, t] - g.initial_energy <= g.ramp_up_rate
                    self.model += g.initial_energy - v["P"][i, t] <= g.ramp_down_rate
                else:
                    self.model += v["P"][i, t] - v["P"][i, t-1] <= g.ramp_up_rate
                    self.model += v["P"][i, t-1] - v["P"][i, t] <= g.ramp_down_rate

    def _build_storage_constraints(self):
        v = self.vars
        for s in self.storage_set:
            self.model += v["SOC"][s.storage_id, 0] == s.soc_init # 初始電量

        for t in self.time_steps:
            for s in self.storage_set:
                sid = s.storage_id
                # [Constraint 15] : 最大充電限制
                self.model += v["P_ch"][sid, t] <= s.charge_max * v["IsCh"][sid, t]
                # [Constraint 14] : 最大放電限制
                self.model += v["P_dis"][sid, t] <= s.discharge_max * (1 - v["IsCh"][sid, t])
                
                # [level 2] 中新增的電池充電保護機制
                limit_expr = s.charge_max * (1 - (v["SOC"][sid, t-1] - s.soc_max * 0.8) / (s.soc_max * 0.2)) + 0.01
                self.model += v["P_ch"][sid, t] <= limit_expr

                # [Constraint 17] : 儲能設備的儲能 上下限
                self.model += v["SOC"][sid, t] >= s.soc_min
                self.model += v["SOC"][sid, t] <= s.soc_max
                
                # [Constraint 18] : 不能放出超過最低存量的電能 
                self.model += v["P_dis"][sid, t] <= v["SOC"][sid, t-1] - s.soc_min + 0.01
                
                # [Constraint 16] : 電量守恆限制
                sigma = 0.01
                self.model += v["SOC"][sid, t] == v["SOC"][sid, t-1] * (1 - sigma) + v["P_ch"][sid, t] - v["P_dis"][sid, t]
            
            # [Constraint 13] : 再生能源預測電量限制
            for re in self.renewable_set:
                self.model += v["P_res"][re.renewable_id, t] <= re.capacity * re.pv_forecast[t-1] * 0.95

    def _build_job_constraints(self, job_dict):
        v = self.vars
        j = job_dict["job_id"]
        r = job_dict["r"]
        e = job_dict["e"]
        
        abs_deadline = r + job_dict["d"] - 1

        if job_dict["type"] == "aperiodic":
            v[f"Miss_{j}"] = pulp.LpVariable(f"Miss_{j}", cat='Binary')     
            v[f"Drop_{j}"] = pulp.LpVariable(f"Drop_{j}", cat='Binary')
            # 假設 drop => 執行時間為 0  沒有drop => 執行時間就要是execution time
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, self.time_horizon + 1)) == e * (1 - v[f"Drop_{j}"])
            
            # [Constraint 4] : Miss 的限制
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, min(abs_deadline, self.time_horizon) + 1)) >= e * (1 - v[f"Miss_{j}"])
                
            for t in range(1, r): # [Constraint 2] Release time 前不可執行
                self.model += v["x"][j, t] == 0

        elif job_dict["type"] == "sporadic":
            # [新增] 設立 Reject 變數 (0=接受, 1=拒絕)
            v[f"Reject_{j}"] = pulp.LpVariable(f"Reject_{j}", cat='Binary')
            abs_deadline = r + job_dict["d"] - 1
            
            # 關鍵修改：如果拒絕 (Reject=1)，等號右邊就會變成 0，任務就不用執行了！
            self.model += pulp.lpSum(v["x"][j, t] for t in range(r, min(abs_deadline , self.time_horizon) + 1)) == e * (1 - v[f"Reject_{j}"])
                
            # [Constraint 2] Release time 前不可執行 + # [Constraint 3] 用電需求在 deadline 前做完
            for t in self.time_steps:
                if t < r or t > abs_deadline:
                    self.model += v["x"][j, t] == 0

        else: # Periodic 
            # [Constraint 3] 用電需求在 deadline 前做完
            self.model += pulp.lpSum(v["x"][j, t] for t in self.time_steps) == e                    # [Constraint 3] : deadline 前要做完所需的時間
            for t in self.time_steps:
                # [Constraint 2] : Release time 之前不能執行
                if t < r or t > abs_deadline:
                    self.model += v["x"][j, t] == 0
                    
        # [Constraint 5] : non-preemptive 要連續執行
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
            
        # [Constraint 1] : 有執行就要給電限制
        for t in self.time_steps:
            self.model += pulp.lpSum(v["k"][j, i, t] for i in self.all_sources) == job_dict["w"] * v["x"][j, t]

    def _apply_dynamic_balance(self):
        v = self.vars

        for t in self.time_steps:
            
            if hasattr(self, 'commit_sell'):    # [level 2] 售電契約
                constraint_name = f"Sell_Commitment_Balance_{t}"
                if constraint_name in self.model.constraints:
                        del self.model.constraints[constraint_name]
                        
                self.model += v["Sell"][t] == self.commit_sell[t] + v["Sell_Surplus"][t] - v["Sell_Deficit"][t], constraint_name
        
            # ==========================================
            # 1. 拆除舊的動態限制式 (如果它們存在的話)
            # ==========================================
            names_to_remove = [f"GlobalBal_{t}", f"NoBat2Bat_{t}"]
            for i in self.gen_ids: names_to_remove.append(f"GenLimit_{i}_{t}")
            for i in self.res_ids: names_to_remove.append(f"ResLimit_{i}_{t}")
            for sid in self.storage_ids: names_to_remove.append(f"StoLimit_{sid}_{t}")

            for name in names_to_remove:
                if name in self.model.constraints:
                    del self.model.constraints[name]

            # ==========================================
            # 2. 建立包含「所有最新任務」的新限制式 (並強制命名)
            # ==========================================
            # [Constraint 20]: 設備被抽走的電 <= 該設備產生的電
            for i in self.gen_ids:
                self.model += pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids) <= v["P"][i, t], f"GenLimit_{i}_{t}"
            for i in self.res_ids:
                self.model += pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids) <= v["P_res"][i, t], f"ResLimit_{i}_{t}"
            for sid in self.storage_ids:
                self.model += pulp.lpSum(v["k"].get((j, sid, t), 0) for j in self.job_ids) <= v["P_dis"][sid, t], f"StoLimit_{sid}_{t}"
            
                        
            # [Constraint 21]: 電池防弊
            gen_res = self.gen_ids + self.res_ids
            task_use = pulp.lpSum(v["k"].get((j, src, t), 0) for j in self.job_ids for src in gen_res)
            avail_power = pulp.lpSum(v["P"][i, t] for i in self.gen_ids) + pulp.lpSum(v["P_res"][i, t] for i in self.res_ids) - task_use
            self.model += pulp.lpSum(v["P_ch"][sid, t] for sid in self.storage_ids) <= avail_power, f"NoBat2Bat_{t}"

            # [Constraint 23]: 全局能量平衡
            total_gen = pulp.lpSum(v["P"][i, t] for i in self.gen_ids) + pulp.lpSum(v["P_res"][i, t] for i in self.res_ids) + pulp.lpSum(v["P_dis"][sid,t] for sid in self.storage_ids)
            total_con = pulp.lpSum(v["k"].get((j, i, t), 0) for j in self.job_ids for i in self.all_sources) + pulp.lpSum(v["P_ch"][sid,t] for sid in self.storage_ids)
            self.model += total_gen == total_con + v["Sell"][t], f"GlobalBal_{t}"

    def _update_objective(self):
        v = self.vars
        cost_var_dict = {g.generator_id: g.cost_variable for g in self.generator_set}
        cost_fixed_dict = {g.generator_id: g.cost_fixed for g in self.generator_set}
        
        total_gen_cost = pulp.lpSum(v["P"][i, t] * cost_var_dict[i] + v["U"][i, t] * cost_fixed_dict[i] for i in self.gen_ids for t in self.time_steps)
        if hasattr(self, 'commit_sell'):
            # 如果 commit_sell 存在，代表進入了第二階段 (動態重排程)
            total_revenue = pulp.lpSum(
                self.commit_sell[t] * self.price_72[t-1] + 
                v["Sell_Surplus"][t] * (self.price_72[t-1] * 0.7) - 
                v["Sell_Deficit"][t] * 100
                for t in self.time_steps
            )
        else:
            # 如果 commit_sell 不存在，代表還在第一階段 (Base Schedule)
            total_revenue = pulp.lpSum(
                v["Sell"][t] * self.price_72[t-1] 
                for t in self.time_steps
            )
        
        # --- [level 2] 電池老化成本 ---
        deg_cost_per_mwh = 5  
        total_deg_cost = pulp.lpSum(
            (v["P_ch"][sid, t] + v["P_dis"][sid, t]) * deg_cost_per_mwh 
            for sid in self.storage_ids for t in self.time_steps
        )
        # -----------------------------

        miss_vars = [val for key, val in v.items() if key.startswith("Miss_")]
        reject_vars = [val for key, val in v.items() if key.startswith("Reject_")]
        drop_vars = [val for key, val in v.items() if key.startswith("Drop_")] # [修改] 抓出 Drop 變數
        
        penalty = (10000 * pulp.lpSum(miss_vars) if miss_vars else 0) + \
                  (1000000 * pulp.lpSum(reject_vars) if reject_vars else 0) + \
                  (1000000 * pulp.lpSum(drop_vars) if drop_vars else 0) # [修改] 加入 Drop 懲罰

        # [修改] 將 total_deg_cost 加進目標函數中
        self.model.setObjective(total_gen_cost + total_deg_cost - total_revenue + penalty)
    
    def run_base_schedule(self):
        print("\n--- 正在計算 Base Schedule (Periodic) ---")
        
        self._apply_dynamic_balance()                       # 綁定能量平衡限制式
        self.model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit= 15, gapRel=0.02))      # 求解
        self.commit_sell = {}       # [level 2] 簽訂契約
        for t in self.time_steps:
            sell_val = pulp.value(self.vars["Sell"][t])
            self.commit_sell[t] = sell_val if sell_val is not None else 0.0

        if pulp.LpStatus[self.model.status] == "Optimal":
            print("=> Base Schedule 成功建立！")
            # self.lock_scheduled_jobs(self.periodic_jobs)    # 鎖定
            return True
        else:
            print("=> Base Schedule 無解！請檢查參數。")
            return False

    def lock_scheduled_jobs(self, current_jobs_to_lock):    # 鎖定 periodic task 的排程結果
        for job_dict in current_jobs_to_lock:
            j = job_dict["job_id"]
            for t in self.time_steps:
                fixed_x = round(pulp.value(self.vars["x"][j, t]))
                self.model += self.vars["x"][j, t] == fixed_x

    def process_unexpected_jobs(self, unexpected_tasks):    # 用來處理非週期任務
        """[新增] Acceptance Test 核心引擎"""
        v = self.vars
        # 按照任務出現的時間 (r) 排序，模擬真實時間推進
        unexpected_tasks.sort(key=lambda t: t.r)
        
        for task in unexpected_tasks:
            self._lock_past_states(task.r)
            print(f" t = {task.r} => {task.task_id}")
            
            job_dict = {
                "job_id": task.task_id, "w": task.w, "e": task.e, "r": task.r,
                "d": task.d, "preempt": task.preempt, 
                "type": "sporadic" if task.type == 1 else "aperiodic"
            }
            
            # 1. 將新變數加入系統
            self.job_ids.append(job_dict["job_id"])
            self.jobs.append(job_dict)
            v["x"].update(pulp.LpVariable.dicts("TaskExe", ((job_dict["job_id"], t) for t in self.time_steps), cat='Binary'))
            v["k"].update(pulp.LpVariable.dicts("k", ((job_dict["job_id"], i, t) for i in self.all_sources for t in self.time_steps), lowBound=0, cat='Continuous'))
            
            # 2. 建立新任務的限制式並更新全域平衡
            self._build_job_constraints(job_dict)
            self._apply_dynamic_balance()
            self._update_objective()
            
            # 3. 嘗試求解 (Acceptance Test)
            self.model.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit = 15,gapRel=0.02))
            
            if pulp.LpStatus[self.model.status] == "Optimal":
                if task.type == 1: # Sporadic
                    reject_val = pulp.value(v[f"Reject_{job_dict["job_id"]}"])
                    is_rejected = True if reject_val is None else (round(reject_val) == 1)
                    
                    if not is_rejected:
                        print(f"ACCEPTED (Sporadic)\n")
                        scheduled_times = [t for t in self.time_steps if round(pulp.value(v["x"][job_dict["job_id"], t])) == 1]
                        
                        self.acceptance_log.append({
                            "job_id": task.task_id,
                            "status": "Accepted",
                            "scheduled_time_steps": scheduled_times,
                            "reason": "Sufficient resources available",
                            "constraint_violation": False
                        })
                        # self.lock_scheduled_jobs([job_dict])
                    else:
                        print(f"REJECTED (Sporadic)\n")
                        self.rejected_sporadic.append(task.task_id)
                        # [新增] 直接利用當下的 task.r，把任務丟進正確的時間分類裡！
                        self.rejected_at_t[task.r].append(task.task_id)

                        abs_deadline = task.r + task.d - 1
                        time_window = abs_deadline - task.r + 1
                        
                        if time_window < task.e:
                            # Reason 1: Insufficient physical time window
                            detailed_reason = f"Insufficient time window: Task requires {task.e} units of execution time, but only {time_window} units are available from arrival (t={task.r}) to deadline (t={abs_deadline})."
                        elif abs_deadline > self.time_horizon and (self.time_horizon - task.r + 1) < task.e:
                            # Reason 2: Hit the scheduling horizon limit
                            detailed_reason = f"Horizon limit reached: Task requires {task.e} units of time, but only {self.time_horizon - task.r + 1} units remain before the scheduling horizon ends (t={self.time_horizon})."
                        elif task.preempt == 0:
                            # Reason 3: Non-preemptive constraint conflict
                            detailed_reason = f"Continuity and resource conflict: This task is non-preemptive. The system cannot allocate {task.e} continuous units of sufficient power capacity within the timeframe (t={task.r} to {abs_deadline})."
                        else:
                            # Reason 4: Power capacity depletion
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
                        print(f"DROPPED (Aperiodic)\n")
                        
                        # ⚠️ [移除] 不要在這裡加進 missed_aperiodic，交給 72 小時後的總結算統一處理！
                        
                        # 物理封印：既然決定放棄，就強制變數歸零，節省後續求解時間
                        self.model += v[f"Drop_{task.task_id}"] == 1
                        for t in self.time_steps:
                            self.model += v["x"][task.task_id, t] == 0
                    else: print(f"SCHEDULED (Aperiodic)\n")

            else:
                # [防呆補強] 如果 AI 求解器崩潰找不到解 (Infeasible)
                print(f"FATAL INFEASIBLE!\n")
                if task.type == 1:
                    # 強制判為 Rejected
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
                    # 強制判為 Dropped (一樣留給總結算去抓 Miss)
                    self.model += v[f"Drop_{task.task_id}"] == 1
                    for t in self.time_steps:
                        self.model += v["x"][task.task_id, t] == 0

    def _lock_past_states(self, current_r):                 # 鎖定非週期任務來之前的發電、再生能源、儲能設備結果
        v = self.vars
        
        for t in range(self.locked_time + 1, current_r):
            
            for i in self.gen_ids:
                u_val = pulp.value(v["U"][i, t])
                if u_val is not None:
                    self.model += v["U"][i, t] == round(u_val), f"TimeLock_U_{i}_{t}"
                
                # 發電量 (Continuous) 捨棄 ==，改用 ± 0.001 的避震器鎖定
                p_val = pulp.value(v["P"][i, t])
                if p_val is not None:
                    p_val = max(0.0, p_val) # 確保不會低於0
                    self.model += v["P"][i, t] >= p_val - 1e-3, f"TimeLock_P_lb_{i}_{t}"
                    self.model += v["P"][i, t] <= p_val + 1e-3, f"TimeLock_P_ub_{i}_{t}"
            
            # 2. 儲能設備鎖定
            for sid in self.storage_ids:
                # 狀態 (Binary) 絕對鎖死
                isch_val = pulp.value(v["IsCh"][sid, t])
                if isch_val is not None:
                    self.model += v["IsCh"][sid, t] == round(isch_val), f"TimeLock_IsCh_{sid}_{t}"

                
                # 充電量 (Continuous) 避震器鎖定
                ch_val = pulp.value(v["P_ch"][sid, t])
                if ch_val is not None:
                    ch_val = max(0.0, ch_val)
                    self.model += v["P_ch"][sid, t] >= ch_val - 1e-3, f"TimeLock_Pch_lb_{sid}_{t}"
                    self.model += v["P_ch"][sid, t] <= ch_val + 1e-3, f"TimeLock_Pch_ub_{sid}_{t}"
                    
                # 放電量 (Continuous) 避震器鎖定
                dis_val = pulp.value(v["P_dis"][sid, t])
                if dis_val is not None:
                    dis_val = max(0.0, dis_val)
                    self.model += v["P_dis"][sid, t] >= dis_val - 1e-3, f"TimeLock_Pdis_lb_{sid}_{t}"
                    self.model += v["P_dis"][sid, t] <= dis_val + 1e-3, f"TimeLock_Pdis_ub_{sid}_{t}"
        
        # 存檔 下次就直接從這個時間開始鎖定
        self.locked_time = max(self.locked_time, current_r - 1)    

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
                    scheduler.missed_aperiodic.append(base_id) # 紀錄總數
                
                # 透過 next() 從 list of dicts 找出目標任務的詳細資訊
                target_job = next(job for job in scheduler.jobs if job["job_id"] == base_id)
                abs_deadline = target_job["r"] + target_job["d"] - 1
                
                # 決定印出的時間點：abs_deadline 的下一個小時 (防呆: 最高不超過 72)
                miss_log_time = min(abs_deadline + 1, scheduler.time_horizon)
                scheduler.missed_at_t[miss_log_time].append(base_id)

        # ==========================================
        # 4. 建立 JSON 匯出結構
        # ==========================================
        final_output = {
            "schedule_result": []
        }
        bonus_revenue = 0.0 # 記錄總共多出來的電拿去賣賺到的錢
        actual_revenue = 0.0  
        penalty_cost = 0.0

        for t in scheduler.time_steps:
            actual_price = price_72[t-1] * random.uniform(0.95, 1.05)
            
            contract_qty = scheduler.commit_sell[t]
            surplus_qty = pulp.value(v["Sell_Surplus"][t]) or 0.0
            deficit_qty = pulp.value(v["Sell_Deficit"][t]) or 0.0

            time_step_data = {
                "t": t,
                "P": {},  
                "k": {},  
                "sell": 0.0,
                "contract_sell":round(contract_qty),
                "actual_price":round(actual_price,2),
                "soc": {},                
                "missed_aperiodic": scheduler.missed_at_t[t],   
                "rejected_sporadic": scheduler.rejected_at_t[t]  
            }
            
            
            # 依照實際電價結算收益
            step_rev = (contract_qty * actual_price) + (surplus_qty * actual_price * 0.7)
            actual_revenue += step_rev
            
            # 累加違約金 (違約金是固定的 1000 元，不隨電價波動)
            penalty_cost += deficit_qty * 100
            # --- 1. 填寫 P 矩陣 ---
            for i in gen_ids:
                val = pulp.value(v["P"][i, t])
                time_step_data["P"][i] = round(val, 2)
            
            step_surplus_p = 0.0  # [修正 1] 新增：紀錄「這一個小時」多出來的總電量
            
            for i in res_ids:
                scheduled_p = pulp.value(v["P_res"][i, t])
                target_re = next(re for re in generator_set + renewable_set if getattr(re, 'renewable_id', None) == i) 
                
                # 實際天氣波動
                actual_weather_ratio = random.uniform(0.95, 1.05)
                actual_p = target_re.capacity * target_re.pv_forecast[t-1] * actual_weather_ratio
                
                surplus_p = max(0.0, actual_p - scheduled_p)
                step_surplus_p += surplus_p                    # 累加這個小時的溢出電量
                bonus_revenue += surplus_p * price_72[t-1]     # 累加總溢出收益
                
                time_step_data["P"][i] = round(actual_p, 2)
                
            for sid in storage_ids:
                val = pulp.value(v["P_dis"][sid, t])
                time_step_data["P"][sid] = round(val, 2)
            
            # --- 2. 填寫 k 矩陣 ---
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
            
            # --- 3. 計算剩餘電量與電池充電 ---
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

            # --- 4. 填寫售電量與 SOC ---
            sell_val = pulp.value(v["Sell"][t])
            scheduled_sell = sell_val if sell_val else 0.0
            
            # [修正 2] 實際售電 = 計畫售電 + 這小時多出來的電
            actual_sell = scheduled_sell + step_surplus_p 
            time_step_data["sell"] = round(actual_sell, 2)
            
            for sid in storage_ids:
                soc_val = pulp.value(v["SOC"][sid, t])
                time_step_data["soc"][sid] = round(soc_val, 2) if soc_val else 0.0

            final_output["schedule_result"].append(time_step_data)

        # [新增] 結算實際電池老化成本
        deg_cost_per_mwh = 5
        real_deg_cost = sum(
            (pulp.value(v["P_ch"][sid, t]) + pulp.value(v["P_dis"][sid, t])) * deg_cost_per_mwh
            for sid in storage_ids for t in scheduler.time_steps
            if pulp.value(v["P_ch"][sid, t]) is not None and pulp.value(v["P_dis"][sid, t]) is not None
        )

        # 淨成本要加上老化成本
        real_net_cost = real_gen_cost + real_deg_cost - actual_revenue + penalty_cost - bonus_revenue

        print(f"預估發電總成本: $ {real_gen_cost:.2f}")
        print(f"電池老化總成本: $ {real_deg_cost:.2f}")
        print(f"預估售電總收益 (排程內): $ {real_revenue:.2f}")
        print(f"實際售電總收益 (含 +-5% 波動與 0.7 倍折價): $ {actual_revenue:.2f}")
        print(f"售電違約總罰金: $ {penalty_cost:.2f}")
        print(f"真實天氣溢出收益 (Bonus): $ {bonus_revenue:.2f}")
        print(f"系統真實淨成本 (含 Bonus): $ {real_net_cost:.2f}")
        print(f"Rejected Sporadic 數量: {len(scheduler.rejected_sporadic)}")
        print(f"Missed Aperiodic 數量: {len(scheduler.missed_aperiodic)}")
        # 5. 匯出檔案
        output_path = "output/schedule_result.json"
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True) # 確保資料夾存在
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)
            
        print(f"\nJson 成功寫入至 {output_path}")

        log_output_path = "output/acceptance_test_log.json"
        
        # 將剛剛在迴圈裡記錄的 acceptance_log 包裝成字典格式
        log_data = {
            "acceptance_test_log": scheduler.acceptance_log
        }
        
        # 寫入 json 檔案
        with open(log_output_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)
            
        print(f"Acceptance Test Log 成功寫入至 {log_output_path}")
    else:
        print("Infeasible! 模型無解，請檢查輸入參數與限制式。")

   