"""Exercise real incremental updates against an isolated local Git remote."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from runtime_lock import RuntimeLock
from update import update

def git(path,*args):
    return subprocess.run(['git','-C',str(path),*args],check=True,capture_output=True,text=True).stdout.strip()

class Updates(unittest.TestCase):
    def test_fast_forward_repeat_dirty_tree_and_lock(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); remote=root/'remote.git'; producer=root/'producer'; client=root/'client'; data=root/'data'
            subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
            subprocess.run(['git','clone',str(remote),str(producer)],check=True,capture_output=True)
            git(producer,'config','user.name','Test');git(producer,'config','user.email','test@example.invalid')
            (producer/'.gitignore').write_text('.installed-requirements.sha256\n__pycache__/\n')
            (producer/'requirements.txt').write_text('');(producer/'app.py').write_text('v1')
            (producer/'test_smoke.py').write_text('import unittest\nclass Smoke(unittest.TestCase):\n def test_load(self): self.assertTrue(True)\n')
            git(producer,'add','.');git(producer,'commit','-m','initial');git(producer,'push','origin','HEAD')
            subprocess.run(['git','clone',str(remote),str(client)],check=True,capture_output=True)
            (client/'.installed-requirements.sha256').write_text(hashlib.sha256(b'').hexdigest())
            (producer/'app.py').write_text('v2');git(producer,'add','.');git(producer,'commit','-m','change');git(producer,'push')
            before,after=update(client,data);self.assertNotEqual(before,after);self.assertEqual((client/'app.py').read_text(),'v2')
            self.assertEqual(update(client,data),(after,after))
            (client/'app.py').write_text('my edits')
            with self.assertRaises(RuntimeError):update(client,data)
            self.assertEqual((client/'app.py').read_text(),'my edits')
            with RuntimeLock(data):
                with self.assertRaises(RuntimeError):update(client,data)
