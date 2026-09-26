"""Alias: this module moved to fusion.web.persistence (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import persistence as _module

sys.modules[__name__] = _module
