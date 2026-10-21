# GiroWatch

**A local Windows dashboard that turns application logs into a clearer view of runs, orders, and incidents.**

GiroWatch combines lightweight machine-learning models, configurable error rules,
and Windows application integration to help operators monitor multiple processing
interfaces from one place. Four fictional desktop applications are included for
testing the workflow without connecting to live business systems.

## Why GiroWatch was created

Monitoring multiple desktop processing applications often means watching a wall
of separate windows, opening daily log files, and searching repeated messages to
understand what happened. Each application can use a different log format, and
one order can appear in several processing cycles.

A green application window or a completed cycle does not necessarily mean every
order succeeded. Likewise, a line containing `Success (OK)` can contain a response
payload that reports a business failure. Operators need the surrounding context,
not just a matching word or an isolated error line.

GiroWatch was created to reduce that manual investigation. Its goals are to:

- Bring application health and incidents into one dashboard.
- Separate long log files into processing runs and individual order occurrences.
- Preserve the context needed to investigate repeated attempts and failures.
- Adapt to different applications through labeled examples and configuration.
- Show live activity separately from the last assessed log result.
- Offer optional access to existing application Run and Restart controls.
- Keep log processing local, without requiring a cloud AI service.

GiroWatch supports monitoring and investigation. It does not replace the source
applications, their transaction systems, or their developers' diagnostics.

## Features

| Area | What it provides |
| --- | --- |
| Home | System health, seven days of completed-run counts, active incidents, and today's error log. |
| Monitoring | Application rows prioritized by Error, Warning, then Stable, with alphabetical ordering within each group. |
| Live activity | Countdown badges and animated status rings for connected applications. |
| Order search | Date-filtered searches returning complete grouped order occurrences and their original log context. |
| Incident review | Severity, active/resolved status, supporting logs, and configurable explanatory messages. |
| Configuration | Per-application error rules, run grouping, order grouping, log folders, and application controls. |
| Actions | Individual Scan, Logs, Run, and Restart actions where supported and configured. |
| Contacts | Application-specific support and payer contact information stored locally. |
| Settings | Automatic scanning, quiet periods, in-app notifications, light/dark/system themes, and 80%/100%/120% display sizes. |

## Machine learning: how it works

GiroWatch uses **machine-learning models (ML models)** implemented with
**scikit-learn**. These are lightweight supervised text classifiers, not large
language models, masked language models, or generative chatbots. They run on the
CPU and do not require a GPU, AI API key, or external model provider.

### Application-specific labeled examples

An operator provides representative messages and labels through Configuration.
Run profiles use:

```text
Run_Start  -> a message beginning a processing cycle
Run_End    -> a message completing a processing cycle
Other      -> ordinary messages inside or around a cycle
```

Order profiles separately use `Order_Start`, `Order_End`, and `Other` to identify
individual order activity within a run. Classifiers predict boundary labels;
deterministic grouping logic then builds the run/order groups. Original log
lines remain available for investigation.

For example, a fictional run profile could contain:

| Training message | Label |
| --- | --- |
| `BEGIN PROCESS` | Run_Start |
| `LOGIN OK` | Other |
| `SENDING ORDERS` | Other |
| `END PROCESS` | Run_End |

Each application can have its own examples and selected order classifier rather
than forcing every log format through one shared profile.

### Supported models

| Task / option | Implementation | Role |
| --- | --- | --- |
| Run grouping | CountVectorizer + Multinomial Naive Bayes | Classify run boundaries and ordinary lines. |
| Order grouping: Word-pair Naive Bayes | Word and word-pair counts + Multinomial Naive Bayes | Identify order boundaries using familiar message patterns. |
| Order grouping: Nearest example | TF-IDF + one-nearest-neighbor with cosine distance | Use the label of the most similar training example. |
| Order grouping: Linear SVM | TF-IDF + LinearSVC | An alternative classifier for comparison on an application's examples. |

Timestamp prefixes are removed before classification. Order-message cleaning
also removes supported order-ID patterns to reduce dependence on a particular
transaction identifier. The original text is retained in the grouped results.

