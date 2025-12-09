#!/usr/bin/env python3
"""
Автоматическое развертывание Docker Monitor Service на сервере
"""

import subprocess
import sys
import time

SERVER_HOST = "212.193.54.178"
SERVER_USER = "root"
SERVER_PASS = "HAVw6-7K46B-8H2v9-Bis4g"
DEPLOY_DIR = "/opt/docker-monitor-service"

def run_ssh_command(command):
    """Выполнение команды на удаленном сервере через SSH"""
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"{SERVER_USER}@{SERVER_HOST}",
        command
    ]
    
    # Используем expect для автоматического ввода пароля
    expect_script = f"""
spawn {' '.join(ssh_cmd)}
expect {{
    "password:" {{
        send "{SERVER_PASS}\\r"
        exp_continue
    }}
    "yes/no" {{
        send "yes\\r"
        exp_continue
    }}
    eof
}}
"""
    
    try:
        result = subprocess.run(
            ["expect", "-c", expect_script],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Timeout"
    except FileNotFoundError:
        print("❌ expect не установлен. Используйте ручную установку.")
        return False, "", "expect not found"

def main():
    print("🚀 Автоматическое развертывание Docker Monitor Service")
    print("=" * 60)
    
    # Проверка expect
    try:
        subprocess.run(["which", "expect"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("❌ expect не установлен")
        print("Установите: sudo apt-get install expect (Linux) или brew install expect (macOS)")
        print("\nИли используйте ручную установку:")
        print(f"  ssh {SERVER_USER}@{SERVER_HOST}")
        print(f"  curl -sSL https://raw.githubusercontent.com/TTVLeaminem/docker-monitor-service/main/install-on-server.sh | bash")
        sys.exit(1)
    
    commands = [
        ("Проверка Docker", "docker --version || echo 'not_installed'"),
        ("Установка Docker (если нужно)", """
            if ! command -v docker &> /dev/null; then
                apt-get update && apt-get install -y ca-certificates curl gnupg lsb-release
                mkdir -p /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
                apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
                systemctl enable docker && systemctl start docker
            fi
        """),
        ("Клонирование репозитория", f"""
            mkdir -p {DEPLOY_DIR}
            cd {DEPLOY_DIR}
            if [ -d ".git" ]; then
                git pull
            else
                git clone https://github.com/TTVLeaminem/docker-monitor-service.git .
            fi
        """),
        ("Запуск установочного скрипта", f"cd {DEPLOY_DIR} && bash install-on-server.sh")
    ]
    
    for step_name, command in commands:
        print(f"\n📦 {step_name}...")
        success, stdout, stderr = run_ssh_command(command)
        
        if success:
            print(f"✅ {step_name} - успешно")
            if stdout:
                print(stdout)
        else:
            print(f"❌ {step_name} - ошибка")
            if stderr:
                print(stderr)
            if "not_installed" in stdout:
                continue  # Docker не установлен, продолжим установку
    
    print("\n" + "=" * 60)
    print("✅ Развертывание завершено!")
    print(f"\nПодключитесь к серверу для настройки:")
    print(f"  ssh {SERVER_USER}@{SERVER_HOST}")
    print(f"  cd {DEPLOY_DIR}")
    print(f"  nano .env  # Заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
    print(f"  docker compose up -d")

if __name__ == "__main__":
    main()

