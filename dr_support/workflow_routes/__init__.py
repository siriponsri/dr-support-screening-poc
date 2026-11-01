"""Route groups of the review workflow API, installed in order by `workflow.install_workflow`.

- `cases`: case list, case detail, comparison
- `images`: image bytes (original, display, analysis area, mask overlay)
- `review`: grade review, queue actions, AI lesion ROI decisions
- `confirm`: admission review, patient/eye resolver review, Confirm Image
- `annotations`: human annotation set, completeness, annotations derived from AI
- `cvat`: CVAT send/sync, export, manual import
"""
