# GiroWatch

A local Windows dashboard for monitoring application logs, reviewing incidents,
searching complete order histories, and managing application profiles.

## Requirements

- Windows with Python 3.12 and Tkinter installed.
- Node.js is optional, for the JavaScript tests.
- Windows PowerShell is used by optional desktop application controls.

## Install

From PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Start with the included test applications

```powershell
.\.venv\Scripts\python.exe web_app.py --local-test --test-windows
```

Open <http://127.0.0.1:8765>. Four fictional desktop applications are included:
TEST CAM, TEST UNITELLER, TEST INTERBANK, and TEST UNITRANSFER. They generate
local simulated logs, waiting countdowns, and occasional simulated failures.
Their Run and Restart actions target only simulators created by this test session.

Local test mode uses temporary data, blocks production configuration routes,
and does not load production log folders, contacts, or application controls.
Automatic scanning starts paused. Use Settings to resume and choose a quiet
period of 1, 10, 20, or 30 seconds. Closing the server discards this test session.
Omit `--test-windows` to explore sample data without opening desktop simulators.

Press Ctrl+C in the server terminal to stop it. Do not start multiple copies
on the same port. Use `--port 8766` for a separate port if needed.

The smaller standalone simulator can also be opened with `Start Test App.cmd`.
It writes only simulated logs under `test_app_logs/`.

## Features

- Home dashboard with health scores, seven-day run counts, and incidents.
- Monitoring ordered by error, warning, then stable, with alphabetical ties.
- Per-application Scan, Logs, Run, and Restart actions.
- Live countdowns and animated processing indicators for connected applications.
- Run/order grouping profiles and configurable error rules.
- Date-filtered order search, contacts, appearance, display size, and notifications.

## Regular mode

```powershell
.\.venv\Scripts\python.exe web_app.py
```

Regular mode reads locally configured profiles. Company profiles, log files,
contacts, application executable paths, and saved runtime state are intentionally
excluded from this repository. Configure your own sources in the application.
For testing, use isolated local test mode instead of connecting live applications.

Desktop controls execute on the machine and Windows session hosting GiroWatch.
Opening an executable from a shared drive runs it on that host, not on the file
server. Run invokes an existing named menu command using Windows accessibility.
Restart requests a normal close, waits for exit, then opens the saved executable.
It does not force-kill the target or modify its executable/configuration.

The web server binds to localhost only. Authentication and remote hosting are
not configured; do not expose it to a network as-is.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
Get-ChildItem tests/js/*.cjs | ForEach-Object { node $_.FullName }
```

The test suite uses fictional fixtures and temporary directories. Live company
logs, credentials, and customer records should never be committed.
