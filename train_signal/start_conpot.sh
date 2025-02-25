#!/bin/bash

LOG_FILE="/var/log/conpot_activation.log"
USED_NAMES_FILE="/tmp/conpot_used_names.txt"
BACKUP_DIR="/var/log/conpot_backups"  # 主機上的日誌備份目錄

# 初始化（以當前用戶身份創建文件）
sudo rm -f $USED_NAMES_FILE  # 清除舊文件
touch $USED_NAMES_FILE
chmod 666 $USED_NAMES_FILE   # 確保可寫
mkdir -p $BACKUP_DIR

while true; do
    # 獲取 attacker_ips 中的所有 IP
    ATTACKER_IPS=$(ipset list attacker_ips | grep -A 9999 "Members" | tail -n +2 | awk '{print $1}' | grep -v '^$')

    if [ -n "$ATTACKER_IPS" ]; then
        for IP in $ATTACKER_IPS; do
            CONPOT_NAME="conpot_$IP"
            CONPOT_NAME=$(echo $CONPOT_NAME | tr '.' '_')
            BACKUP_PATH="$BACKUP_DIR/$CONPOT_NAME"

            # 檢查容器是否已存在
            if ! docker ps -a --format '{{.Names}}' | grep -q "^$CONPOT_NAME$"; then
                echo "$(date) - 偵測到攻擊者 IP: $IP，啟動容器: $CONPOT_NAME" >> $LOG_FILE
                mkdir -p "$BACKUP_PATH"
                # 使用完整 Conpot 啟動命令
                docker run --name "$CONPOT_NAME" -v "$BACKUP_PATH":/conpot/data -d conpot_clean \
                    /home/conpot/.local/bin/conpot \
                    --template /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/templates/default/ \
                    --config /home/conpot/.local/lib/python3.6/site-packages/conpot-0.6.0-py3.6.egg/conpot/conpot.cfg
                if [ $? -eq 0 ]; then
                    echo "$CONPOT_NAME" >> $USED_NAMES_FILE
                fi
            else
                echo "$(date) - 容器 $CONPOT_NAME 已存在，跳過" >> $LOG_FILE
            fi
        done
    fi
    sleep 10
done
