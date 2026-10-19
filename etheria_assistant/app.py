"""Launch the PySide6 dark desktop application."""
import sys
if __name__ == '__main__':
    try:
        from qt_app import main
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith('PySide6'):
            print('Missing PySide6. Run install_windows.cmd first, or pip install -r requirements.txt')
        raise
    sys.exit(main())
