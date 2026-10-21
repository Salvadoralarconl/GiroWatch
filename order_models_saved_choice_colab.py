from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC
from collections import Counter
from google.colab import files
from pathlib import Path
import json
import re


# --------------------------------------------------
# 1. Storage locations
# --------------------------------------------------

order_profiles_file = Path("order_profiles.json")

order_results_folder = Path("results")
order_results_folder.mkdir(exist_ok=True)


# --------------------------------------------------
# 2. Clean messages for classification
# --------------------------------------------------

def clean_order_message(text):
    # Remove timestamps from the model's input.
    text = re.sub(
        r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+[AP]M\s+",
        "",
        text
    )

    # Remove Girosol order IDs from the model's input.
    # Original saved lines keep their IDs and timestamps.
    text = re.sub(
        r"\b\d{17}C\d{2}\b",
        "",
        text,
        flags=re.IGNORECASE
    )

    return " ".join(text.split())


# --------------------------------------------------
# 3. Load saved order profiles
# --------------------------------------------------

order_training_data = {}

if order_profiles_file.exists():
    with open(order_profiles_file, "r", encoding="utf-8") as file:
        order_training_data = json.load(file)

    print("Saved order profiles loaded.")


# --------------------------------------------------
# 4. Collect training examples
# --------------------------------------------------

def collect_order_examples(label):
    examples = []

    print(f"\nEnter examples for {label}, one at a time.")
    print("Press Enter on an empty line when finished.")

    while True:
        entered = input(f"{label} example: ").strip()

        if not entered:
            if not examples:
                print("Enter at least one example.")
                continue
            break

        message = clean_order_message(entered)

        if not message:
            print("Enter message text, not just a timestamp or ID.")
            continue

        if message.lower() in {
            example.lower() for example in examples
        }:
            print("That example has already been added.")
            continue

        examples.append(message)

    return examples


# --------------------------------------------------
# 5. Select or create an order profile
# --------------------------------------------------

order_choice = input(
    "Use an existing order profile or create one? (existing/new): "
).strip().lower()

if order_choice == "new":
    order_application = input("Application name: ").strip()

    if not order_application:
        raise ValueError("Enter an application name.")

    if order_application.lower() in {
        name.lower() for name in order_training_data
    }:
        raise ValueError(
            "That order profile already exists. Choose 'existing'."
        )

    start_examples = collect_order_examples("Order_Start")
    end_examples = collect_order_examples("Order_End")
    other_examples = collect_order_examples("Other")

    order_training_data[order_application] = {
        "messages": (
            start_examples + end_examples + other_examples
        ),
        "labels": (
            ["Order_Start"] * len(start_examples)
            + ["Order_End"] * len(end_examples)
            + ["Other"] * len(other_examples)
        )
    }

elif order_choice == "existing":
    print(
        "Available order profiles:",
        ", ".join(order_training_data) or "(none)"
    )

    selected_name = input("Select an application: ").strip()

    matching_names = [
        name for name in order_training_data
        if name.lower() == selected_name.lower()
    ]

    if not matching_names:
        raise ValueError("That order profile does not exist.")

    order_application = matching_names[0]

else:
    raise ValueError("Please enter 'existing' or 'new'.")


# --------------------------------------------------
# 6. Prepare training examples
# --------------------------------------------------

selected_profile = order_training_data[order_application]

if len(selected_profile["messages"]) != len(selected_profile["labels"]):
    raise ValueError("Every training message must have one label.")

order_messages = []
order_labels = []
seen_messages = {}

for message, label in zip(
    selected_profile["messages"],
    selected_profile["labels"]
):
    cleaned = clean_order_message(message)

    if not cleaned:
        raise ValueError("A training example is empty after cleaning.")

    if label not in {"Order_Start", "Order_End", "Other"}:
        raise ValueError(
            f"Unexpected label: {label}. "
            "This version uses Order_Start, Order_End, and Other."
        )

    key = cleaned.lower()

    if key in seen_messages:
        if seen_messages[key] != label:
            raise ValueError(
                f"Conflicting labels after cleaning: {cleaned}"
            )

        # Skip duplicate cleaned examples.
        continue

    seen_messages[key] = label
    order_messages.append(cleaned)
    order_labels.append(label)

