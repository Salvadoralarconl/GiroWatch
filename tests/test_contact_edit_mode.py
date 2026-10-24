import tempfile
import unittest
from pathlib import Path
from local_test_mode import LocalTestStore, allow_test_request


class ContactEditModeTests(unittest.TestCase):
    def test_contact_edits_remain_in_isolated_test_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalTestStore(Path(folder))
            try:
                allow_test_request('POST', '/api/contacts')
                store.contacts({'application': 'TEST CAM', 'contacts': [{'payer': 'Test support'}]})
                self.assertTrue((Path(folder) / 'web_data' / 'contacts.json').is_file())
            finally:
                store.close()
