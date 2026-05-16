# 排程主程式入口
"""
傳統機組的參數說明 (generator):
generator_id        編號
output_min          最小出力
output_max          最大出力
ramp_up_rate        一個時間間隔 出力可增加的幅度
ramp_down_rate      一個時間間隔 出力可減少的幅度
min_up_time         最短開啟時間
min_down_time       最長開啟時間
cost_fixed          每小時的固定成本
cost_variable       發出 1 MWh 的 成本
initial_on_time     排程前機組已經連續開機的時間 
initial_off_time    排程前機組已經連續關機的時間
initial_energy      機組在 t = 0 時可供應的電量

再生能源參數說明 (renewable_capacity)
renewable_id        單一再生能源的編號
capacity            再生能源的最大出力

再生能源預測參數說明 (renewable_forecast)
hour                預測發生的時段
pv_forecast         太陽能預測出力百分比

儲能設備參數說明 (storage)
storage_id          編號
soc_min             必須保留的最低電能量
soc_max             可以儲存的最高電能量
discharge_max       最大放電功率
charge_max          最大充電功率
soc_init            初始存量
"""
