"""Alias: this module moved to fusion.web.settings (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import settings as _module

sys.modules[__name__] = _module
