"""Bot service wrapper — auto-restart on crash, log rotation."""
import subprocess, sys, os, time, datetime

PROJECT = os.environ.get("NOVA_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = f"{PROJECT}/logs"
PYTHON = sys.executable
BOT_SCRIPT = f"{PROJECT}/scripts/telegram_automation.py"
MAX_RESTARTS = 50
RESTART_DELAY = 10

os.makedirs(LOGS_DIR, exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(f"{LOGS_DIR}/service.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def get_log_file():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    return open(f"{LOGS_DIR}/bot_{date}.log", "a", encoding="utf-8")

def run():
    restarts = 0
    while restarts < MAX_RESTARTS:
        log_file = get_log_file()
        log(f"Starting bot (restart #{restarts})...")

        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                [PYTHON, "-u", BOT_SCRIPT],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=PROJECT,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            proc.wait()
            exit_code = proc.returncode
            log(f"Bot exited with code {exit_code}")
        except Exception as e:
            log(f"Bot crash: {e}")
            exit_code = 1
        finally:
            log_file.close()

        restarts += 1
        if restarts < MAX_RESTARTS:
            log(f"Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)

    log(f"Max restarts ({MAX_RESTARTS}) reached. Service stopping.")

if __name__ == "__main__":
    log("=== Bot Service Started ===")
    run()
    log("=== Bot Service Stopped ===")
