from pathlib import Path
from copy import deepcopy
from collections import Counter
import json
import re

from google.colab import files
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC


# ORDER GROUPING ONLY. Keep the run-grouping cell unchanged.
# Separate storage protects the previous Cam profile file.
PROFILE_FILE = Path("order_model_profiles.json")
LEGACY_FILE = Path("order_profiles.json")
RESULTS_FOLDER = Path("results")
RESULTS_FOLDER.mkdir(exist_ok=True)
LABELS = ("Order_Start", "Order_End", "Other")
MODEL_NAMES = {
    "naive_bayes": "Word-pair Naive Bayes",
    "nearest_example": "TF-IDF nearest example",
    "linear_svm": "TF-IDF Linear SVM (backup)"
}


def clean_message(text):
    # Remove changing values only from the model input.
    # Original lines are retained in exported results.
    text = re.sub(
        r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+[AP]M\s+",
        "", text
    )
    text = re.sub(r"\b\d{17}[CI]\d{2}\b", "", text, flags=re.I)
    text = re.sub(r"\b\d+X\d+C\d+\b", "", text, flags=re.I)
    # Normalize the claim value, keeping the message wording.
    text = re.sub(
        r"(\bCLAIM\s+NUMBER\s+)\S+",
        r"\1", text, flags=re.I
    )
    return " ".join(text.split())


def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, data):
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    temporary.replace(path)


def yes_no(prompt):
    while True:
        answer = input(prompt).strip().lower()
        if answer in {"yes", "no"}:
            return answer == "yes"
        print("Enter yes or no.")


def training_pairs(profile):
    # Validate saved examples and remove duplicates after cleaning.
    if not isinstance(profile, dict):
        raise ValueError("Invalid training profile.")
    messages = profile.get("messages")
    labels = profile.get("labels")
    if not isinstance(messages, list) or not isinstance(labels, list):
        raise ValueError("A profile needs messages and labels lists.")
    if len(messages) != len(labels):
        raise ValueError("Every example needs one label.")
    pairs = {}
    for message, label in zip(messages, labels):
        if not isinstance(message, str) or label not in LABELS:
            raise ValueError("Invalid message or label in the profile.")
        cleaned = clean_message(message)
        if not cleaned:
            raise ValueError("An example is empty after cleaning.")
        key = cleaned.lower()
        if key in pairs and pairs[key][1] != label:
            raise ValueError(f"Conflicting labels after cleaning: {cleaned}")
        pairs[key] = (cleaned, label)
    return pairs


def edit_examples(profile):
    pairs = training_pairs(profile)
    for label in LABELS:
        count = sum(value[1] == label for value in pairs.values())
        print(f"\n{label}: {count} saved examples.")
        print("Enter examples one at a time; blank finishes this category.")
        while True:
            entered = input(f"{label} example: ").strip()
            if not entered:
                if not any(value[1] == label for value in pairs.values()):
                    print("Add at least one example for this category.")
                    continue
                break
            message = clean_message(entered)
            if not message:
                print("Enter message text, not just an ID or timestamp.")
                continue
            key = message.lower()
            if key in pairs and pairs[key][1] != label:
                print(f"Corrected label from {pairs[key][1]} to {label}.")
            pairs[key] = (message, label)
    return {
        "messages": [value[0] for value in pairs.values()],
        "labels": [value[1] for value in pairs.values()]
    }


# 1. Choose the application and model manually.
profiles = load_json(PROFILE_FILE)
legacy = load_json(LEGACY_FILE)
if not isinstance(profiles, dict) or not isinstance(legacy, dict):
    raise ValueError("Profile files must contain dictionaries.")
print("Applications:", ", ".join(sorted(set(profiles) | set(legacy))) or "none")
entered_name = input("Application name (existing or new): ").strip()
if not entered_name:
    raise ValueError("Enter an application name.")
matching = [
    name for name in set(profiles) | set(legacy)
    if name.lower() == entered_name.lower()
]
if len(matching) > 1:
    raise ValueError("Duplicate application names differ only by capitalization.")
application = matching[0] if matching else entered_name
profiles.setdefault(application, {})

print("\n1: Word-pair Naive Bayes (main model)")
print("2: TF-IDF nearest example (main model)")
print("3: TF-IDF Linear SVM (backup only)")
choice = input("Model number: ").strip()
model_key = {"1": "naive_bayes", "2": "nearest_example", "3": "linear_svm"}.get(choice)
if model_key is None:
    raise ValueError("Choose 1, 2, or 3.")


# 2. Reuse saved data, copy data from another model, or type examples.
if model_key in profiles[application]:
    profile = deepcopy(profiles[application][model_key])
    if yes_no("Add or correct examples for this profile? (yes/no): "):
        profile = edit_examples(profile)
else:
    sources = list(profiles[application].items())
    if application in legacy:
        sources.append(("previous single-line profile", legacy[application]))
    profile = {"messages": [], "labels": []}
    if sources:
        print("\nExamples available to copy for this application:")
        for number, (name, _) in enumerate(sources, start=1):
            print(f"{number}: {MODEL_NAMES.get(name, name)}")
        print("0: Type new examples")
        source_choice = input("Copy from which profile? ").strip()
        if source_choice != "0":
            if not source_choice.isdigit() or not 1 <= int(source_choice) <= len(sources):
                raise ValueError("Choose one of the displayed numbers.")
            profile = deepcopy(sources[int(source_choice) - 1][1])
    if not profile["messages"]:
        profile = edit_examples(profile)
    elif yes_no("Add or correct the copied examples? (yes/no): "):
        profile = edit_examples(profile)

