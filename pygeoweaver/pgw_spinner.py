import time
import itertools
import threading
from IPython.display import display, clear_output

spinner_styles = {
    "dots": itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']),
    "line": itertools.cycle(['-', '/', '|', '\\']),
    "arrow": itertools.cycle(['←', '↖', '↑', '↗', '→', '↘', '↓', '↙']),
    "circle": itertools.cycle(['◐', '◓', '◑', '◒']),
    "bounce": itertools.cycle(['⠁', '⠂', '⠄', '⡀', '⢀', '⠠', '⠐', '⠈'])
}

class Spinner:
    def __init__(self, text="Loading...", style="circle", interval=0.1):
        self.text = text
        self.interval = interval
        self.spinner_cycle = spinner_styles.get(style, spinner_styles["dots"])
        self.stop_running = threading.Event()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while not self.stop_running.is_set():
            display(f"{next(self.spinner_cycle)} {self.text}", display_id='spinner')
            time.sleep(self.interval)
            clear_output(wait=True)

    def stop(self):
        self.stop_running.set()
        display(f"{self.text} Done!", display_id='spinner')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        
