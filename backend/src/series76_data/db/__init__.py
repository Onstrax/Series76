"""Database access layer for Spec 1.

Exposes the SQLAlchemy engine/session factory and the typed, parameterized
repository surface. No code path here executes free-form, model-generated SQL
(Req 7.4).
"""
