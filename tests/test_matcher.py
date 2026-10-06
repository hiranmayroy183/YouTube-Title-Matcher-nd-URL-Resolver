"""
Unit tests for the TitleMatcher and scoring system.
"""

import unittest
from matcher import TitleMatcher


class TestMatcher(unittest.TestCase):

    def setUp(self):
        self.matcher = TitleMatcher(confidence_threshold=0.65)

    def test_exact_match(self):
        score = self.matcher.calculate_confidence(
            "Artist - My Song",
            "Artist - My Song",
            "Artist"
        )
        self.assertEqual(score, 1.0)

    def test_fluff_tolerance(self):
        score = self.matcher.calculate_confidence(
            "Artist - My Song *",
            "Artist - My Song (Official Video)",
            "Artist Channel"
        )
        self.assertGreaterEqual(score, 0.90)

    def test_punctuation_and_casing_tolerance(self):
        score = self.matcher.calculate_confidence(
            "artist: my song",
            "Artist - My Song",
            ""
        )
        self.assertGreaterEqual(score, 0.90)

    def test_underscores_and_serial_tolerance(self):
        score = self.matcher.calculate_confidence(
            "1. 'Sooraj Dooba Hain' FULL VIDEO SONG_ Arijit singh Aditi Singh Sharma _ T-SERIES",
            "'Sooraj Dooba Hain' FULL VIDEO SONG | Arijit singh Aditi Singh Sharma | T-SERIES",
            "T-Series"
        )
        self.assertGreaterEqual(score, 0.95)

    def test_unrelated_video_rejection(self):
        # Video shares one common word ('Song') but is completely different
        score = self.matcher.calculate_confidence(
            "Anuv Jain - Alag Aasmaan",
            "Completely Different Pop Song 2024",
            "Other Label"
        )
        self.assertLess(score, 0.40)

    def test_shared_artist_different_song_rejection(self):
        # Both by Arijit Singh, but completely different songs
        score = self.matcher.calculate_confidence(
            "Arijit Singh - Tum Hi Ho",
            "Arijit Singh - Channa Mereya (Official Video)",
            "Sony Music India"
        )
        # Should not meet the threshold of 0.65
        self.assertLess(score, 0.60)

    def test_select_best_match_ranking(self):
        candidates = [
            {"video_id": "vid1", "title": "Random Song by Arijit Singh", "channel": "Music"},
            {"video_id": "vid2", "title": "Sooraj Dooba Hain Official Video | Arijit Singh", "channel": "T-Series"},
            {"video_id": "vid3", "title": "Sooraj Dooba Hain (Cover)", "channel": "Covers"},
        ]
        best_cand, best_score, is_match = self.matcher.select_best_match(
            "1. 'Sooraj Dooba Hain' FULL VIDEO SONG_ Arijit singh Aditi Singh Sharma _ T-SERIES",
            candidates
        )
        self.assertTrue(is_match)
        self.assertEqual(best_cand["video_id"], "vid2")
        self.assertGreaterEqual(best_score, 0.85)

    def test_below_threshold_returns_not_found(self):
        candidates = [
            {"video_id": "vid1", "title": "Some Unrelated Video 1", "channel": "Chan1"},
            {"video_id": "vid2", "title": "Another Irrelevant Clip", "channel": "Chan2"},
        ]
        best_cand, best_score, is_match = self.matcher.select_best_match(
            "Unknown Song by Secret Artist",
            candidates
        )
        self.assertFalse(is_match)
        self.assertLess(best_score, 0.65)


if __name__ == '__main__':
    unittest.main()
