import typer
import subprocess
import sys
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = typer.Typer()

class BotRestartHandler(FileSystemEventHandler):
    def __init__(self, script, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.script = script
        self.process = None
        self.start_bot()

    def start_bot(self):
        if self.process:
            self.process.kill()
        self.process = subprocess.Popen([sys.executable, '-m', self.script], 
                                        env=os.environ.copy())

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f'Change detected in {event.src_path}. Reloading bot...')
            self.start_bot()

@app.command()
def run(reload: bool = typer.Option(False, "--reload", help="Enable hot-reloading.")):
    """Runs the bot."""
    if reload:
        path = 'Bot'
        print(f'Watching for changes in: {path}')
        event_handler = BotRestartHandler('Bot')
        observer = Observer()
        observer.schedule(event_handler, path, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        import runpy
        runpy.run_module("Bot", run_name="__main__")

if __name__ == "__main__":
    app()