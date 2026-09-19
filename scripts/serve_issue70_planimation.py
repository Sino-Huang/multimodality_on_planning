"""Serve the installed Planimation clone on localhost without writing into its source tree."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
from wsgiref.simple_server import make_server

if TYPE_CHECKING:
    from _typeshed.wsgi import WSGIApplication


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18092)
    parser.add_argument("--workers", type=int, default=1, help="isolated backend processes on consecutive ports")
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".slim/clonedeps/repos/planimation__backend/server",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be positive")
    if args.workers == 1:
        serve(args.port, args.backend_root)
        return
    processes = [
        multiprocessing.get_context("spawn").Process(target=serve, args=(args.port + index, args.backend_root))
        for index in range(args.workers)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            if process.pid is not None:
                process.join()


def serve(port: int, backend_root: Path) -> None:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(backend_root.resolve()))
    os.environ["DJANGO_SETTINGS_MODULE"] = "server.settings"
    from django.conf import settings
    from django.core.wsgi import get_wsgi_application

    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
    application = cast("WSGIApplication", get_wsgi_application())
    with make_server("127.0.0.1", port, application) as server:
        print(f"Planimation localhost backend ready at http://127.0.0.1:{port}; Ctrl-C stops it.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
