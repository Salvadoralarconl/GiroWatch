"""Server-style desktop TEST application. No network or production app imports."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import time
import tkinter as tk

from simulator_controls import TEST_APPS
from test_interface import TestInterface, write_event


def scheduled_outcome(root, name, stamp=None):
    """Share one fault budget across all four simulators, including restarts."""
    stamp = time.time() if stamp is None else stamp
    lock = root / 'fault-schedule.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        return 'Stable'
    try:
        path = root / 'fault-schedule.json'
        schedule = json.loads(path.read_text()) if path.exists() else {'next_due': stamp+600, 'next_app': 0}
        outcome = 'Stable'
        if stamp >= schedule['next_due'] and name == TEST_APPS[schedule['next_app']]:
            outcome = 'Error'
            schedule = {'next_due': stamp+600, 'next_app': (schedule['next_app']+1) % len(TEST_APPS)}
        path.write_text(json.dumps(schedule), encoding='utf-8')
        return outcome
    finally:
        lock.rmdir()


class ServerTestInterface(TestInterface):
    def __init__(self, window, name, folder):
        self.name, self.folder = name, folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.cycle = TEST_APPS.index(name) * 3
        super().__init__(window)
        window.title(f'{name} - INTERFACE (LOCAL SIMULATION)')
        index = TEST_APPS.index(name)
        window.geometry(f'340x125+{100+(index % 2)*370}+{100+(index // 2)*180}')
        self.outcome.set('Stable')

    def run(self):
        if self.busy:
            return
        self.outcome.set(scheduled_outcome(self.folder.parent, self.name))
        self.cycle += 1
        super().run()

    def log(self, message, severity='INFO'):
        write_event(self.folder / 'logs', message, severity=severity)
        return True

    def tick(self):
        if not self.busy:
            seconds = max(0, int(self.next_run - time.monotonic()))
            self.display.config(text=f'{self.name}, waiting {seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}')
            if time.monotonic() >= self.next_run:
                self.run()
        request = self.folder / 'run.request'
        if request.exists():
            request.unlink()
            self.run()
        data = {'live_timer_state': 'running' if self.busy else 'waiting',
                'sampled_at': time.time(),
                'next_run_at': None if self.busy else (datetime.now().astimezone()+timedelta(seconds=max(0,self.next_run-time.monotonic()))).isoformat()}
        temporary = self.folder / 'display.tmp'
        try:
            temporary.write_text(json.dumps(data), encoding='utf-8')
            temporary.replace(self.folder / 'display.json')
        except OSError:
            # Windows readers can briefly prevent replacement. Retry next tick.
            pass
        finally:
            self.window.after(250, self.tick)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', choices=TEST_APPS, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    window = tk.Tk()
    ServerTestInterface(window, args.name, args.root / args.name)
    window.mainloop()
