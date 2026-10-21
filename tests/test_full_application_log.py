import tempfile
import unittest
from pathlib import Path
from web_service import WatchStore, write_json


class FullLogTests(unittest.TestCase):
    def test_log_larger_than_two_megabytes_includes_first_and_last_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            logs=root/'logs';logs.mkdir()
            text='FIRST LOG LINE\n'+'sample activity\n'*150000+'LAST LOG LINE\n'
            (logs/'20261021.log').write_bytes(text.encode('utf-8'))
            write_json(root/'folder_profiles.json',{'TEST CAM':{'path':str(logs),'recursive':False,'extension':'.log'}})
            result=WatchStore(root).application_log('TEST CAM')
            self.assertEqual(result['text'],text)
            self.assertFalse(result['truncated'])
