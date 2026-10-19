"""Launch the PySide6 dark desktop application."""
import sys
if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
        from release_smoke import run
        sys.exit(run(sys.argv[2]))
    try:
        from qt_app import main
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith('PySide6'):
            print('Missing PySide6. Run install_windows.cmd first, or pip install -r requirements.txt')
        raise
    sys.exit(main())
