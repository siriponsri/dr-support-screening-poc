"""Old milestone name of `dr_support.services.qualification_attestation`; kept so existing imports keep working.

Importing this module returns the renamed module itself (same object), so attributes and test
patches behave exactly as before.
"""
# providers/prism_bound.py (provenance-pinned, must not be edited) still imports this name.
import sys

from dr_support.services import qualification_attestation as _module

sys.modules[__name__] = _module
