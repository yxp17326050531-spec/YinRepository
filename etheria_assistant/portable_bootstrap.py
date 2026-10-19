"""App-local Windows runtime entry point, including early startup diagnostics."""
from pathlib import Path
import os
import runpy
import sys
import traceback


def main():
    try:
        runpy.run_path(str(Path(__file__).with_name('app.py')),run_name='__main__')
    except SystemExit as exc:
        return exc.code if isinstance(exc.code,int) else 0 if exc.code is None else 1
    except Exception:
        error=traceback.format_exc()
        try:
            directory=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'EtheriaAssistant'
            directory.mkdir(parents=True,exist_ok=True)
            (directory/'startup-error.log').write_text(error,encoding='utf-8')
        except OSError:pass
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'启动失败，请查看本机 EtheriaAssistant 数据目录的 startup-error.log。\n\n'+str(error[-1500:]),'伊瑟 · 对局助手',0x10)
        elif sys.stderr:print(error,file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