if set(order_labels) != {"Order_Start", "Order_End", "Other"}:
    raise ValueError(
        "The profile needs Order_Start, Order_End, and Other examples."
    )


# --------------------------------------------------
# 7. Save order profiles
# --------------------------------------------------

temporary_file = order_profiles_file.with_suffix(".tmp")

with open(temporary_file, "w", encoding="utf-8") as file:
    json.dump(
        order_training_data,
        file,
        indent=2,
        ensure_ascii=False
    )

temporary_file.replace(order_profiles_file)

print(f"Order profiles saved to: {order_profiles_file.resolve()}")


# --------------------------------------------------
# 8. Model choices shared by all application profiles
# --------------------------------------------------

# Each application still has ONE messages list and ONE labels list.
# Testing another model does not change or copy those examples.
MODEL_NAMES = {
    "naive_bayes": "Word-pair Naive Bayes",
    "nearest_example": "TF-IDF nearest example",
    "linear_svm": "TF-IDF Linear SVM (backup)"
}


def choose_model(default_key=None):
    print("\n1: Word-pair Naive Bayes (main model)")
    print("2: TF-IDF nearest example (main model)")
    print("3: TF-IDF Linear SVM (backup only)")

    if default_key in MODEL_NAMES:
        print(f"Default: {MODEL_NAMES[default_key]}")
        print("Press Enter to use it, or enter another model number.")

    choices = {
        "1": "naive_bayes",
        "2": "nearest_example",
        "3": "linear_svm"
    }

    while True:
        answer = input("Model number: ").strip()
        if not answer and default_key in MODEL_NAMES:
            return default_key
        if answer in choices:
            return choices[answer]
        print("Enter 1, 2, or 3.")


def train_order_model(model_key):
    # All three models use the same application examples and labels.
    # Model 1 keeps the original Cam configuration.
    if model_key == "naive_bayes":
        vectorizer = CountVectorizer(ngram_range=(1, 2))
        model = MultinomialNB(alpha=0.1)

    elif model_key == "nearest_example":
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        model = KNeighborsClassifier(
            n_neighbors=1,
            metric="cosine",
            algorithm="brute"
        )

    else:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        model = LinearSVC(
            class_weight="balanced",
            random_state=0,
            max_iter=10000
        )

    X = vectorizer.fit_transform(order_messages)
    model.fit(X, order_labels)
    return vectorizer, model, X


# --------------------------------------------------
# 10. Upload grouped-runs JSON
# --------------------------------------------------

print(f"\nSelected order profile: {order_application}")
print("Upload its grouped-runs JSON file, not the raw .log.")

uploaded_runs = files.upload()

if len(uploaded_runs) != 1:
    raise ValueError("Please upload exactly one JSON file.")

runs_path = Path(next(iter(uploaded_runs)))

if runs_path.suffix.lower() != ".json":
    raise ValueError(
        "Select the grouped-runs JSON created by the run cell."
    )

try:
    with open(runs_path, "r", encoding="utf-8-sig") as file:
        order_input_runs = json.load(file)
except json.JSONDecodeError as error:
    raise ValueError(
        "The uploaded file is not valid JSON."
    ) from error

if not isinstance(order_input_runs, list):
    raise ValueError("The grouped-runs file must contain a list.")

for run_number, run in enumerate(order_input_runs, start=1):
    if not isinstance(run, dict):
        raise ValueError(f"Run {run_number} has an invalid format.")

    if (
        not isinstance(run.get("status"), str)
        or run["status"] not in ("complete", "incomplete")
        or not isinstance(run.get("lines"), list)
        or not all(isinstance(line, str) for line in run["lines"])
    ):
        raise ValueError(
            f"Run {run_number} has an invalid format. "
            "Upload the JSON produced by run grouping."
        )

print(f"Loaded {len(order_input_runs)} runs.")


# --------------------------------------------------
# 11. Test models using the same uploaded file
# --------------------------------------------------

# Older profiles have no selected_model yet. Choose one on the first test.
default_model = selected_profile.get("selected_model")

