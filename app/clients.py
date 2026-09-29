"""Alias: this module moved to fusion_first.web.clients (packaged with Fusion so `fusion serve` works)."""

import sys

from fusion_first.web import clients as _module

sys.modules[__name__] = _module
