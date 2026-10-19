"""Shared nonblocking lock for the desktop app and its updater."""
import os
from pathlib import Path

class RuntimeLock:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.stream=open(Path(directory)/'desktop.lock','a+b')
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if os.fstat(self.stream.fileno()).st_size==0:
                self.stream.write(b'0'); self.stream.flush()
        except OSError:
            self.stream.close()
            raise RuntimeError('程序正在运行或更新，请先关闭它，再试一次。') from None
    def close(self):
        self.stream.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
