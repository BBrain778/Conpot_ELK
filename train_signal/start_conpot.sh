#!/bin/bash

LOG_FILE="/var/log/conpot_activation.log"
USED_NAMES_FILE="/tmp/conpot_used_names.txt"
BACKUP_DIR="/var/log/conpot_backups"

sudo rm -f $USED_NAMES_FILE
touch $USED_NAMES_FILE
chmod 666 $USED_NAMES_FILE
mkdir -p $BACKUP_DIR

# 清空並設置異常檢測
sudo iptables -t nat -F PREROUTING
# 檢查 attacker_ips 是否存在，若不存在則創建
if ! sudo ipset list attacker_ips >/dev/null 2>&1; then
    sudo ipset create attacker_ips hash:ip
fi
sudo ipset flush attacker_ips  # 清空現有 IP
sudo iptables -t nat -I PREROUTING 1 -p tcp --dport 5020 -m recent --set --name MODBUS_ATTACK
sudo iptables -t nat -I PREROUTING 2 -p tcp --dport 5020 -m recent --update --seconds 10 --hitcount 5 --name MODBUS_ATTACK -j SET --add-set attacker_ips src

while true; do
    ATTACKER_IPS=$(ipset list attacker_ips | grep -A 9999 "Members" | tail -n +2 | awk '{print $1}' | grep -v '^$')

    if [ -n "$ATTACKER_IPS" ]; then
        for IP in $ATTACKER_IPS; do
            CONPOT_NAME="conpot_$IP"
            CONPOT_NAME=$(echo $CONPOT_NAME | tr '.' '_')
            BACKUP_PATH="$BACKUP_DIR/$CONPOT_NAME"

            if ! docker ps -a --format '{{.Names}}' | grep -q "^$CONPOT_NAME$"; then
                echo "$(date) - 偵測到攻擊者 IP: $IP，啟動容器: $CONPOT_NAME" >> $LOG_FILE
                mkdir -p "$BACKUP_PATH"
                PORT=5021
                while sudo netstat -tuln | grep -q ":$PORT "; do
                    PORT=$((PORT + 1))
                done
                docker run --name "$CONPOT_NAME" -v "$BACKUP_PATH":/conpot/data -p "$PORT:502" -p 161:161/udp -p 20000:20000 -d conpot_clean \
                    /home/conpot/.local/bin/conpot \
                    --template /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/templates/default/ \
                    --config /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/conpot.cfg
                if [ $? -eq 0 ]; then
                    echo "$CONPOT_NAME" >> $USED_NAMES_FILE
                    CONTAINER_IP=$(docker inspect -f '{{.NetworkSettings.IPAddress}}' "$CONPOT_NAME")
                    sudo iptables -t nat -I PREROUTING 3 -m set --match-set attacker_ips src -p tcp --dport 5020 -j DNAT --to-destination "$CONTAINER_IP:502"
                    sudo iptables -t nat -I PREROUTING 4 -m set --match-set attacker_ips src -p udp --dport 161 -j DNAT --to-destination "$CONTAINER_IP:161"
                    sudo iptables -t nat -I PREROUTING 5 -m set --match-set attacker_ips src -p tcp --dport 20000 -j DNAT --to-destination "$CONTAINER_IP:20000"
                else
                    echo "$(date) - 啟動容器 $CONPOT_NAME 失敗" >> $LOG_FILE
                fi
            else
                echo "$(date) - 容器 $CONPOT_NAME 已存在，跳過" >> $LOG_FILE
            fi
        done
    fi
    sleep 10
done
