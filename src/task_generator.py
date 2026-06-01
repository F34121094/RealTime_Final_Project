import json
import os
import random
import math

OUTPUT_FILE_PATH = "output/task_set.json"

def generate_tasks():
    # n = num of tasks
    
    while(1):
        n = random.randint(6,10)
        task_set = {}
        for i in range(1, n + 1):       # 1-4
            # 建議的修改邏輯概念：

            if i <= 2: 
                p = random.choice([8, 12, 16, 20, 24]) 
                e = 4
                d = 4
                pee = random.choice([0, 1])

            elif i <= 4:
                p = random.randint(6, 24)
                e = 2
                pee = 0 
                min_d = 2 * 4 - math.gcd(4, p) 
                d = random.randint(min_d, p)

            else:
                p = random.randint(6, 24)
                e = random.randint(1, 3) 
                pee = random.choice([0, 1])
                min_d = 2 * 4 - math.gcd(4, p)
                d = random.randint(min_d, p)
            
            # w = energy demand
            if i <= 2:           
                w = random.randint(14,18)
            else:
                w = random.randint(6,18)
            
            # r = release time
            r = random.randint(1, p)
            
            task_id = f"p{i}"       # 1-1
            task_set[task_id] = {   # job ID
                "r": r,             # release time
                "p": p,             # period
                "e": e,             # execution time
                "d": d,             # relative deadline
                "w": w,             # energy demand
                "preempt": pee      # preemptive / non-preemptive
            }
        unique_periods = len(set(task["p"] for task in task_set.values()))
        if check_workload_density(task_set) and check_job_count(task_set) and unique_periods >= 3: return {"periodic":task_set}
    

def check_workload_density(task_set):
    density = sum(task["e"] / task["p"] for task in task_set.values())
    print(f"density : {density}(>= 0.7)")
    return density >= 0.7

def check_job_count(task_set):
    total_jobs = sum(72 // task["p"] for task in task_set.values())
    print(f"total jobs : {total_jobs}(> 30)")
    return total_jobs > 30

def save_to_json(data, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"[Success] Task set successfully generated")



def main():
    task_data = generate_tasks()

    save_to_json(task_data, OUTPUT_FILE_PATH)


if __name__ == "__main__":
    main()