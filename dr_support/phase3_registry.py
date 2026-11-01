"""Old milestone name of `dr_support.capability_registry`; kept so existing imports keep working.

Importing this module returns the renamed module itself (same object), so attributes and test
patches behave exactly as before.
"""
import sys

from dr_support import capability_registry as _module

sys.modules[__name__] = _module
