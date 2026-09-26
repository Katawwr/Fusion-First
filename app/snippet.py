"""Alias: this module moved to fusion.web.snippet (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import snippet as _module

sys.modules[__name__] = _module
