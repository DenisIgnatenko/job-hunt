"""
Abstract scraper (OCP): new sources extend this without touching existing code.
"""

from abc import ABC, abstractmethod

from src.database.repository import Vacancy


class BaseScraper(ABC):
 @abstractmethod
 def fetch(self) -> list[Vacancy]:
  """Fetch vacancies from the source. Returns unsaved Vacancy objects."""
  ...
