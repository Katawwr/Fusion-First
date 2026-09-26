"""Alias: this module moved to fusion.web.clients (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import clients as _module

sys.modules[__name__] = _module
