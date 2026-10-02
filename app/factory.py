"""Alias for fusion_first.web.factory (used by app/modal_app.py and `uvicorn app.factory:create_app`)."""

import sys

from fusion_first.web import factory as _module

sys.modules[__name__] = _module
