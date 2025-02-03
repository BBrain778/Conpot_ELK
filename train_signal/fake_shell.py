import socket
import threading


HOST = '0.0.0.0'  # 監聽所有網卡
PORT = 10201  # Telnet 預設端口
FAKE_PROMPT = "root@siemens:~# "


def handle_client(client_socket):
    client_socket.sendall(FAKE_PROMPT.encode())
    while True:
        try:
            command = client_socket.recv(1024).decode().strip()
            if not command:
                break

            fake_response = fake_command_handler(command)
            client_socket.sendall(fake_response.encode() + b"\n" + FAKE_PROMPT.encode())

        except Exception as e:
            print(f"Client disconnected: {e}")
            break
    client_socket.close()


def fake_command_handler(command):
    """ 根據輸入的指令返回假回應 """
    fake_responses = {
        "ls": "bin  boot  dev  etc  home  lib  lost+found  media  mnt  opt  proc  root  run  sbin  srv  sys  tmp  usr  var",
        "pwd": "/root",
        "whoami": "root",
        "uname -a": "Linux siemens 5.4.0-91-generic #102-Ubuntu SMP x86_64 GNU/Linux",
        "cat /etc/passwd": "root:x:0:0:root:/root:/bin/bash\nuser:x:1000:1000:user:/home/user:/bin/bash",
        "exit": "logout"
    }

    return fake_responses.get(command, "bash: command not found: " + command)


def start_fake_shell():
    """ 啟動假的 Shell 服務 """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[*] Fake shell listening on {HOST}:{PORT}")

    while True:
        client_socket, addr = server.accept()
        print(f"[+] Accepted connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()


if __name__ == "__main__":
    start_fake_shell()
