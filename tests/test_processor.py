"""
Unit tests for BatchProcessor file generation and resume.
"""

import tempfile
import unittest
from pathlib import Path

from processor import BatchProcessor, ProcessResult


class TestProcessorFileWriting(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.links_file = self.temp_path / "test_links.txt"
        self.urls_file = self.temp_path / "test_urls.txt"
        self.ckpt_file = self.temp_path / "test_checkpoint.json"

        self.processor = BatchProcessor(
            output_file=str(self.links_file),
            urls_file=str(self.urls_file),
            checkpoint_file=str(self.ckpt_file),
            resume=False,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_writes_both_links_and_urls_files(self):
        results = [
            ProcessResult(
                index=1,
                raw_title="1. Artist - Song One",
                url="https://www.youtube.com/watch?v=vid1",
                confidence=0.98,
                is_match=True,
            ),
            ProcessResult(
                index=2,
                raw_title="2. Unknown Artist - Obscure Song",
                url="NOT_FOUND",
                confidence=0.30,
                is_match=False,
            ),
        ]

        self.processor._write_links_file(results)

        # Check links.txt
        self.assertTrue(self.links_file.exists())
        with open(self.links_file, "r", encoding="utf-8") as f:
            link_lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(link_lines), 2)
        self.assertEqual(link_lines[0], "1. Artist - Song One | https://www.youtube.com/watch?v=vid1")
        self.assertEqual(link_lines[1], "2. Unknown Artist - Obscure Song | NOT_FOUND")

        # Check urls.txt
        self.assertTrue(self.urls_file.exists())
        with open(self.urls_file, "r", encoding="utf-8") as f:
            url_lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(url_lines), 2)
        self.assertEqual(url_lines[0], "https://www.youtube.com/watch?v=vid1")
        self.assertEqual(url_lines[1], "NOT_FOUND")


if __name__ == '__main__':
    unittest.main()
