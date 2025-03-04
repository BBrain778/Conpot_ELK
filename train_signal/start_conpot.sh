#!/bin/bash
# 初始化設定
LOG_FILE="/var/log/conpot_activation.log"  # 存放腳本運行的日誌
USED_NAMES_FILE="/tmp/conpot_used_names.txt"  # 存放已啟動的 Conpot 容器名稱
BACKUP_DIR="/var/log/conpot_backups"  # 備份 Conpot 數據的目錄

# 初始化檔案和目錄
sudo rm -f "$USED_NAMES_FILE"
touch "$USED_NAMES_FILE"
chmod 666 "$USED_NAMES_FILE"
mkdir -p "$BACKUP_DIR"

# 清空 PREROUTING 鏈中的規則
sudo iptables -t nat -F PREROUTING

# 檢查並創建 attacker_ips ipset
if ! sudo ipset list attacker_ips >/dev/null 2>&1; then
    sudo ipset create attacker_ips hash:ip
fi
sudo ipset flush attacker_ips  # 清空現有 IP

# 設置 iptables 規則，檢測攻擊者
sudo iptables -t nat -I PREROUTING 1 -p tcp --dport 5020 -m recent --set --name MODBUS_ATTACK
sudo iptables -t nat -I PREROUTING 2 -p tcp --dport 5020 -m recent --update --seconds 10 --hitcount 5 --name MODBUS_ATTACK -j SET --add-set attacker_ips src

# 監控 ipset 攻擊者列表
while true; do
    ATTACKER_IPS=$(ipset list attacker_ips | grep -A 9999 "Members" | tail -n +2 | awk '{print $1}' | grep -v '^$')

    # 針對每個攻擊者 IP 啟動 Conpot 蜜罐
    if [ -n "$ATTACKER_IPS" ]; then
        for IP in $ATTACKER_IPS; do
            CONPOT_NAME="conpot_$IP"
            CONPOT_NAME=$(echo "$CONPOT_NAME" | tr '.' '_')
            BACKUP_PATH="$BACKUP_DIR/$CONPOT_NAME"

            # 檢查是否已啟動對應的 Conpot 容器
            if ! docker ps -a --format '{{.Names}}' | grep -q "^$CONPOT_NAME$"; then
                echo "$(date) - 偵測到攻擊者 IP: $IP，啟動容器: $CONPOT_NAME" >> "$LOG_FILE"
                mkdir -p "$BACKUP_PATH"

                # 動態分配 5020 端口
                PORT_5020=5020
                while sudo ss -tuln | grep -q ":$PORT_5020 "; do
                    PORT_5020=$((PORT_5020 + 1))
                done

                # 動態分配 161 端口 (UDP)
                PORT_161=161
                while sudo ss -tuln | grep -q ":$PORT_161 "; do
                    PORT_161=$((PORT_161 + 1))
                done

                # 動態分配 20000 端口
                PORT_20000=20000
                while sudo ss -tuln | grep -q ":$PORT_20000 "; do
                    PORT_20000=$((PORT_20000 + 1))
                done

                # 啟動容器
                docker run --name "$CONPOT_NAME" \
                    -v "$BACKUP_PATH":/conpot/data \
                    -p "$PORT_5020:5020" \
                    -p "$PORT_161:161/udp" \
                    -p "$PORT_20000:20000" \
                    -d conpot_clean \
                    /home/conpot/.local/bin/conpot \
                    --template /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/templates/default/ \
                    --config /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/conpot.cfg

                if [ $? -eq 0 ]; then
                    echo "$CONPOT_NAME" >> "$USED_NAMES_FILE"
                    echo "$(date) - 容器 $CONPOT_NAME 成功啟動，端口: 5020->$PORT_5020, 161->$PORT_161, 20000->$PORT_20000" >> "$LOG_FILE"

                    # 獲取容器 IP
                    CONTAINER_IP=$(docker inspect -f '{{.NetworkSettings.IPAddress}}' "$CONPOT_NAME")

                    # 設置 iptables 規則，將特定攻擊者 IP 的流量轉發至對應容器
                    sudo iptables -t nat -A PREROUTING -s "$IP" -p tcp --dport 5020 -j DNAT --to-destination "$CONTAINER_IP:5020"
                    sudo iptables -t nat -A PREROUTING -s "$IP" -p udp --dport 161 -j DNAT --to-destination "$CONTAINER_IP:161"
                    sudo iptables -t nat -A PREROUTING -s "$IP" -p tcp --dport 20000 -j DNAT --to-destination "$CONTAINER_IP:20000"
                else
                    echo "$(date) - 啟動容器 $CONPOT_NAME 失敗" >> "$LOG_FILE"
                fi
            else
                echo "$(date) - 容器 $CONPOT_NAME 已存在，跳過" >> "$LOG_FILE"
            fi
        done
    fi
    sleep 10
done