The selected order model is saved with the application's profile. Models are
trained from saved examples when needed; some runtime paths cache them for reuse.
Profiles store examples and settings, not a continually learning neural network.

### Error detection is rule-based

After grouping, explicit text-match rules determine **Warning**, **Critical**, or
**Ignore** findings. Critical findings appear as errors in the UI. Rules can
include a display message, troubleshooting notes, and case-sensitive matching.

**ML identifies log structure; configured rules identify the errors.** GiroWatch
does not independently understand every payer response or guarantee that an order
was accepted, paid, or settled.

### How results improve

Better, more representative labeled examples can improve grouping for that
application. Adding another application does not automatically improve the
existing classifiers. There is no automatic training from every scan.

Changed log formats, unfamiliar messages, and new business response codes need
review and profile updates. No universal accuracy percentage is claimed: validate
each application against representative logs before relying on its results.

## How monitoring works

1. **Locate the source:** use the saved folder profile to identify dated
   `YYYYMMDD.log` files, including weekday subfolders when configured.
2. **Watch for changes:** inspect file metadata without reading content on every
   check.
3. **Wait for readiness:** automatic scanning currently waits for a connected
   application's waiting state and the selected quiet period: 1, 10, 20, or
   30 seconds. Without a readable waiting state, use manual Scan.
4. **Read updates:** incremental readers retain offsets and partial-line buffers
   and handle file rotation/replacement. Source handles close before ML analysis.
5. **Group and assess:** application examples identify boundaries, then configured
   rules assess findings and update incident state.
6. **Display results:** the browser polls status and shows health, incidents, and
   supported live application activity.

Live countdowns are read from supported application displays, not predicted from
historical run intervals. A running process, an active processing cycle, a
completed cycle, and a successful order are different facts.

System health averages application scores: Stable = 100%, Warning = 50%, and
Error = 0%. Unknown applications currently contribute zero to this calculation.
The overall health label follows score thresholds; incident counts separately
show unresolved findings.

## Quick start with the test applications

### Requirements

- Windows with **Python 3.12**, including Tkinter.
- Git to clone and synchronize the repository.
- Windows PowerShell for optional real desktop integration.
- Node.js only for the JavaScript tests.

### Install

Run these commands separately in PowerShell or Command Prompt:

