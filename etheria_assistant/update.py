"""Incremental update of a clean Git checkout. Run after closing the app."""
import hashlib
import subprocess
import sys
from pathlib import Path
from runtime_lock import RuntimeLock
from storage import data_directory


def run(*args, cwd):
    return subprocess.run(list(args),cwd=cwd,check=True,text=True,encoding='utf-8',
                          errors='replace',stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.strip()


def update(directory=None, data_dir=None):
    directory=Path(directory or Path(__file__).resolve().parent)
    with RuntimeLock(data_dir or data_directory()):
        root=Path(run('git','rev-parse','--show-toplevel',cwd=directory))
        if run('git','status','--porcelain',cwd=root):
            raise RuntimeError('源码有本地改动。请先提交或保存改动，更新不会覆盖它们。')
        branch=run('git','symbolic-ref','--short','HEAD',cwd=root)
        upstream=run('git','rev-parse','--abbrev-ref','@{upstream}',cwd=root)
        before=run('git','rev-parse','HEAD',cwd=root)
        print('Updating '+branch+' from '+upstream,flush=True)
        run('git','pull','--ff-only',cwd=root)
        after=run('git','rev-parse','HEAD',cwd=root)
        # UI and parser changes need no dependency installation.
        requirements=directory/'requirements.txt'
        digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
        marker=directory/'.installed-requirements.sha256'
        dependencies_changed=not marker.exists() or marker.read_text().strip()!=digest
        if dependencies_changed:
            subprocess.run([sys.executable,'-m','pip','install','-r',str(requirements)],check=True,cwd=directory)
            marker.write_text(digest+'\n')
        if before!=after or dependencies_changed:
            subprocess.run([sys.executable,'-m','unittest','discover','-v'],check=True,cwd=directory)
        print(('Already current: ' if before==after else 'Updated: ')+after[:12],flush=True)
        return before,after

if __name__=='__main__':
    try:update()
    except (RuntimeError,subprocess.CalledProcessError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        if isinstance(exc,subprocess.CalledProcessError):print(exc.stderr or '',file=sys.stderr)
        print('Update did not finish. Keep this window open to read the error.',file=sys.stderr)
        sys.exit(1)
