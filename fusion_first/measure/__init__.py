"""Fusion measurement harness: run the real test→detect→fix loop against a live model (via the
subscription CLI or an API key), record it to cassettes, and compute honest numbers.

This is the "self-improving loop" surface: measure sufficiency (are the attacks strong enough?),
judge accuracy (Bar A vs the oracle), and before/after (Bar B): using real model calls, then
replay the recorded cassettes offline for free. Pure core: no `modal`, no SDK import at module load.
"""
