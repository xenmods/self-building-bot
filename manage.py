import os
import signal
import subprocess
import sys
import threading
import time
import typer
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

app = typer.Typer()


class BotProcessManager(FileSystemEventHandler):
    def __init__(self, script: str = "Bot"):
        super().__init__()
        self.script = script
        self.process = None
        self.running = True
        self.user_stopped = False
        self._lock = threading.Lock()
        self.start_bot()

    def start_bot(self):
        with self._lock:
            self.stop_bot()
            env = os.environ.copy()
            env["JARVIS_MANAGED"] = "1"
            # Launch child process attached cleanly
            self.process = subprocess.Popen(
                [sys.executable, "-m", self.script],
                env=env
            )

    def stop_bot(self):
        if self.process:
            try:
                if self.process.poll() is None:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            self.process = None
            # Allow OS file handles (e.g. SQLite database session locks) to release
            time.sleep(0.4)

    def on_modified(self, event):
        if not self.running or self.user_stopped:
            return
        if event.src_path.endswith(".py"):
            print(f"\n[HOT-RELOAD] Change detected in {event.src_path}. Reloading bot...")
            self.start_bot()


def start_interactive_quit_listener(manager: BotProcessManager, observer: Observer = None):
    """Background thread that listens for 'q', 'quit', 'exit', 'r', 'reload' from stdin."""
    def _listener():
        while manager.running and not manager.user_stopped:
            try:
                user_input = sys.stdin.readline()
                if not user_input:
                    time.sleep(0.2)
                    continue
                cmd = user_input.strip().lower()
                if cmd in ("q", "quit", "exit"):
                    print("\n[*] 'q' received. Terminating J.A.R.V.I.S. and stopping runner...")
                    manager.user_stopped = True
                    manager.running = False
                    manager.stop_bot()
                    if observer:
                        try:
                            observer.stop()
                        except Exception:
                            pass
                    # Force clean exit
                    os._exit(0)
                elif cmd in ("r", "reload", "restart"):
                    print("\n[*] Manual reload command received. Restarting bot...")
                    manager.start_bot()
            except Exception:
                break

    t = threading.Thread(target=_listener, daemon=True)
    t.start()
    return t


@app.command()
def run(reload: bool = typer.Option(False, "--reload", help="Enable hot-reloading.")):
    """Runs the bot with interactive 'q' key to quit and clean Ctrl+C handling."""
    print("=" * 60)
    print("  ⚡ J.A.R.V.I.S. Self-Building Bot Runner")
    print("  👉 Type 'q' + Enter or press Ctrl+C to stop the bot cleanly.")
    print("  👉 Type 'r' + Enter to manually reload the bot.")
    print("=" * 60)

    manager = BotProcessManager("Bot")
    observer = None

    if reload:
        path = "Bot"
        print(f"[*] Hot-reloader active. Watching for code changes in: {path}/")
        observer = Observer()
        observer.schedule(manager, path, recursive=True)
        observer.start()

    start_interactive_quit_listener(manager, observer)

    try:
        while manager.running and not manager.user_stopped:
            if manager.process:
                ret = manager.process.poll()
                # If child process exited but user did NOT request stop, auto-restart child
                if ret is not None and manager.running and not manager.user_stopped:
                    print(f"\n[⚡ SUPERVISOR] Bot process exited (code {ret}). Reloading core process...")
                    time.sleep(1.0)
                    if manager.running and not manager.user_stopped:
                        manager.start_bot()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[*] Ctrl+C received. Shutting down...")
    finally:
        manager.user_stopped = True
        manager.running = False
        manager.stop_bot()
        if observer:
            try:
                observer.stop()
                observer.join(timeout=2)
            except Exception:
                pass
        print("[*] Bot stopped cleanly.")


if __name__ == "__main__":
    app()
