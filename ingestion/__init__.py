"""
JobIntel - Ingestion Module
Handles data acquisition from Jobvetta, IndianAPI, and future API sources.
"""

from ingestion.base import BaseJobSource
from ingestion.jobvetta_client import JobvettaClient
from ingestion.indianapi_client import IndianAPIClient
from ingestion.cleaner import TextCleaner
from ingestion.deduplicator import Deduplicator
from ingestion.normalizer import JobNormalizer
from ingestion.runner import IngestionRunner

__all__ = [
    "BaseJobSource",
    "JobvettaClient",
    "IndianAPIClient",
    "TextCleaner",
    "Deduplicator",
    "JobNormalizer",
    "IngestionRunner",
]
