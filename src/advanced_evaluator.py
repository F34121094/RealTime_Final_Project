import json
import os

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_advanced_evaluator():
    # Load all inputs
    processor_settings = load_json('input/processor_settings.json')
    price_72hr = load_json('input/price_72hr.json')
    tasks = load_json('input/aperiodic_n_sporadic.json')
    task_set = load_json('output/task_set.json')
    schedule = load_json('output/schedule_result.json')
    
    acceptance_log = {}
    if os.path.exists('output/acceptance_test_log.json'):
        acceptance_log = load_json('output/acceptance_test_log.json')
    
    # Process market prices
    market_prices = {item['hour']: item['market_price'] for item in price_72hr['price']}
    
    # Process generator costs
    gen_costs = {}
    for gen in processor_settings.get('generator', []):
        gen_costs[gen['generator_id']] = {
            'fixed': gen['cost_fixed'],
            'variable': gen['cost_variable']
        }
        
    # Extract jobs
    # Periodic jobs
    periodic_jobs = []
    periodic_tasks = task_set.get('periodic', {})
    for p_id, p_info in periodic_tasks.items():
        r = p_info['r']
        p = p_info['p']
        e = p_info['e']
        d = p_info['d']
        w = p_info['w']
        for k in range(72):
            rel_time = r + k * p
            if rel_time > 72:
                break
            abs_deadline = rel_time + d - 1
            periodic_jobs.append({
                'id': p_id,
                'instance_k': k,
                'r': rel_time,
                'd': abs_deadline,
                'e': e,
                'w': w,
                'type': 'periodic',
                'executed': 0,
                'completion_time': None
            })
            
    # Aperiodic jobs
    aperiodic_jobs = []
    aperiodic_tasks = tasks.get('aperiodic', {})
    for a_id, a_info in aperiodic_tasks.items():
        aperiodic_jobs.append({
            'id': a_id,
            'r': a_info['r'],
            'd': a_info['r'] + a_info['d'] - 1,
            'e': a_info['e'],
            'w': a_info['w'],
            'type': 'aperiodic',
            'executed': 0,
            'completion_time': None
        })
        
    # Sporadic jobs
    sporadic_jobs = []
    sporadic_tasks = tasks.get('sporadic', {})
    accepted_sporadics = set()
    for log in acceptance_log.get('acceptance_test_log', []):
        if log['status'] == 'Accepted':
            accepted_sporadics.add(log['job_id'])
            
    for s_id, s_info in sporadic_tasks.items():
        sporadic_jobs.append({
            'id': s_id,
            'r': s_info['r'],
            'd': s_info['r'] + s_info['d'] - 1,
            'e': s_info['e'],
            'w': s_info['w'],
            'type': 'sporadic',
            'accepted': s_id in accepted_sporadics,
            'executed': 0,
            'completion_time': None
        })
        
    all_jobs = periodic_jobs + aperiodic_jobs + sporadic_jobs
    
    # Analyze schedule
    generator_cost = 0.0
    market_revenue = 0.0
    
    ot_hours = set(range(12, 20)) | set(range(36, 44)) | set(range(60, 68))
    
    for step in schedule.get('schedule_result', []):
        t = step['t']
        
        # Calculate generator cost
        P = step.get('P', {})
        is_ot = t in ot_hours
        for g_id, g_cost in gen_costs.items():
            power = P.get(g_id, 0.0)
            if power > 0:
                fixed_cost = g_cost['fixed'] * 1.25 if is_ot else g_cost['fixed']
                generator_cost += fixed_cost + g_cost['variable'] * power
                
        # Calculate market revenue
        sell = step.get('sell', 0.0)
        contract_sell = step.get('contract_sell', sell) # Fallback to sell if contract_sell missing
        actual_price = step.get('actual_price', market_prices.get(t, 0.0))
        is_peak = step.get('is_peak_hour', False)
        
        gamma = 1.25 if is_peak else 1.0
        
        if sell >= contract_sell:
            revenue_t = actual_price * gamma * contract_sell + 0.7 * actual_price * gamma * (sell - contract_sell)
        else:
            revenue_t = actual_price * gamma * sell - 100 * (contract_sell - sell)
            
        market_revenue += revenue_t
        
        # Job execution
        k_alloc = step.get('k', {})
        for job_id, alloc in k_alloc.items():
            if job_id.endswith('_chg'):
                continue
                
            possible_jobs = [j for j in all_jobs if j['id'] == job_id and j['r'] <= t and j['executed'] < j['e']]
            if possible_jobs:
                possible_jobs.sort(key=lambda x: x['r'])
                target_job = possible_jobs[0]
                target_job['executed'] += 1
                if target_job['executed'] == target_job['e']:
                    target_job['completion_time'] = t

    # Metrics calculation
    # Hard deadline miss rate (periodic + accepted sporadic)
    hard_deadline_jobs = [j for j in all_jobs if j['type'] == 'periodic' or (j['type'] == 'sporadic' and j['accepted'])]
    hard_misses = 0
    for j in hard_deadline_jobs:
        if j['completion_time'] is None or j['completion_time'] > j['d']:
            hard_misses += 1
            if j['completion_time'] is None:
                j['completion_time'] = 72
    
    hard_deadline_miss_rate = hard_misses / len(hard_deadline_jobs) if hard_deadline_jobs else 0.0

    # Soft deadline miss rate (aperiodic)
    soft_deadline_jobs = [j for j in all_jobs if j['type'] == 'aperiodic']
    soft_misses = 0
    for j in soft_deadline_jobs:
        if j['completion_time'] is None or j['completion_time'] > j['d']:
            soft_misses += 1
            if j['completion_time'] is None:
                j['completion_time'] = 72
                
    soft_deadline_miss_rate = soft_misses / len(soft_deadline_jobs) if soft_deadline_jobs else 0.0
    missed_aperiodic_count = soft_misses

    # Tardiness and Response Time for ALL jobs (excluding rejected sporadic)
    eval_jobs = [j for j in all_jobs if not (j['type'] == 'sporadic' and not j['accepted'])]
    
    tardiness_list = [max(0, j['completion_time'] - j['d']) for j in eval_jobs]
    response_time_list = [j['completion_time'] - j['r'] for j in eval_jobs]

    avg_tardiness = sum(tardiness_list) / len(tardiness_list) if tardiness_list else 0.0
    max_tardiness = max(tardiness_list) if tardiness_list else 0

    avg_response_time = sum(response_time_list) / len(response_time_list) if response_time_list else 0.0
    max_response_time = max(response_time_list) if response_time_list else 0

    # Completion-time Jitter (for periodic tasks)
    jitter_list = []
    for p_id in periodic_tasks.keys():
        insts = [j for j in periodic_jobs if j['id'] == p_id]
        resps = [j['completion_time'] - j['r'] for j in insts if j['completion_time'] is not None]
        if resps:
            jitter_list.append(max(resps) - min(resps))
            
    completion_time_jitter = sum(jitter_list) / len(jitter_list) if jitter_list else 0.0

    # sporadic_value_rate
    sporadic_accepted_e = sum(j['e'] for j in sporadic_jobs if j['accepted'] and j['completion_time'] is not None and j['completion_time'] <= j['d'])
    sporadic_total_e = sum(j['e'] for j in sporadic_jobs)
    sporadic_value_rate = sporadic_accepted_e / sporadic_total_e if sporadic_total_e > 0 else 0.0

    # post_acceptance_violation_rate (Assume 0 for now)
    post_acceptance_violation_rate = 0.0

    objective_value = 10000 * missed_aperiodic_count + generator_cost - market_revenue

    # Output
    results = {
        "hard_deadline_miss_rate": round(hard_deadline_miss_rate, 4),
        "soft_deadline_miss_rate": round(soft_deadline_miss_rate, 4),
        "average_tardiness": round(avg_tardiness, 4),
        "max_tardiness": round(max_tardiness, 4),
        "average_response_time": round(avg_response_time, 4),
        "max_response_time": round(max_response_time, 4),
        "completion_time_jitter": round(completion_time_jitter, 4),
        "sporadic_value_rate": round(sporadic_value_rate, 4),
        "post_acceptance_violation_rate": round(post_acceptance_violation_rate, 4),
        "generator_cost": round(generator_cost, 4),
        "market_revenue": round(market_revenue, 4),
        "objective_value": round(objective_value, 4)
    }

    with open('output/evaluation_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4)

if __name__ == '__main__':
    run_advanced_evaluator()
