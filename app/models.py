"""Alias: this module moved to fusion.web.models (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import models as _module

sys.modules[__name__] = _module
