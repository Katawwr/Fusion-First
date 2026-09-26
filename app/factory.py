"""Alias: this module moved to fusion.web.factory (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion.web import factory as _module

sys.modules[__name__] = _module
