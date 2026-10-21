# Local version extracted from GiroWatch.ipynb.
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from local_files import files
from pathlib import Path
import json
import re


# --------------------------------------------------
# 1. File locations
# --------------------------------------------------

# Files are stored in the current working folder.
profiles_file = Path("girosol_profiles.json")
results_folder = Path("results")
results_folder.mkdir(exist_ok=True)


# --------------------------------------------------
# 2. Remove timestamps before classification
# --------------------------------------------------

def clean_message(text):
    # Only the model's input is cleaned.
    # Original lines, including timestamps, are preserved.
    return re.sub(
        r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+[AP]M\s+",
        "",
        text
    ).strip()


# --------------------------------------------------
# 3. Default run profiles
# --------------------------------------------------

from copy import deepcopy
from run_defaults import DEFAULT_RUN_PROFILES

training_data = deepcopy(DEFAULT_RUN_PROFILES)


# --------------------------------------------------
# 4. Load previously saved profiles
# --------------------------------------------------

if profiles_file.exists():
    with open(profiles_file, "r", encoding="utf-8") as file:
        saved_profiles = json.load(file)

    # Saved profiles replace defaults with the same name.
    training_data.update(saved_profiles)
    print("Saved run profiles loaded.")


# --------------------------------------------------
# 5. Select or create a run profile
# --------------------------------------------------

choice = input(
    "Use an existing run profile or create one? (existing/new): "
).strip().lower()

if choice == "new":
    application = input("Application name: ").strip()

    if not application:
        raise ValueError("Enter an application name.")

    if application.lower() in {
        name.lower() for name in training_data
    }:
        raise ValueError(
            "That profile already exists. Choose 'existing'."
        )

    start_message = clean_message(input("Run-start message: "))
    end_message = clean_message(input("Run-end message: "))

    if not start_message or not end_message:
        raise ValueError("Start and end messages cannot be empty.")

    if start_message.lower() == end_message.lower():
        raise ValueError("Start and end messages must be different.")

    # Collect multiple Other examples.
    other_messages = []

    print("\nEnter Other examples, one message at a time.")
    print("Press Enter on an empty line when finished.")

    while True:
        entered_message = input("Other example: ").strip()

        if not entered_message:
            if not other_messages:
                print("Add at least one Other example.")
                continue
            break

        other_message = clean_message(entered_message)

        if not other_message:
            print("Enter message text, not just a timestamp.")
            continue

        if other_message.lower() in {
            start_message.lower(),
            end_message.lower()
        }:
            print("A boundary message cannot also be Other.")
            continue

        if other_message.lower() in {
            message.lower() for message in other_messages
        }:
            print("That example has already been added.")
            continue

        other_messages.append(other_message)

    # Create the profile with automatically assigned labels.
    training_data[application] = {
        "messages": [
            start_message,
            end_message
        ] + other_messages,

        "labels": [
            "Run_Start",
            "Run_End"
        ] + ["Other"] * len(other_messages)
    }

elif choice == "existing":
    print("Available profiles:", ", ".join(training_data))
    selected_name = input("Select an application: ").strip()

    matching_names = [
        name for name in training_data
        if name.lower() == selected_name.lower()
    ]

    if not matching_names:
        raise ValueError("That run profile does not exist.")

    application = matching_names[0]

else:
    raise ValueError("Please enter 'existing' or 'new'.")


# --------------------------------------------------
# 6. Save run profiles
# --------------------------------------------------

temporary_file = profiles_file.with_suffix(".tmp")

with open(temporary_file, "w", encoding="utf-8") as file:
    json.dump(training_data, file, indent=2, ensure_ascii=False)

temporary_file.replace(profiles_file)

print(f"Run profiles saved to: {profiles_file.resolve()}")


# --------------------------------------------------
# 7. Train the run classifier
# --------------------------------------------------

messages = [
    clean_message(message)
    for message in training_data[application]["messages"]
]
labels = training_data[application]["labels"].copy()

# Additional example to distinguish errors from run boundaries.
messages.append(
    "System.IO.IOException: The process cannot access the file "
    "because it is being used by another process."
)
labels.append("Other")

if len(messages) != len(labels):
    raise ValueError("Every training message must have one label.")

# Learn the vocabulary and convert messages into word counts.
vectorizer = CountVectorizer()
X = vectorizer.fit_transform(messages)

# Alpha controls smoothing of word counts.
model = MultinomialNB(alpha=0.1)
model.fit(X, labels)


# --------------------------------------------------
# 8. Select the raw log file
# --------------------------------------------------

print(f"\nSelected run profile: {application}")
print("Select one raw .log file:")

uploaded = files.upload()

if len(uploaded) != 1:
    raise ValueError("Please upload exactly one log file.")

filename = next(iter(uploaded))
log_path = Path(filename)

with open(log_path, "r", encoding="utf-8-sig") as file:
    log_lines = file.read().splitlines()

print(f"Loaded {len(log_lines)} lines.")


# --------------------------------------------------
# 9. Group log lines into runs
# --------------------------------------------------

runs = []
current_run = []
inside_run = False
has_activity = False

for line in log_lines:
    message = clean_message(line)

    # Preserve blank lines inside a run without classifying them.
    if not message:
        if inside_run:
            current_run.append(line)
        continue

    # Predict the category for this line.
    X_line = vectorizer.transform([message])
    label = model.predict(X_line)[0]

    if label == "Run_Start":
        # Preserve an unfinished run if it had activity.
        # Initialization-only groups are excluded.
        if inside_run and has_activity:
            runs.append({
                "status": "incomplete",
                "lines": current_run
            })

        # Begin a new run, including its start line.
        current_run = [line]
        inside_run = True
        has_activity = False

    elif inside_run:
        # Collect every line while inside a run.
        current_run.append(line)

        if label == "Run_End":
            # Save the run, including its end line.
            runs.append({
                "status": "complete",
                "lines": current_run
            })

            current_run = []
            inside_run = False
            has_activity = False

        elif "INITIALIZING TIME" not in message.upper():
            has_activity = True


# --------------------------------------------------
# 10. Save grouped runs as JSON
# --------------------------------------------------

safe_application = re.sub(
    r"[^A-Za-z0-9_-]+",
    "_",
    application
)

output_file = results_folder / (
    f"{safe_application}_{log_path.stem}_runs.json"
)

with open(output_file, "w", encoding="utf-8") as file:
    json.dump(runs, file, indent=2, ensure_ascii=False)

complete_count = sum(
    run["status"] == "complete" for run in runs
)
incomplete_count = sum(
    run["status"] == "incomplete" for run in runs
)

print(f"\nComplete runs: {complete_count}")
print(f"Incomplete runs: {incomplete_count}")
print(f"Results saved to: {output_file}")

# An open final run remains pending rather than being marked incomplete.
if inside_run:
    print("The final run is pending and is not included in this JSON.")

# Download the grouped-runs file for use in the order cell.
files.download(str(output_file))