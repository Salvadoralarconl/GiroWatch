"""Import-safe versions of the existing notebook grouping algorithms.

The terminal workflows remain intact. This module lets the website call the
same classifiers without running input() prompts or changing saved profiles.
"""
from copy import deepcopy
import re

from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC

from error_review import review_lines, review_runs

MODEL_NAMES = {
    'naive_bayes': 'Word-pair Naive Bayes',
    'nearest_example': 'TF-IDF nearest example',
    'linear_svm': 'TF-IDF Linear SVM · backup',
}
TIMESTAMP = r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+[AP]M\s+'


def clean_message(text):
    return re.sub(TIMESTAMP, '', text).strip()


def clean_order_message(text):
    text = re.sub(r'\b\d{17}C\d{2}\b', '', clean_message(text), flags=re.I)
    return ' '.join(text.split())


def prepare_examples(profile, kind):
    """Validate manual labels and reject conflicting cleaned examples."""
    start, end = ('Run_Start', 'Run_End') if kind == 'run' else ('Order_Start', 'Order_End')
    clean = clean_message if kind == 'run' else clean_order_message
    if len(profile.get('messages', [])) != len(profile.get('labels', [])):
        raise ValueError('Every training message must have one label.')
    messages, labels, seen = [], [], {}
    for message, label in zip(profile.get('messages', []), profile.get('labels', [])):
        if not isinstance(message, str) or label not in (start, end, 'Other'):
            raise ValueError('Invalid training message or label.')
        message = clean(message)
        if not message:
            raise ValueError('A training example is empty after cleaning.')
        key = message.casefold()
        if key in seen:
            if seen[key] != label:
                raise ValueError(f'Conflicting labels: {message}')
            if kind == 'order':
                continue
        seen[key] = label
        messages.append(message)
        labels.append(label)
    if set(labels) != {start, end, 'Other'}:
        raise ValueError(f'The {kind} profile needs {start}, {end}, and Other examples.')
    return messages, labels


def group_runs(lines, profile):
    messages, labels = prepare_examples(profile, 'run')
    messages.append('System.IO.IOException: The process cannot access the file because it is being used by another process.')
    labels.append('Other')
    vectorizer = CountVectorizer()
    model = MultinomialNB(alpha=0.1).fit(vectorizer.fit_transform(messages), labels)
    runs, current = [], []
    inside = activity = False
    # Batch predictions avoid thousands of individual sklearn calls. The model,
    # cleaned input and state transitions match the original run cell.
    cleaned = [clean_message(line) for line in lines]
    predictions = iter(model.predict(vectorizer.transform([m for m in cleaned if m]))) if any(cleaned) else iter(())
    for line, message in zip(lines, cleaned):
        if not message:
            if inside:
                current.append(line)
            continue
        label = next(predictions)
        if label == 'Run_Start':
            if inside and activity:
                runs.append({'status': 'incomplete', 'lines': current})
            current, inside, activity = [line], True, False
        elif inside:
            current.append(line)
            if label == 'Run_End':
                runs.append({'status': 'complete', 'lines': current})
                current, inside, activity = [], False, False
            elif 'INITIALIZING TIME' not in message.upper():
                activity = True
    # An open final run stays pending, just as in the original cell.
    return runs, inside


def group_orders(runs, profile, model_key, application):
    messages, labels = prepare_examples(profile, 'order')
    if model_key not in MODEL_NAMES:
        raise ValueError('Choose a supported order model.')
    if model_key == 'naive_bayes':
        vectorizer, model = CountVectorizer(ngram_range=(1, 2)), MultinomialNB(alpha=0.1)
    elif model_key == 'nearest_example':
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        model = KNeighborsClassifier(n_neighbors=1, metric='cosine', algorithm='brute')
    else:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        model = LinearSVC(class_weight='balanced', random_state=0, max_iter=10000)
    model.fit(vectorizer.fit_transform(messages), labels)
    results = []
    for number, run in enumerate(runs, 1):
        orders, current, unassigned = [], [], []
        inside = False
        cleaned = [clean_order_message(line) for line in run['lines']]
        predictions = iter(model.predict(vectorizer.transform([m for m in cleaned if m]))) if any(cleaned) else iter(())
        for line, message in zip(run['lines'], cleaned):
            if not message:
                (current if inside else unassigned).append(line)
                continue
            label = next(predictions)
            if label == 'Order_Start':
                if inside:
                    orders.append({'status': 'incomplete', 'lines': current})
                current, inside = [line], True
            elif inside:
                current.append(line)
                if label == 'Order_End':
                    orders.append({'status': 'complete', 'lines': current})
                    current, inside = [], False
            else:
                unassigned.append(line)
        if inside:
            orders.append({'status': 'incomplete' if run['status'] == 'complete' else 'unresolved', 'lines': current})
        results.append({'application': application, 'model': model_key, 'run_number': number,
                        'run_status': run['status'], 'orders': orders, 'unassigned_lines': unassigned})
    return results


def apply_rules(runs, rules, application):
    if rules:
        return review_runs(runs, rules, application)
    # No policy means unassessed, never an automatic all-clear.
    results = deepcopy(runs)
    for run in results:
        for number, order in enumerate(run['orders'], 1):
            order.update(review_lines(order['lines'], []))
            order['group_number'] = number
        run['unassigned_review'] = review_lines(run['unassigned_lines'], [])
    return results


def search_orders(runs, query):
    query = query.strip().casefold()
    if not query:
        return []
    return [dict(group, run_number=run['run_number']) for run in runs for group in run['orders']
            if any(query in line.casefold() for line in group['lines'])]
