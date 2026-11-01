"""Old milestone name of `dr_support.services.workspace_context`; kept so existing imports keep working.

Importing this module returns the renamed module itself (same object), so attributes and test
patches behave exactly as before.
"""
import sys

from dr_support.services import workspace_context as _module

sys.modules[__name__] = _module
