"""Ten deterministic quantitative models powering the Manhuaju Autopilot v2.0 whitepaper.

Every public function takes ``rng: numpy.random.Generator`` as the *only* source
of randomness. Callers are responsible for seeding (default
``research.whitepaper.SEED``).
"""

from __future__ import annotations
