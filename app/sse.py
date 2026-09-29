"""Alias: this module moved to fusion_first.web.sse (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion_first.web import sse as _module

sys.modules[__name__] = _module
