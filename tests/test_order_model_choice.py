"""Control-flow tests with stand-ins for Colab and classifiers.

These tests check save/retest behavior, not numerical model accuracy.
"""
import builtins
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "order_models_saved_choice_colab.py"


class Vector:
    def __init__(self, **kwargs):
        pass

    def fit_transform(self, messages):
        return messages

    def transform(self, messages):
        return messages


class Classifier:
    def __init__(self, **kwargs):
        pass

    def fit(self, messages, labels):
        self.examples = dict(zip(messages, labels))

    def predict(self, messages):
        return [self.examples.get(message, "Other") for message in messages]


class ModelChoiceTests(unittest.TestCase):
    def execute(self, answers, saved=None, new=False):
        uploads, downloads = [], []
        modules = {}
        for name in ["sklearn", "sklearn.feature_extraction", "sklearn.feature_extraction.text", "sklearn.naive_bayes", "sklearn.neighbors", "sklearn.svm", "google", "google.colab"]:
            modules[name] = types.ModuleType(name)
        modules["sklearn.feature_extraction.text"].CountVectorizer = Vector
        modules["sklearn.feature_extraction.text"].TfidfVectorizer = Vector
        modules["sklearn.naive_bayes"].MultinomialNB = Classifier
        modules["sklearn.neighbors"].KNeighborsClassifier = Classifier
        modules["sklearn.svm"].LinearSVC = Classifier
        profile = {"messages": ["START", "END", "MIDDLE"], "labels": ["Order_Start", "Order_End", "Other"]}
        if saved:
            profile["selected_model"] = saved
        original_examples = profile["messages"][:]
        prior_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            os.chdir(temporary)
            try:
                if not new:
                    Path("order_profiles.json").write_text(json.dumps({"Cam": profile}))
                Path("cam_runs.json").write_text(json.dumps([{"status":"complete", "lines":["outside", "START", "MIDDLE", "END", "tail"]}]))
                def upload():
                    uploads.append(True)
                    return {"cam_runs.json": b""}
                modules["google.colab"].files = types.SimpleNamespace(upload=upload, download=lambda path: downloads.append(str(path)))
                with patch.dict(sys.modules, modules), patch.object(builtins, "input", side_effect=answers), contextlib.redirect_stdout(io.StringIO()):
                    runpy.run_path(str(TARGET))
                saved_profiles = json.loads(Path("order_profiles.json").read_text())
                outputs = {p.name: json.loads(p.read_text()) for p in Path("results").glob("*.json")}
            finally:
                os.chdir(prior_cwd)
        return saved_profiles, outputs, uploads, downloads, original_examples

    def test_retest_same_upload_then_save_second_model(self):
        profiles, outputs, uploads, downloads, examples = self.execute(["existing", "Cam", "1", "test", "2", "save"])
        self.assertEqual(profiles["Cam"].get("selected_model"), "nearest_example")
        self.assertEqual(len(uploads), 1)
        self.assertEqual(len(outputs), 2)
        self.assertEqual(profiles["Cam"]["messages"], examples)
        for output in outputs.values():
            self.assertEqual(output[0]["orders"], [{"status":"complete", "lines":["START", "MIDDLE", "END"]}])
            self.assertEqual(output[0]["unassigned_lines"], ["outside", "tail"])

    def test_saved_model_is_default(self):
        profiles, outputs, uploads, downloads, _ = self.execute(["existing", "Cam", "", "save"], saved="linear_svm")
        self.assertEqual(profiles["Cam"]["selected_model"], "linear_svm")
        self.assertTrue(any("linear_svm" in name for name in outputs))

    def test_stop_does_not_replace_previous_choice(self):
        profiles, outputs, uploads, downloads, _ = self.execute(["existing", "Cam", "2", "stop"], saved="naive_bayes")
        self.assertEqual(profiles["Cam"]["selected_model"], "naive_bayes")

    def test_new_application_one_profile(self):
        profiles, outputs, uploads, downloads, _ = self.execute(["new", "NewApp", "START", "", "END", "", "MIDDLE", "", "3", "save"], new=True)
        self.assertEqual(list(profiles), ["NewApp"])
        self.assertEqual(profiles["NewApp"]["selected_model"], "linear_svm")


if __name__ == "__main__":
    unittest.main()
