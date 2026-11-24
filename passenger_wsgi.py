"""Entry point for Passenger / cPanel "Setup Python App".

Set the application startup file to passenger_wsgi.py and the
entry point to `application`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from rally import create_app  # noqa: E402

application = create_app()
