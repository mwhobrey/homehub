"""Local development server. Prefer: .venv\\Scripts\\python.exe run.py"""
from __future__ import annotations

import os
import signal
import sys

from app import create_app, stop_background_jobs

app = create_app()


def _dev_run_kwargs() -> dict:
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() not in ('0', 'false', 'no')
    rel = os.environ.get('FLASK_USE_RELOADER', 'auto').lower()
    if rel == 'auto':
        # Werkzeug reloader + selectors often throws WinError 10038 on Windows.
        use_reloader = debug and os.name != 'nt'
    else:
        use_reloader = rel in ('1', 'true', 'yes')
    return {
        'host': '0.0.0.0',
        'port': port,
        'debug': debug,
        'use_reloader': use_reloader,
    }


def _install_interrupt_handlers() -> None:
    def _shutdown(signum, frame):
        print('\nStopping HomeHub…', flush=True)
        stop_background_jobs()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, _shutdown)


if __name__ == '__main__':
    if not getattr(sys, 'frozen', False):
        in_venv = hasattr(sys, 'real_prefix') or sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
        if not in_venv and os.path.isdir(os.path.join(os.path.dirname(__file__), '.venv')):
            print(
                'Tip: use the project venv so deps match: .venv\\Scripts\\python.exe run.py',
                file=sys.stderr,
            )
    opts = _dev_run_kwargs()
    if opts['debug'] and not opts['use_reloader']:
        print(
            'Debug on, auto-reload off (stable on Windows). '
            'Set FLASK_USE_RELOADER=1 to force reload, or restart after code changes.',
            file=sys.stderr,
        )
    if os.environ.get('HOMEHUB_DISABLE_BACKGROUND_JOBS', '').lower() in ('1', 'true', 'yes'):
        print('Background calendar sync disabled (HOMEHUB_DISABLE_BACKGROUND_JOBS).', file=sys.stderr)
    _install_interrupt_handlers()
    try:
        app.run(**opts)
    except (KeyboardInterrupt, SystemExit):
        stop_background_jobs()
        raise SystemExit(0) from None
