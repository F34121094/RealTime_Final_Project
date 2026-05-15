# 生成 Periodic Tasks 的邏輯
import json
import os
import random

OUTPUT_FILE_PATH = "output/task_set.json"

def generate_tasks():
    # n = num of tasks
    
    while(1):
        n = random.randint(6,10)
        task_set = {}
        for i in range(1, n + 1):       # 1-4
            # p = period
            if i == 1:
                p = random.randint(6,12)
            elif i == 2:
                p = random.randint(13,18)
            elif i == 3:
                p = random.randint(19,24)
            else:
                p = random.randint(6,24)
            # e = execution time
            # pee = preemptive (0 or 1)
            if i <= 2:
                e = 2
                pee = 0                 # 1-7
            elif i <= 3:
                e = random.randint(3,4)
                pee = random.choice([0, 1])
            else: 
                e = random.randint(1,4)
                pee = random.choice([0, 1])
            
            # d = relative deadline
            if i <= 2:
                d = e                   #1-6
            else:
                d = random.randint(e,p)
            
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
        if check_workload_density(task_set) and check_job_count(task_set): return task_set
    

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