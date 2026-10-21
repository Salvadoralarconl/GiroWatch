import unittest
import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import patch
from application_control import application_action
from application_control import cam_command


class ApplicationControlTests(unittest.TestCase):
    def setUp(self):
        self.controls_temp=tempfile.TemporaryDirectory()
        root=Path(self.controls_temp.name)
        source=Path(__file__).resolve().parents[1]
        shutil.copyfile(source/'cam_control.ps1',root/'cam_control.ps1')
        (root/'application_controls.json').write_text(json.dumps({'Cam':{
            'executable':r'C:\TestApps\Cam.exe','working_folder':r'C:\TestApps',
            'process_name':'Cam','window_title':'Fictional Cam','menu_name':'Actions',
            'run_name':'Run','close_timeout':10}}),encoding='utf-8')
        self.root_patch=patch('application_control.ROOT',root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.controls_temp.cleanup()

    def test_cam_uses_fixed_inline_command_without_changing_policy(self):
        from types import SimpleNamespace
        with patch('application_control.subprocess.run',return_value=SimpleNamespace(stdout='{"running":false}',returncode=0)) as run:
            self.assertFalse(cam_command('status')['running'])
            arguments=run.call_args.args[0]
            self.assertIn('-Command',arguments)
            self.assertNotIn('-File',arguments)
            self.assertNotIn('-ExecutionPolicy',arguments)
        with self.assertRaises(ValueError):
            cam_command('restart; unexpected')
    def test_real_applications_cannot_be_controlled(self):
        with self.assertRaises(ValueError):
            application_action({'application': 'UNITELLER', 'action': 'restart'})

    def test_cam_uses_named_external_control(self):
        with patch('application_control.cam_command',return_value={'ok':True}) as command:
            application_action({'application':'Cam','action':'run'})
            command.assert_called_once_with('run')

    def test_run_is_sent_only_to_test_interface(self):
        with patch('application_control.send_command', return_value={'ok': True}) as send:
            application_action({'application': 'Test Interface', 'action': 'run'})
            send.assert_called_once_with('run')

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            application_action({'application': 'Test Interface', 'action': 'delete'})

    def test_control_profile_save_and_reload(self):
        from web_service import WatchStore
        with tempfile.TemporaryDirectory() as directory:
            store=WatchStore(Path(directory))
            profile={'executable':r'C:\Apps\Example.exe','working_folder':r'C:\Apps','process_name':'Example','window_title':'Example','menu_name':'Actions','run_name':'Run','close_timeout':12}
            store.configure({'action':'save','section':'controls','application':'Example','profile':profile})
            reloaded=WatchStore(Path(directory))
            self.assertEqual(reloaded.profile('controls','Example')['profile'],profile)
            self.assertTrue(next(app for app in reloaded.state()['applications'] if app['name']=='Example')['control_profile'])
            with self.assertRaises(ValueError):
                store.configure({'action':'save','section':'controls','application':'Example','profile':{**profile,'close_timeout':0}})

    def test_log_view_reads_only_configured_folder(self):
        from web_service import WatchStore
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            logs=root/'logs';logs.mkdir()
            (logs/'20261021.log').write_text('original log line\n',encoding='utf-8')
            store=WatchStore(root)
            store.configure({'action':'save','section':'folders','application':'Example','profile':{'path':str(logs),'recursive':False,'extension':'.log'}})
            self.assertEqual(store.application_log('Example')['text'].splitlines(),['original log line'])
            with self.assertRaises(ValueError):
                store.application_log('../unconfigured')
