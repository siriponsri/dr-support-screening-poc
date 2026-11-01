"""Old milestone name of `dr_support.contracts.model_context`; kept so existing imports keep working.

Importing this module returns the renamed module itself (same object), so attributes and test
patches behave exactly as before.
"""
import sys

from dr_support.contracts import model_context as _module

sys.modules[__name__] = _module
