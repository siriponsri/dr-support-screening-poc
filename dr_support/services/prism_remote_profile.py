"""Declared QA candidate; hard disabled before any app/DB/provider construction."""
PROFILE = 'qa-prism-bound-remote-v2-disabled'
QUALIFIED = False
BLOCKERS = (
    'No shared authority owns every app case/admission/source/Workspace/provider writer',
    'Existing bearer connection has no reviewed prepare-source/forward-authority principal mapping',
    'Owned executor, authenticated transport deadlines and real native-ROI initialization unqualified',
)


def reject_disabled_profile(value):
    if value == PROFILE:
        raise RuntimeError('REMOTE_ENTRY_FENCE_PROFILE_NOT_QUALIFIED')


def register_isolated_remote_profile(*args, **kwargs):
    raise RuntimeError('REMOTE_ENTRY_FENCE_PROFILE_NOT_QUALIFIED')
