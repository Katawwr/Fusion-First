"""Alias: this module moved to fusion.web.sse (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import sse as _module

sys.modules[__name__] = _module
