"""Separate, manually configured error detection for saved order groups.

Run in Colab with: %run order_error_review_colab.py
This code does not retrain models or change order/run boundaries.
"""
from pathlib import Path
from collections import Counter
from copy import deepcopy
import json
import re

ERROR_PROFILES_FILE = Path("error_profiles.json")
RESULTS_FOLDER = Path("results")
SEVERITIES = ("Ignore", "Warning", "Critical")
PRIORITY = {"None": 0, "Ignore": 0, "Warning": 1, "Critical": 2}


def save_json(path, data):
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    temporary.replace(path)


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise ValueError("Add at least one error rule.")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Each error rule must be a dictionary.")
        if not isinstance(rule.get("match"), str) or not rule["match"].strip():
            raise ValueError("Every rule needs nonempty match text.")
        if rule.get("severity") not in SEVERITIES:
            raise ValueError("Each rule needs Ignore, Warning, or Critical.")
        if not isinstance(rule.get("message", ""), str):
            raise ValueError("A rule's display message must be text.")
        if not isinstance(rule.get("case_sensitive", False), bool):
            raise ValueError("case_sensitive must be true or false.")


def review_lines(lines, rules):
    """Return every original line plus findings, without changing its group."""
    findings = []
    for line_number, line in enumerate(lines, start=1):
        matches = []
        for rule_number, rule in enumerate(rules, start=1):
            # Match literal text, not executable code or regular expressions.
            flags = 0 if rule.get("case_sensitive", False) else re.IGNORECASE
            for match in re.finditer(re.escape(rule["match"]), line, flags):
                matches.append({
                    "rule_number": rule_number,
                    "line_number": line_number,
                    "match": rule["match"],
                    "matched_text": match.group(),
                    "severity": rule["severity"],
                    "message": rule.get("message") or rule["match"],
                    "start": match.start(),
                    "end": match.end(),
                    "alert": rule["severity"] != "Ignore"
                })

        # A specific ignore phrase can suppress a broad match inside it.
        # It cannot suppress an unrelated error elsewhere on the same line.
        ignored_matches = [m for m in matches if m["severity"] == "Ignore"]
        for finding in matches:
            if finding["alert"]:
                containing_ignores = [
                    ignored for ignored in ignored_matches
                    if ignored["start"] <= finding["start"]
                    and ignored["end"] >= finding["end"]
                ]
                if containing_ignores:
                    finding["alert"] = False
                    finding["suppressed_by_rules"] = [
                        ignored["rule_number"] for ignored in containing_ignores
                    ]
        findings.extend(matches)

    active = [finding for finding in findings if finding["alert"]]
    highest = max(
        (finding["severity"] for finding in active),
        key=lambda severity: PRIORITY[severity],
        default="None"
    )
    return {
        "lines": list(lines),
        "has_alert": bool(active),
        "highest_severity": highest,
        "outcome": "not_assessed",
        "findings": findings
    }


def review_runs(runs, rules, application):
    validate_rules(rules)
    results = []
    for position, run in enumerate(runs, start=1):
        reviewed_orders = []
        for group_number, group in enumerate(run["orders"], start=1):
            # Preserve every original field, including the grouping status.
            reviewed_group = deepcopy(group)
            reviewed_group.update(review_lines(group["lines"], rules))
            reviewed_group["group_number"] = group_number
            reviewed_orders.append(reviewed_group)

        result = deepcopy(run)
        result["application"] = application
        result["run_number"] = run.get("run_number", position)
        result["orders"] = reviewed_orders
        # Never attach unassigned errors to an order by guessing.
        result["unassigned_review"] = review_lines(run["unassigned_lines"], rules)
        results.append(result)
    return results


def validate_runs(runs):
    if not isinstance(runs, list) or not runs:
        raise ValueError("Upload a nonempty order-grouping results JSON.")
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, dict) or not isinstance(run.get("orders"), list):
            raise ValueError(
                f"Run {index}: upload ORDER results, not raw logs or run-only JSON."
            )
        if not isinstance(run.get("unassigned_lines"), list):
            raise ValueError(f"Run {index} needs unassigned_lines.")
        if not all(isinstance(line, str) for line in run["unassigned_lines"]):
            raise ValueError(f"Run {index} has invalid unassigned text.")
        for group in run["orders"]:
            if (not isinstance(group, dict)
                    or not isinstance(group.get("lines"), list)
                    or not all(isinstance(line, str) for line in group["lines"])):
                raise ValueError(f"Run {index} contains an invalid order group.")


def yes_no(prompt):
    while True:
        answer = input(prompt).strip().lower()
        if answer in {"yes", "no"}:
            return answer == "yes"
        print("Enter yes or no.")


def enter_rules(existing):
    # Start with saved rules; adding the same phrase updates that rule.
    rules = deepcopy(existing)
    print("\nEnter your predetermined error phrases or codes one at a time.")
    print("Use a distinctive phrase such as an error-code prefix.")
    print("Matches ignore capitalization. Press Enter on a blank phrase to finish.")
    print("No severities are assigned automatically; you choose each one.")
    while True:
        phrase = input("Error match text: ").strip()
        if not phrase:
            if not rules:
                print("Enter at least one rule.")
                continue
            break
        print("1: Ignore   2: Warning   3: Critical")
        while True:
            choice = input("Severity number: ").strip()
            if choice in {"1", "2", "3"}:
                severity = {"1":"Ignore", "2":"Warning", "3":"Critical"}[choice]
                break
            print("Enter 1, 2, or 3.")
        message = input("Display message (Enter to use match text): ").strip()
        new_rule = {
            "match": phrase,
            "severity": severity,
            "message": message or phrase,
            "case_sensitive": False
        }
        matches = [i for i, rule in enumerate(rules) if rule["match"].casefold() == phrase.casefold()]
        if matches:
            rules[matches[0]] = new_rule
            print("Updated that rule.")
        else:
            rules.append(new_rule)
            print("Added rule.")
    return rules


