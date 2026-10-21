"""Local-only interface simulator. Never connects to a payer or sends orders."""
from datetime import datetime
from pathlib import Path
import time
import tkinter as tk
from tkinter import messagebox

LOG_ROOT = Path(__file__).resolve().parent / 'test_app_logs'
RUN_INTERVAL_SECONDS = 5 * 60


def write_event(root, message, stamp=None, severity='INFO'):
    stamp = stamp or datetime.now()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{stamp:%Y%m%d}.log'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(f'{stamp:%m/%d/%Y %I:%M:%S %p} {severity:<7} HQ    {message}\n')
    return path


class TestInterface:
    def __init__(self, window):
        self.window = window
        self.busy = False
        self.next_run = time.monotonic() + RUN_INTERVAL_SECONDS
        self.pending = None
        self.outcome = tk.StringVar(value='Stable')
        window.title('GiroWatch TEST Interface')
        window.geometry('340x125')
        window.minsize(290, 110)
        menu = tk.Menu(window)
        actions = tk.Menu(menu, tearoff=False)
        actions.add_command(label='Run', command=self.run)
        actions.add_separator()
        actions.add_command(label='Exit', command=self.close)
        menu.add_cascade(label='Actions', menu=actions)
        outcomes = tk.Menu(menu, tearoff=False)
        for outcome in ('Stable', 'Warning', 'Error'):
            outcomes.add_radiobutton(label=outcome, variable=self.outcome, value=outcome)
        menu.add_cascade(label='Test outcome', menu=outcomes)
        window.config(menu=menu)
        self.display = tk.Label(window, background='#00ef24', foreground='#000000', font=('Segoe UI', 11))
        self.display.pack(fill='both', expand=True, padx=5, pady=(5, 0))
        tk.Label(window, text='SIMULATION · local logs only', font=('Segoe UI', 8)).pack(pady=3)
        window.protocol('WM_DELETE_WINDOW', self.close)
        self.tick()

    def log(self, message, severity='INFO'):
        try:
            write_event(LOG_ROOT, message, severity=severity)
        except OSError as error:
            self.busy = False
            messagebox.showerror('Cannot write test log', str(error))
            return False
        return True

    def run(self):
        if self.busy:
            return
        self.busy = True
        self.display.config(text='INTERFACE RUNNING!', background='#00ef24')
        outcome = self.outcome.get()
        from simulated_workload import build_live_run_events
        events = build_live_run_events(getattr(self, 'name', 'TEST Interface'), outcome,
                                  'TEST' + datetime.now().strftime('%Y%m%d%H%M%S%f'))
        def step(index=0):
            if not self.log(*events[index]):
                return
            if index + 1 < len(events):
                self.display.config(text=f'{getattr(self, "name", "TEST")} · processing {index+1}/{len(events)}')
                self.pending = self.window.after(300, lambda: step(index+1))
            else:
                self.pending = None
                self.busy = False
                self.next_run = time.monotonic() + RUN_INTERVAL_SECONDS
                self.display.config(background={'Stable':'#00ef24','Warning':'#ffd34d','Error':'#ff6b79'}[outcome])
        step()

    def tick(self):
        if not self.busy:
            seconds = max(0, int(self.next_run - time.monotonic()))
            self.display.config(text=f'TEST, waiting {seconds//60:02}:{seconds%60:02}')
            if time.monotonic() >= self.next_run:
                self.run()
        self.window.after(250, self.tick)

    def close(self):
        if self.pending:
            self.window.after_cancel(self.pending)
        self.window.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    TestInterface(root)
    root.mainloop()
