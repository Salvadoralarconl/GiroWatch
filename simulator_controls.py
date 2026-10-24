"""Controls only child simulators created by this test session."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

TEST_APPS = ('TEST CAM', 'TEST UNITELLER', 'TEST INTERBANK', 'TEST UNITRANSFER')


class SimulatorControls:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.processes = {}
        self.lock = threading.Lock()

    def _wait_for_window(self, name, process, folder):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError(f'{name} could not open. See {folder / "startup.log"} for details.')
            if (folder / 'display.json').exists():
                return
            time.sleep(0.05)
        process.terminate()
        process.wait(timeout=5)
        raise ValueError(f'{name} did not open within 5 seconds. See {folder / "startup.log"} for details.')

    def action(self, payload):
        name, action = payload.get('application'), payload.get('action')
        if name not in TEST_APPS or action not in ('run', 'restart'):
            raise ValueError('Local test mode: only the named TEST simulators can be run or restarted.')
        with self.lock:
            folder = self.root / name
            folder.mkdir(parents=True, exist_ok=True)
            process = self.processes.get(name)
            if action == 'restart':
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                for file in ('run.request', 'display.json'):
                    (folder / file).unlink(missing_ok=True)
                script = Path(__file__).resolve().with_name('test_simulator.py')
                # A Windows venv executable is a redirector: terminate must target
                # the actual interpreter that owns the Tk window.
                executable = getattr(sys, '_base_executable', sys.executable) if sys.platform == 'win32' else sys.executable
                with (folder / 'startup.log').open('w', encoding='utf-8') as log:
                    process = subprocess.Popen(
                        [executable, str(script), '--name', name, '--root', str(self.root)],
                        stdout=log, stderr=log,
                        cwd=script.parent, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.processes[name] = process
                self._wait_for_window(name, process, folder)
            elif process is None or process.poll() is not None:
                raise ValueError('Test application is closed. Use Restart to open it.')
            else:
                (folder / 'run.request').write_text('run', encoding='utf-8')
        return {'ok': True, 'simulation': True}

    def status(self, name):
        process = self.processes.get(name)
        running = process is not None and process.poll() is None
        data = {}
        if running:
            try:
                data = json.loads((self.root / name / 'display.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        if time.time() - data.get('sampled_at', 0) > 3:
            data = {'live_timer_state': 'unavailable', 'next_run_at': None}
        return {**data, 'process_running': running, 'control_available': True}

    def close(self):
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
