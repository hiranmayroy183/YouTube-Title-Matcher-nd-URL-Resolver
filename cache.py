"""
Thread-safe persistent cache for YouTube search results.
Prevents repeated queries, speeds up re-runs, and enables instant resume.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any

from config import DEFAULT_CACHE_FILE

logger = logging.getLogger("yt_matcher.cache")


class SearchCache:
    """
    Persistent JSON cache mapping normalized queries to search result dictionaries.
    Thread-safe and uses atomic writes to prevent file corruption.
    """

    def __init__(self, cache_file: str = DEFAULT_CACHE_FILE, enabled: bool = True):
        self.cache_file = Path(cache_file)
        self.enabled = enabled
        self._lock = threading.Lock()
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._dirty_count = 0
        self._save_interval = 25  # Save to disk every 25 updates

        if self.enabled:
            self._load()

    def _load(self) -> None:
        """Loads cache data from disk if it exists."""
        if not self.cache_file.exists():
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            logger.info(f"Loaded {len(self._cache)} cached searches from {self.cache_file}")
        except Exception as e:
            logger.warning(f"Could not load cache from {self.cache_file}: {e}")
            self._cache = {}

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieves cached results for a query."""
        if not self.enabled:
            return None
        with self._lock:
            return self._cache.get(query.strip().lower())

    def set(self, query: str, results: List[Dict[str, Any]]) -> None:
        """Stores search results for a query and periodically persists to disk."""
        if not self.enabled:
            return
        key = query.strip().lower()
        with self._lock:
            self._cache[key] = results
            self._dirty_count += 1
            if self._dirty_count >= self._save_interval:
                self._flush_locked()

    def flush(self) -> None:
        """Persists all dirty cache entries to disk."""
        if not self.enabled:
            return
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        """Internal flush implementation protected by lock."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.cache_file)
            self._dirty_count = 0
        except Exception as e:
            logger.error(f"Failed to persist cache to {self.cache_file}: {e}")

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