while True:
    model_key = choose_model(default_model)

    order_vectorizer, order_model, order_X = train_order_model(model_key)

    print(f"\nApplication: {order_application}")
    print(f"Testing: {MODEL_NAMES[model_key]}")
    print("Training examples:", dict(Counter(order_labels)))

    # Check known examples. This is NOT accuracy on the uploaded log.
    training_predictions = order_model.predict(order_X)
    mistake_count = 0

    for message, expected, predicted in zip(
        order_messages, order_labels, training_predictions
    ):
        if expected != predicted:
            mistake_count += 1
            print(f"Expected: {expected} | Predicted: {predicted}")
            print(message)

    print(f"Training-example mismatches: {mistake_count}")

    # --------------------------------------------------
    # 11. Group orders within each run
    # --------------------------------------------------

    order_results = []

    for run_number, run in enumerate(order_input_runs, start=1):
        orders = []
        current_order = []
        inside_order = False
        unassigned_lines = []

        for line in run["lines"]:
            message = clean_order_message(line)

            # Preserve blank lines without classifying them.
            if not message:
                if inside_order:
                    current_order.append(line)
                else:
                    unassigned_lines.append(line)
                continue

            order_line_X = order_vectorizer.transform([message])
            order_label = order_model.predict(order_line_X)[0]

            if order_label == "Order_Start":
                # Preserve an unfinished group if another start appears.
                if inside_order:
                    orders.append({
                        "status": "incomplete",
                        "lines": current_order
                    })

                current_order = [line]
                inside_order = True

            elif inside_order:
                # Save original lines with timestamps and order IDs.
                current_order.append(line)

                if order_label == "Order_End":
                    orders.append({
                        "status": "complete",
                        "lines": current_order
                    })

                    current_order = []
                    inside_order = False

            else:
                # Preserve lines outside detected order groups.
                unassigned_lines.append(line)

        # Keep occurrences separate across different runs.
        if inside_order:
            orders.append({
                "status": (
                    "incomplete"
                    if run["status"] == "complete"
                    else "unresolved"
                ),
                "lines": current_order
            })

        order_results.append({
            "application": order_application,
            "model": model_key,
            "run_number": run_number,
            "run_status": run["status"],
            "orders": orders,
            "unassigned_lines": unassigned_lines
        })


    # --------------------------------------------------
    # 12. Save and download results
    # --------------------------------------------------

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        order_application
    )

    order_output_file = order_results_folder / (
        f"{safe_name}_{model_key}_{runs_path.stem}_orders.json"
    )

    with open(order_output_file, "w", encoding="utf-8") as file:
        json.dump(
            order_results,
            file,
            indent=2,
            ensure_ascii=False
        )

    total_orders = sum(
        len(result["orders"]) for result in order_results
    )

    print(f"\nSaved {total_orders} order groups.")
    print(f"Results saved to: {order_output_file}")

    files.download(str(order_output_file))

    # Review the downloaded results before choosing what to keep.
    print("\nGroup counts and training matches are not an accuracy score.")
    print("test = keep testing another model on the same data")
    print("save = save this model choice to the application profile")
    print("stop = exit without changing the saved model choice")

    while True:
        action = input("Next action (test/save/stop): ").strip().lower()
        if action in {"test", "save", "stop"}:
            break
        print("Enter test, save, or stop.")

    if action == "test":
        # No new file upload and no changes to the saved model.
        default_model = model_key
        continue

    if action == "save":
        # Save only the choice. Retrain from these same examples next time.
        selected_profile["selected_model"] = model_key

        temporary_file = order_profiles_file.with_suffix(".tmp")
        with open(temporary_file, "w", encoding="utf-8") as file:
            json.dump(order_training_data, file, indent=2, ensure_ascii=False)
        temporary_file.replace(order_profiles_file)

        print(f"Saved {MODEL_NAMES[model_key]} for {order_application}.")
        print("Next time, press Enter at model selection to use this choice.")
        # Download a backup because Colab runtime storage can reset.
        files.download(str(order_profiles_file))

    else:
        print("Stopped. The previously saved model choice was not changed.")

    break
