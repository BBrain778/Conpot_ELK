import json
import time
import datetime

# 設定日誌檔案路徑
LOG_FILE = "/home/bbrain/conpot_logs/conpot.json"
ANOMALY_LOG = "/home/bbrain/conpot_logs/anomalies.log"

# 設定平交道控制器資訊
TARGET_SLAVE_ID = 4  # 平交道控制器的 Modbus Slave ID
TARGET_COIL_ADDRESS = 3  # 監控的 Modbus 線圈位址
MODBUS_FUNCTION_CODES = [5, 6, 15, 16]  # 5/6: 寫單一線圈/寄存器, 15/16: 寫多個線圈/寄存器

# 設定不可操作時段 (09:00 - 12:00)
FORBIDDEN_HOURS = range(9, 12)

def log_anomaly(event):
    """ 將異常事件寫入日誌 """
    with open(ANOMALY_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")

def monitor_conpot_logs():
    """ 監測 Conpot JSON 日誌檔案，檢測異常行為 """
    print("[*] 平交道控制器異常偵測啟動，監測 Modbus 交通...")

    with open(LOG_FILE, "r") as log_file:
        log_file.seek(0, 2)  # 移動到檔案末尾，監測新增的記錄

        while True:
            line = log_file.readline()
            if not line:
                time.sleep(1)
                continue

            try:
                log_entry = json.loads(line.strip())

                # **確保是 Modbus 交通事件**
                if log_entry.get("event_type") == "MODBUS_TRAFFIC":
                    timestamp = log_entry.get("timestamp", "")
                    function_code = log_entry.get("function_code", -1)
                    slave_id = log_entry.get("slave_id", -1)
                    src_ip = log_entry.get("src_ip", "Unknown")
                    src_port = log_entry.get("src_port", -1)
                    dst_ip = log_entry.get("dst_ip", "Unknown")
                    dst_port = log_entry.get("dst_port", -1)
                    request = log_entry.get("request", "")

                    # **解析時間**
                    if timestamp:
                        log_time = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                        hour_now = log_time.hour

                        # **檢查是否為禁止時段**
                        if hour_now in FORBIDDEN_HOURS:
                            # **檢查是否對 `slave_id=4` 的 `function_code=5,6,15,16` 進行操作**
                            if slave_id == TARGET_SLAVE_ID and function_code in MODBUS_FUNCTION_CODES:
                                alert = {
                                    "timestamp": timestamp,
                                    "src_ip": src_ip,
                                    "src_port": src_port,
                                    "dst_ip": dst_ip,
                                    "dst_port": dst_port,
                                    "slave_id": slave_id,
                                    "function_code": function_code,
                                    "request": request,
                                    "alert": "🚨 非法修改平交道控制器數值！🚨"
                                }
                                log_anomaly(alert)
                                print(f"[ALERT] {alert}")

            except json.JSONDecodeError:
                print("[!] JSON 解碼錯誤，忽略該行")

if __name__ == "__main__":
    monitor_conpot_logs()
