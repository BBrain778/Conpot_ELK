import socket
import threading
import logging
import os

# 設定 Fake Shell 監聽的 IP 和 Port
HOST = "0.0.0.0"  # 監聽所有網卡
PORT = 10201  # Fake Shell 端口
FAKE_PROMPT = "root@siemens:~# "

# 設定 Log 檔案目錄
LOG_DIR = "/var/log/conpot"
LOG_FILE = f"{LOG_DIR}/fake_shell_commands.log"

# 確保 Log 目錄存在
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 設定 Log 記錄
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s"
)

def handle_client(client_socket, addr):
    """處理攻擊者的連線"""
    try:
        client_socket.sendall(FAKE_PROMPT.encode())

        while True:
            command = client_socket.recv(1024).decode().strip()
            if not command:
                continue  # 避免空輸入導致連線關閉

            # 記錄攻擊者輸入的指令
            log_message = f"[{addr[0]}:{addr[1]}] {command}"
            logging.info(log_message)  # 寫入 log 檔案
            print(log_message)  # 顯示在終端機

            # 產生 Fake Shell 回應
            fake_response = fake_command_handler(command)
            client_socket.sendall(fake_response.encode() + b"\n" + FAKE_PROMPT.encode())

            if command.lower() in ["exit", "logout"]:
                break  # 讓攻擊者以為真的登出

    except Exception as e:
        logging.error(f"Error handling client {addr}: {e}")
    finally:
        client_socket.close()

def fake_command_handler(command):
    """模擬 shell 回應"""
    fake_responses = {
        "ls": "bin  boot  dev  etc  home  lib  lost+found  media  mnt  opt  proc  root  run  sbin  srv  sys  tmp  usr  var",
        "pwd": "/root",
        "whoami": "root",
        "uname -a": "Linux siemens 5.4.0-91-generic #102-Ubuntu SMP x86_64 GNU/Linux",
        "cat /etc/passwd": "root:x:0:0:root:/root:/bin/bash\nuser:x:1000:1000:user:/home/user:/bin/bash",
        "exit": "logout"
    }
    return fake_responses.get(command, f"bash: command not found: {command}")

def start_fake_shell():
    """啟動假的 Shell 服務"""
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允許端口重用
        server.bind((HOST, PORT))
        server.listen(5)
        logging.info(f"[*] Fake shell listening on {HOST}:{PORT}")

        while True:
            client_socket, addr = server.accept()
            logging.info(f"[+] Accepted connection from {addr}")
            client_handler = threading.Thread(target=handle_client, args=(client_socket, addr))
            client_handler.start()

    except Exception as e:
        logging.error(f"Fake Shell crashed: {e}")

if __name__ == "__main__":
    start_fake_shell()
