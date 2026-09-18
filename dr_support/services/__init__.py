"""Stateless deployment-side services.

Each module in this package is a self-contained FastAPI app exposing a single
concern (currently only the model_api). They are mounted by the top-level
profile dispatcher in ``dr_support.app`` and never imported by the review API
directly.
"""
