import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TARGET = Path(__file__).resolve().parents[1] / 'local_files.py'


class LocalFilesTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TARGET.exists(), 'Local file access is not implemented yet.')
        spec = importlib.util.spec_from_file_location('local_files', TARGET)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_selects_existing_file_without_copying_or_changing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'test log.log'
            path.write_text('original log')
            with patch('builtins.input', return_value=f'"{path}"'):
                result = self.module.files.upload()
            self.assertEqual(list(result), [str(path.resolve())])
            self.assertEqual(path.read_text(), 'original log')
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_missing_input_reprompts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'runs.json'
            path.write_text('[]')
            with patch('builtins.input', side_effect=['does-not-exist.log', str(path)]):
                result = self.module.files.upload()
            self.assertEqual(list(result), [str(path.resolve())])

    def test_download_reports_existing_local_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.json'
            path.write_text('[]')
            with patch('builtins.print') as display:
                self.module.files.download(str(path))
            self.assertIn(str(path.resolve()), display.call_args[0][0])
            self.assertEqual(path.read_text(), '[]')


if __name__ == '__main__':
    unittest.main()