```powershell
git clone https://github.com/Salvadoralarconl/GiroWatch.git
cd GiroWatch
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Start isolated test mode

```powershell
.\.venv\Scripts\python.exe web_app.py --local-test --test-windows
```

Open **http://127.0.0.1:8765** and keep the terminal open.

Four fictional interfaces open: **TEST CAM**, **TEST UNITELLER**, **TEST INTERBANK**,
and **TEST UNITRANSFER**. Each has its own simulated log source, processing cycles,
and waiting countdown. The simulators generate fictional order activity and
occasional failures; they do not send real orders.

Local test mode uses temporary data, does not load production profiles or
contacts, and blocks production configuration routes. Run and Restart target
only simulators owned by that session. Closing the server discards the temporary
session. This mode is for demonstration and development, not permanent profile
editing.

### Try the workflow

1. Open **Monitoring** and select **Actions -> Run** on a test app.
2. Watch its countdown become **Running** and its status indicator animate.
3. In **Settings**, select a quiet period and resume automatic scanning.
4. After processing finishes, check its assessment and completed-run count.
5. Open **Actions -> Logs** to inspect the original simulated messages.
6. Try **Restart**, or search a fictional order ID copied from the logs.

Press **Ctrl+C** in the server terminal to stop. Do not start multiple copies on
the same port. Add `--port 8766` if you need a separate port.

Omit `--test-windows` to browse fictional data without opening desktop windows.
The smaller standalone simulator is also available through `Start Test App.cmd`;
it writes simulated logs under `test_app_logs/`.

## Configure your own applications

```powershell
.\.venv\Scripts\python.exe web_app.py
```

Regular mode reads locally saved profiles. Live company profiles, log files,
contacts, executable paths, and runtime state are excluded from this repository.
Some generic run examples are bundled, but a fresh clone is not a configured
live installation.

| Configuration tab | What you supply |
| --- | --- |
| Errors | Match phrases/codes, severity, display messages, and optional notes. |
| Run Grouping | Labeled Run_Start, Run_End, and Other examples. |
| Order Grouping | Labeled Order_Start, Order_End, and Other examples, plus a classifier. |
| Log Folders | Root log folder and whether to include subfolders. |
| Application controls | Executable, working folder, process name, window title, menu/command names, and close timeout. |

The configuration Test workflow evaluates saved profiles against uploaded logs
or a configured source. It exports grouped runs, grouped orders, and profile JSON
for review without replacing the live monitoring state.

### External Windows controls

GiroWatch uses a PowerShell helper and a small C# Windows accessibility adapter:

- **Run** finds the configured existing menu command and invokes it by name.
- **Restart** requests a normal close, waits for process exit, then opens the saved
  executable in its working folder. Real-application controls do not force-kill
  the target. Fictional simulators use separate test-session process controls.
- **Live timer** reads a supported waiting/running display from the application.

Compatibility depends on the target's accessibility support. The current adapter
expects a Windows Forms menu and supported display text; this is not a universal
controller for every Windows program.

Controls run on the machine and Windows session hosting GiroWatch. Opening an
executable from a shared drive runs it on that machine, not on the file server.
To operate a server's visible apps, GiroWatch must run in the appropriate logged-in
server session. A remote control agent is not included.

These integrations do not modify the target application's source, executable,
or configuration. However, Run can trigger its real business processing. Use
fictional test mode for development.

## Architecture

The backend uses Python's standard-library HTTP server and JSON persistence.
The frontend uses HTML, CSS, and JavaScript with no build step. scikit-learn
provides the vectorizers and classifiers.

| Component | Responsibility |
| --- | --- |
| `web/design.html`, `web/design.css`, `web/design.js` | UI, settings, log dialogs, and configuration editors. |
| `web_app.py` | Local server and API routes. |
| `web_service.py` | Profiles, contacts, configuration, and service coordination. |
| `girowatch_core.py` | ML-backed run and order grouping. |
| `error_review.py` | Configured error matching and assessment. |
| `monitoring_service.py` | Incremental reads, readiness checks, automatic scans, and status. |
| `home_errors.py`, `run_stats.py` | Incident tracking and completed-run statistics. |
| `historical_search.py`, `order_search.py` | Historical grouping, caching, and occurrence search. |
| `application_control.py`, `cam_control.ps1`, `cam_accessibility.cs` | External Windows integration and live display reading. |
| `local_test_mode.py`, `simulator_controls.py`, `test_simulator.py` | Isolated test environment and fictional applications. |
| `tests/` | Python and JavaScript regression tests. |

## Verification

Run the Python suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run JavaScript checks from PowerShell:

```powershell
Get-ChildItem tests/js/*.cjs | ForEach-Object { node $_.FullName }
node tests/actions_menu.test.cjs
```

Tests cover grouping, search, configuration persistence, incident handling,
incremental reads and handle closure, scanning settings, test-mode boundaries,
simulator behavior, and selected UI logic. Fictional fixtures and temporary
folders keep tests independent of live company data. Passing tests do not
establish production accuracy for an application's real logs.

## Current scope and limitations

- GiroWatch is an actively developed local Windows application.
- The server binds to **localhost**. Authentication, remote hosting, and multi-user
  access controls are not implemented; do not expose it to a network as-is.
- A scan reflects readable logs, not guaranteed real-time delivery or settlement.
- Closing log handles before classification reduces their lifetime but cannot
  guarantee compatibility with another application's exclusive file access.
- New formats and business codes require suitable examples, rules, and validation.
- Restarting an app does not repair an external service, payer failure, or order.
- Production logs, credentials, customer records, contacts, and machine-specific
  settings must remain out of Git. `.gitignore` excludes common local data, but
  review new files before committing them.
