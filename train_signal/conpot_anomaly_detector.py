import json
import time
import datetime

# 設定日誌檔案路徑
LOG_FILE = "/home/bbrain/conpot_logs/conpot.json"
ANOMALY_LOG = "/home/bbrain/conpot_logs/anomalies.log"

# 設備設定
DEVICES = {
    3: {  # 火車信號燈控制
        "red_light": 1,
        "green_light": 2,
        "description": "火車信號燈"
    },
    4: {  # 平交道控制器
        "barrier": 3,
        "description": "平交道控制器"
    },
    5: {  # 道岔控制器
        "switch": 4,
        "description": "道岔控制器"
    }
}

MODBUS_FUNCTION_CODES = [5, 6, 15, 16]  # 允許寫入的 Modbus function codes
FORBIDDEN_HOURS = range(7, 13)  # 不可操作時段（09:00-12:00）
FREQUENCY_LIMIT = 5  # 設定異常變更頻率閾值
recent_events = []  # 用於監測頻繁變更

def log_anomaly(event):
    """ 記錄異常事件 """
    with open(ANOMALY_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")

def is_frequent_change(slave_id, timestamp):
    """ 判斷短時間內是否頻繁變更 """
    global recent_events
    # 刪除 10 秒之前的事件
    recent_events = [e for e in recent_events if (timestamp - e["time"]).seconds < 10]
    # 新增當前事件
    recent_events.append({"slave": slave_id, "time": timestamp})
    return sum(1 for e in recent_events if e["slave"] == slave_id) > FREQUENCY_LIMIT

    print(f"Checking frequent changes for slave {slave_id} at {timestamp}")
    print(f"Recent events: {recent_events}")
    
    # 計算 10 秒內的變更次數
    return sum(1 for e in recent_events if e["slave"] == slave_id) > FREQUENCY_LIMIT

def monitor_conpot_logs():
    """ 監測 Conpot 日誌，偵測異常行為 """
    print("[*] Modbus 交通異常偵測啟動...")
    
    with open(LOG_FILE, "r") as log_file:
        log_file.seek(0, 2)  # 移動到檔案末尾，監測新增記錄

        while True:
            line = log_file.readline()
            if not line:
                time.sleep(1)
                continue
            
            try:
                log_entry = json.loads(line.strip())
                if log_entry.get("event_type") != "MODBUS_TRAFFIC":
                    continue
                
                timestamp = datetime.datetime.strptime(log_entry["timestamp"], "%Y-%m-%d %H:%M:%S")
                function_code = log_entry["function_code"]
                slave_id = log_entry["slave_id"]
                request = log_entry.get("request", "")
                
                # **火車信號燈異常檢測**
                if slave_id == 3:
                    if timestamp.hour in FORBIDDEN_HOURS and function_code in MODBUS_FUNCTION_CODES:
                        log_anomaly({
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert": " Modification of Train signal lights during prohibited periods"
                        })
                        print(f"[ALERT] Modification of Train signal lights during prohibited periods！time: {timestamp}")
                
                # **平交道控制器異常檢測**
                if slave_id == 4:
                    if timestamp.hour in FORBIDDEN_HOURS and function_code in MODBUS_FUNCTION_CODES:
                        log_anomaly({
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert": " Modification of level crossing gates during prohibited periods"
                        })
                        print(f"[ALERT] Modification of level crossing gates during prohibited periods！time: {timestamp}")
                    if is_frequent_change(slave_id, timestamp):
                        log_anomaly({
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert": " Frequent opening and closing of level crossing gates in a short period of time"
                        })
                        print(f"[ALERT] Frequent opening and closing of level crossing gates in a short period of time！time: {timestamp}")
                
                # **道岔控制器異常檢測**
                if slave_id == 5:
                    if timestamp.hour in FORBIDDEN_HOURS and function_code in MODBUS_FUNCTION_CODES:
                        log_anomaly({
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert": " Modification of rail-switch during prohibited periods"
                        })
                        print(f"[ALERT] Modification of rail-switch during prohibited periods！time: {timestamp}")
                    if is_frequent_change(slave_id, timestamp):
                        log_anomaly({
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert": " Frequent switch rail-switch in a short period of time！"
                        })
                        print(f"[ALERT] Frequent switch rail-switch in a short period of time！time: {timestamp}")
            
            except json.JSONDecodeError:
                print("[!] JSON 解碼錯誤，忽略該行")

if __name__ == "__main__":
    monitor_conpot_logs()
