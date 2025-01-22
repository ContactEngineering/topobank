#!/usr/bin/env python
import os
import sys

from django.conf import settings

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topobank.settings.local")

    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django  # noqa
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )

        raise

    # https://github.com/microsoft/debugpy/issues/1392
    if settings.DEBUG:
        # Allows VSCode to attach to port for debugging breakpoint
        if os.environ.get('RUN_MAIN') or os.environ.get('WERKZEUG_RUN_MAIN'):
            try:
                import debugpy
                debugpy.listen(("0.0.0.0", 5678))
            except ImportError:
                print("Could not import debugpy. Debugger is not listening.")

    # This allows easy placement of apps within the interior
    # topobank directory.
    current_path = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(os.path.join(current_path, "topobank"))

    execute_from_command_line(sys.argv)
