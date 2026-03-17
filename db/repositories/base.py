"""
Base Repository — abstract interface for data access.

Every repository has TWO implementations:
  1. In-memory (default, no database needed)
  2. PostgreSQL (when DATABASE_URL is set)

Services use the repository interface — they don't know
which implementation is active. This makes testing easy
and allows gradual migration from in-memory → PostgreSQL.
"""
from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Abstract base for all repositories.

    Subclasses implement either in-memory or database operations.
    The factory method `create()` chooses the right one based on config.
    """

    @abstractmethod
    def get(self, id: str) -> Optional[T]:
        """Get a single record by ID."""
        ...

    @abstractmethod
    def get_all(self, **filters) -> list[T]:
        """Get all records matching filters."""
        ...

    @abstractmethod
    def create(self, data: dict) -> T:
        """Create a new record."""
        ...

    @abstractmethod
    def update(self, id: str, data: dict) -> Optional[T]:
        """Update a record by ID."""
        ...

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Delete a record by ID."""
        ...
