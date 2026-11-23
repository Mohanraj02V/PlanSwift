#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    backend_dir = Path(__file__).resolve().parent
    for p in (str(root_dir), str(backend_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
