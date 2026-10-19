"""Release boundary regressions use only synthetic files, never installed drivers."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import release_tools as release


class ReleaseTests(unittest.TestCase):
    def test_runtime_resource_allowlist_excludes_analysis_and_private_evidence(self):
        self.assertTrue(all((release.ROOT/p).is_file() for p in release.RUNTIME_DATA))
        self.assertFalse(set(release.RUNTIME_DATA)&release.FORBIDDEN)
        self.assertIn('mappings.json',release.RUNTIME_DATA)

    def test_archive_has_one_complete_folder_and_rejects_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'bundle';bundle.mkdir()
            (bundle/'EtheriaAssistant.exe').write_bytes(b'synthetic executable')
            internal=bundle/'_internal';internal.mkdir();(internal/'mappings.json').write_text('{}')
            archive=release.package(bundle,root/'release','0.0.0','a'*40)
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()),{'EtheriaAssistant/EtheriaAssistant.exe','EtheriaAssistant/_internal/mappings.json'})
            m=json.loads((archive.parent/'release.json').read_text())
            self.assertEqual(m['sha256'],release.sha256(archive))
            for name in ('history.sqlite3','runtime.log.1','battle.pcapng','backup.db','mapping_evidence.json','npcap.exe','wpcap.dll'):
                bad=internal/name;bad.write_bytes(b'synthetic private data')
                with self.assertRaises(ValueError):release.package(bundle,root/'release','0.0.0','a'*40)
                bad.unlink()
            self.assertEqual(release.sha256(archive),m['sha256'])

    def test_capture_bundle_checks_hashes_architecture_and_rejects_driver_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);exe=bytearray(96);exe[:2]=b'MZ';exe[60:64]=(64).to_bytes(4,'little');exe[64:70]=b'PE\0\0\x64\x86'
            for name,content in [('dumpcap.exe',exe),('COPYING.txt',b'synthetic license'),('SOURCE.txt',b'synthetic source notice')]:
                (root/name).write_bytes(content)
            m={'version':'synthetic','source_url':'https://example.invalid/source','files':{p.name:release.sha256(p) for p in root.iterdir()}}
            manifest=root/'capture_manifest.json';manifest.write_text(json.dumps(m))
            self.assertEqual(len(release.capture_files(root)),4)
            for name in ('../outside.dll','C:/outside.dll','npcap.sys','wpcap.dll','Packet.dll'):
                bad=dict(m,files=dict(m['files'],**{name:'0'*64}));manifest.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):release.capture_files(root)
            manifest.write_text(json.dumps(m));(root/'dumpcap.exe').write_bytes(b'tampered')
            with self.assertRaises(ValueError):release.capture_files(root)

    def test_publish_rejects_changed_zip_before_any_gh_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'qt_app.py').write_text("VERSION='0.0.0'\n")
            bundle=root/'bundle';bundle.mkdir();(bundle/'EtheriaAssistant.exe').write_bytes(b'synthetic')
            archive=release.package(bundle,root/'release','0.0.0','a'*40);archive.write_bytes(b'changed')
            with patch.object(release,'ROOT',root),patch('release_tools.shutil.which',return_value='gh'),patch('release_tools.subprocess.run') as run:
                with self.assertRaises(ValueError):release.publish()
                run.assert_not_called()

    def test_publish_refuses_preexisting_tag_instead_of_misbinding_build(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'qt_app.py').write_text("VERSION='0.0.0'\n")
            bundle=root/'bundle';bundle.mkdir();(bundle/'EtheriaAssistant.exe').write_bytes(b'synthetic')
            release.package(bundle,root/'release','0.0.0','a'*40)
            with patch.object(release,'ROOT',root),patch('release_tools.shutil.which',return_value='gh'),patch('release_tools.subprocess.check_output',return_value='a'*40),patch('release_tools.subprocess.run') as run:
                run.side_effect=[subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0,stdout='{}',stderr='')]
                with self.assertRaisesRegex(ValueError,'Tag already exists'):release.publish()
                self.assertFalse(any('create' in call.args[0] for call in run.call_args_list))

if __name__=='__main__':unittest.main()
