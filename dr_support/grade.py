"""Stable clinician-facing DR grade vocabulary and review states."""

DR_GRADE_LABELS = {
    0: "No apparent DR",
    1: "Mild NPDR",
    2: "Moderate NPDR",
    3: "Severe NPDR",
    4: "Proliferative DR (PDR)",
}

GRADE_STATUS_NOT_REVIEWED = "NOT_REVIEWED"
GRADE_STATUS_CONFIRMED = "CONFIRMED"
GRADE_STATUS_UNGRADABLE = "UNGRADABLE"
GRADE_STATUS_NEEDS_SECOND_REVIEW = "NEEDS_SECOND_REVIEW"
GRADE_STATUS_LEGACY_UNKNOWN = "UNKNOWN"


def grade_label(grade: object) -> str | None:
    """Return a clinician-facing label without changing numeric compatibility data."""

    if isinstance(grade, int) and not isinstance(grade, bool):
        return DR_GRADE_LABELS.get(grade)
    return None