pairs = training_pairs(profile)
messages = [value[0] for value in pairs.values()]
labels = [value[1] for value in pairs.values()]
if set(labels) != set(LABELS):
    raise ValueError("The profile needs examples for all three labels.")


# 3. Train only the chosen model using this application's examples.
if model_key == "naive_bayes":
    vectorizer = CountVectorizer(ngram_range=(1, 2))
    model = MultinomialNB(alpha=0.1)
elif model_key == "nearest_example":
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    model = KNeighborsClassifier(n_neighbors=1, metric="cosine", algorithm="brute")
else:
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    model = LinearSVC(class_weight="balanced", random_state=0, max_iter=10000)

X = vectorizer.fit_transform(messages)
model.fit(X, labels)
training_predictions = model.predict(X)
mistakes = sum(expected != predicted for expected, predicted in zip(labels, training_predictions))
print(f"\nApplication: {application}")
print(f"Model: {MODEL_NAMES[model_key]}")
print("Examples per label:", dict(Counter(labels)))
print(f"Training-example mismatches: {mistakes}")
for message, expected, predicted in zip(messages, labels, training_predictions):
    if expected != predicted:
        print(f"Expected {expected}; predicted {predicted}: {message}")

# Store examples independently for this application AND model.
# Model objects are retrained on each execution, not serialized here.
profiles[application][model_key] = {"messages": messages, "labels": labels}
save_json(PROFILE_FILE, profiles)


# 4. Upload the JSON generated by the unchanged run-grouping cell.
print(f"\nUpload {application}'s grouped-runs JSON, not its raw .log.")
uploaded = files.upload()
if len(uploaded) != 1:
    raise ValueError("Upload exactly one JSON file.")
input_path = Path(next(iter(uploaded)))
if input_path.suffix.lower() != ".json":
    raise ValueError("Select a grouped-runs .json file.")
runs = load_json(input_path)
if not isinstance(runs, list) or not runs:
    raise ValueError("The JSON must contain a nonempty list of grouped runs.")
for number, run in enumerate(runs, start=1):
    if not isinstance(run, dict):
        raise ValueError(f"Invalid run {number}.")
    if (run.get("status") not in ("complete", "incomplete")
            or not isinstance(run.get("lines"), list)
            or not all(isinstance(line, str) for line in run["lines"])):
        raise ValueError(f"Invalid grouped-run format in run {number}.")


# 5. Group the predicted boundaries, keeping original log lines.
def group_lines(lines, predictions, run_status):
    orders, current, unassigned = [], [], []
    inside = False
    for line, label in zip(lines, predictions):
        if label == "Order_Start":
            if inside:
                orders.append({"status": "incomplete", "lines": current})
            current = [line]
            inside = True
        elif inside:
            current.append(line)
            if label == "Order_End":
                orders.append({"status": "complete", "lines": current})
                current = []
                inside = False
        else:
            unassigned.append(line)
    if inside:
        status = "incomplete" if run_status == "complete" else "unresolved"
        orders.append({"status": status, "lines": current})
    return orders, unassigned


results = []
unknown_lines = 0
for run_number, run in enumerate(runs, start=1):
    lines = run["lines"]
    predictions = ["Other"] * len(lines)
    positions = [index for index, line in enumerate(lines) if clean_message(line)]
    # Batch classification is faster than predicting each line separately.
    for offset in range(0, len(positions), 500):
        batch = positions[offset:offset + 500]
        features = vectorizer.transform([clean_message(lines[index]) for index in batch])
        known = [index for index, count in enumerate(features.getnnz(axis=1)) if count > 0]
        unknown_lines += len(batch) - len(known)
        if known:
            for row, predicted in zip(known, model.predict(features[known])):
                predictions[batch[row]] = str(predicted)
    orders, unassigned = group_lines(lines, predictions, run["status"])
    results.append({
        "application": application,
        "model": model_key,
        "source_file": input_path.name,
        "run_number": run_number,
        "run_status": run["status"],
        "orders": orders,
        "unassigned_lines": unassigned
    })


# 6. Save results with the model name for easy comparison.
safe_application = re.sub(r"[^A-Za-z0-9_-]+", "_", application)
output_path = RESULTS_FOLDER / f"{safe_application}_{model_key}_{input_path.stem}_orders.json"
save_json(output_path, results)
groups = [group for run in results for group in run["orders"]]
print(f"\nRuns processed: {len(results)}")
print(f"Predicted order groups: {len(groups)}")
print("Group statuses:", dict(Counter(group["status"] for group in groups)))
print(f"Unassigned lines: {sum(len(run['unassigned_lines']) for run in results)}")
print(f"Lines with no known vocabulary, kept as Other: {unknown_lines}")
print(f"Results saved to: {output_path}")
print("Group counts and training matches are not an accuracy score.")
files.download(str(output_path))
files.download(str(PROFILE_FILE))
