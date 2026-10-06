"""
Unit tests for the SearchCache module.
"""

import os
import tempfile
import unittest
from pathlib import Path

from cache import SearchCache


class TestSearchCache(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = Path(self.temp_dir.name) / "test_cache.json"
        self.cache = SearchCache(cache_file=str(self.cache_file))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cache_miss_and_hit(self):
        self.assertIsNone(self.cache.get("non_existent_query"))

        sample_results = [
            {"video_id": "abc12345", "title": "Test Title", "channel": "Test Channel"}
        ]
        self.cache.set("my test query", sample_results)
        self.cache.flush()

        # Should retrieve regardless of casing or extra spaces
        retrieved = self.cache.get("MY TEST QUERY")
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["video_id"], "abc12345")

    def test_persistence_across_instances(self):
        self.cache.set("query 1", [{"video_id": "v1", "title": "Title 1"}])
        self.cache.flush()

        # Reopen with new cache instance
        cache2 = SearchCache(cache_file=str(self.cache_file))
        retrieved = cache2.get("query 1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved[0]["video_id"], "v1")


if __name__ == '__main__':
    unittest.main()
