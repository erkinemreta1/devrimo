"""The searchable corpus of public campus content, and how Scholar reads it."""

from app.knowledge.store import campus_vector_db, knowledge_available, reset_knowledge

__all__ = ["campus_vector_db", "knowledge_available", "reset_knowledge"]
