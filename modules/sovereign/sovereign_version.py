"""Authoritative SOVEREIGN product version.

All runtime components import this module.  Packaging metadata derives its
PEP 440 value from here; UI and HTTP clients obtain the display value from the
runtime health endpoint rather than embedding a second product version.
"""

PRODUCT_VERSION = "3.1.2"
PEP440_VERSION = "3.1.2"
RELEASE_CHANNEL = "baseline-development"
