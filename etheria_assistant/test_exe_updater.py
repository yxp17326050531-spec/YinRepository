import tempfile
import unittest
import zipfile
from pathlib import Path
from exe_updater import check,allowed_url,extract_checked

class UpdaterTests(unittest.TestCase):
    def release(self,version):
        return {'tag_name':'v'+version,'assets':[{'name':'release.json'},{'name':'EtheriaAssistant-'+version+'-windows-x64.zip'}]}
    def test_channels_versions_and_missing_assets(self):
        rows=[self.release('2.11.16-calc-test'),self.release('9.0.0')]
        self.assertEqual(check('2.11.15-calc-test',rows)['version'],'2.11.16-calc-test')
        self.assertEqual(check('2.11.15',rows)['version'],'9.0.0')
        self.assertIsNone(check('2.11.16-calc-test',rows))
        rows[0]['draft']=True;self.assertIsNone(check('2.11.15-calc-test',rows))
    def test_only_project_https_downloads(self):
        self.assertTrue(allowed_url('https://github.com/yxp17326050531-spec/YinRepository/releases/download/v1/a.zip'))
        for value in ['http://github.com/x','https://evil.com/x','https://github.com/other/repo/releases/download/v1/a.zip','https://user:pass@github.com/x']:
            self.assertFalse(allowed_url(value))
    def test_extract_rejects_traversal_and_user_database(self):
        for name in ['EtheriaAssistant/../../bad.exe','EtheriaAssistant/history.sqlite3','EtheriaAssistant/evil:stream']:
            with tempfile.TemporaryDirectory() as tmp:
                archive=Path(tmp)/'a.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'bad')
                with self.assertRaises(ValueError):extract_checked(archive,Path(tmp)/'stage')
    def test_valid_bundle_and_wrong_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'a.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('EtheriaAssistant/EtheriaAssistant.exe',b'MZtest');z.writestr('EtheriaAssistant/_internal/test.txt','ok')
            root=extract_checked(archive,Path(tmp)/'stage');self.assertTrue((root/'EtheriaAssistant.exe').exists())

    def test_worker_uses_actual_bundle_layout_even_with_inherited_portable_env(self):
        from unittest.mock import patch
        from exe_updater import launch_worker
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict('os.environ',{'ETHERIA_PORTABLE_ROOT':tmp}),patch('exe_updater.subprocess.Popen') as popen:
                launch_worker(tmp,tmp)
                self.assertEqual(popen.call_args.args[0][0],str(Path(tmp)/'worker/EtheriaAssistant.exe'))
                import os
                self.assertEqual(popen.call_args.args[0][-1],str(os.getpid()))