def display_review(review):
    # Show the WHOLE group, marking matching error lines for context.
    active = [finding for finding in review["findings"] if finding["alert"]]
    by_line = {}
    for finding in active:
        by_line.setdefault(finding["line_number"], []).append(finding)
    print("\nSeverity:", review["highest_severity"])
    for number, line in enumerate(review["lines"], start=1):
        if number in by_line:
            severity = max(
                (finding["severity"] for finding in by_line[number]),
                key=lambda value: PRIORITY[value]
            )
            print(f">>> [{severity}] {number}: {line}")
            for message in dict.fromkeys(f["message"] for f in by_line[number]):
                print(f"    Reason: {message}")
        else:
            print(f"    {number}: {line}")


def main():
    # Import Colab only when running the interactive cell.
    from google.colab import files

    # 1. Load or create the application's manually configured error profile.
    profiles = {}
    if ERROR_PROFILES_FILE.exists():
        with open(ERROR_PROFILES_FILE, "r", encoding="utf-8-sig") as file:
            profiles = json.load(file)
    if not isinstance(profiles, dict):
        raise ValueError("error_profiles.json must contain a dictionary.")
    print("Saved error profiles:", ", ".join(profiles) or "none")
    entered = input("Application name: ").strip()
    if not entered:
        raise ValueError("Enter an application name.")
    matching = [name for name in profiles if name.casefold() == entered.casefold()]
    application = matching[0] if matching else entered
    rules = deepcopy(profiles.get(application, {}).get("rules", []))
    if rules:
        print("\nSaved rules:")
        for number, rule in enumerate(rules, start=1):
            print(f"{number}: {rule['severity']} | {rule['match']} | {rule.get('message', '')}")
    if not rules or yes_no("Add or update error rules? (yes/no): "):
        rules = enter_rules(rules)
    validate_rules(rules)
    profiles[application] = {"rules": rules}
    save_json(ERROR_PROFILES_FILE, profiles)

    # 2. Upload the ORDER-grouping output, leaving that source unchanged.
    print(f"\nUpload {application}'s ORDER-grouping results JSON.")
    uploaded = files.upload()
    if len(uploaded) != 1:
        raise ValueError("Upload exactly one JSON file.")
    input_path = Path(next(iter(uploaded)))
    if input_path.suffix.lower() != ".json":
        raise ValueError("Select an order-grouping JSON file, not the raw log.")
    with open(input_path, "r", encoding="utf-8-sig") as file:
        runs = json.load(file)
    validate_runs(runs)
    declared_apps = {run["application"].casefold() for run in runs if isinstance(run.get("application"), str)}
    if declared_apps and declared_apps != {application.casefold()}:
        raise ValueError("The file's application does not match this error profile.")

    # 3. Apply error rules to order groups AND unassigned run lines.
    reviewed = review_runs(runs, rules, application)
    alerts = []
    findings = []
    for run in reviewed:
        for group in run["orders"]:
            findings.extend(group["findings"])
            if group["has_alert"]:
                alerts.append((run["run_number"], f"Order group {group['group_number']}", group))
        unassigned = run["unassigned_review"]
        findings.extend(unassigned["findings"])
        if unassigned["has_alert"]:
            alerts.append((run["run_number"], "Unassigned run lines", unassigned))

    # 4. Save all original groups and attach the findings.
    RESULTS_FOLDER.mkdir(exist_ok=True)
    safe_application = re.sub(r"[^A-Za-z0-9_-]+", "_", application)
    output_path = RESULTS_FOLDER / f"{safe_application}_{input_path.stem}_error_review.json"
    report = {
        "application": application,
        "source_file": input_path.name,
        "rules_used": deepcopy(rules),
        "outcome_assessed": False,
        "runs": reviewed
    }
    save_json(output_path, report)

    # Ignored matches are recorded but do not create alerts.
    print(f"\nRuns reviewed: {len(reviewed)}")
    print(f"Order groups reviewed: {sum(len(run['orders']) for run in reviewed)}")
    print(f"Groups or unassigned sections with alerts: {len(alerts)}")
    print("Alert severities:", dict(Counter(item[2]["highest_severity"] for item in alerts)))
    print("Ignored/suppressed matching occurrences:", sum(not finding["alert"] for finding in findings))
    print("Original grouping status is preserved. Final success/failure is not assessed.")
    print("Unassigned errors stay with their run; they are not attached to an order.")
    print("The report preserves the run's groups and unassigned lines separately.")

    files.download(str(output_path))
    # Back up manually entered rules so they can be restored after a reset.
    files.download(str(ERROR_PROFILES_FILE))

    # 5. Inspect one alert at a time instead of flooding the notebook.
    for number, (run_number, location, review) in enumerate(alerts[:20], start=1):
        print(f"{number}: Run {run_number} | {location} | {review['highest_severity']}")
    if len(alerts) > 20:
        print(f"Showing the first 20 of {len(alerts)} alert locations. Any number can be opened.")
    while alerts:
        entered = input("\nAlert number to show in full (Enter to finish): ").strip()
        if not entered:
            break
        if not entered.isdigit() or not 1 <= int(entered) <= len(alerts):
            print("Enter a valid alert number.")
            continue
        run_number, location, review = alerts[int(entered) - 1]
        print(f"\nRun {run_number} | {location}")
        display_review(review)


if __name__ == "__main__":
    main()
