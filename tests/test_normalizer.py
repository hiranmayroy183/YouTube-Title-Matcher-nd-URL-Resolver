"""
Unit tests for the normalizer module.
"""

import unittest
from normalizer import (
    strip_serial_prefix,
    clean_query_for_search,
    normalize_title,
    strip_fluff,
    extract_significant_tokens,
    split_artist_title,
)


class TestNormalizer(unittest.TestCase):

    def test_strip_serial_prefix(self):
        self.assertEqual(strip_serial_prefix("1. My Song"), "My Song")
        self.assertEqual(strip_serial_prefix("669. Song Name"), "Song Name")
        self.assertEqual(strip_serial_prefix("No Number"), "No Number")
        self.assertEqual(strip_serial_prefix("123.  Lots of spaces"), "Lots of spaces")

    def test_clean_query_for_search_underscores(self):
        raw = "10. A_R_Rahman_Hosanna_Best_Video_Ekk_Deewana_Tha"
        cleaned = clean_query_for_search(raw)
        self.assertNotIn("_", cleaned)
        self.assertIn("A R Rahman", cleaned)
        self.assertIn("Hosanna", cleaned)

    def test_clean_query_mp3_and_downloader_tags(self):
        raw = "70. Tere Vaaste (MP3_160K) 2"
        cleaned = clean_query_for_search(raw)
        self.assertEqual(cleaned, "Tere Vaaste")

        raw2 = "December'er Shohorey-converted 2"
        self.assertEqual(clean_query_for_search(raw2), "December'er Shohorey")

    def test_clean_query_split_on_mp3(self):
        raw = "647. Vida_Karo_Lyrical_Amar_Singh_Cha mkila_Diljit. mp3 Gao Gaan (feat. Paridhi)"
        cleaned = clean_query_for_search(raw)
        self.assertIn("Vida Karo", cleaned)
        self.assertNotIn("mp3", cleaned.lower())
        self.assertNotIn("Gao Gaan", cleaned)

    def test_clean_query_emojis(self):
        raw = "669. 🎵Benche Thakar Gaan _🎤Anupam Roy _ United Mix"
        cleaned = clean_query_for_search(raw)
        self.assertEqual(cleaned, "Benche Thakar Gaan Anupam Roy United Mix")

    def test_normalize_title_tolerance(self):
        t1 = normalize_title("Artist - My Song *")
        t2 = normalize_title("Artist: My Song")
        t3 = normalize_title("artist my song")
        self.assertEqual(t1, "artist my song")
        self.assertEqual(t2, "artist my song")
        self.assertEqual(t3, "artist my song")

    def test_strip_fluff(self):
        t = normalize_title("Artist - My Song (Official Video)")
        fluff_stripped = strip_fluff(t)
        self.assertEqual(fluff_stripped, "artist my song")

        t2 = normalize_title("Song Name Full Video Song HD 1080p")
        self.assertEqual(strip_fluff(t2), "song name")

    def test_extract_significant_tokens(self):
        tokens = extract_significant_tokens("a beautiful official song by arijit singh")
        self.assertIn("beautiful", tokens)
        self.assertIn("arijit", tokens)
        self.assertIn("singh", tokens)
        # Stopwords or fluff should not be in significant tokens
        self.assertNotIn("the", tokens)
        self.assertNotIn("official", tokens)
        self.assertNotIn("song", tokens)

    def test_split_artist_title(self):
        artist, title = split_artist_title("1. Anuv Jain - ALAG AASMAAN")
        self.assertEqual(artist, "Anuv Jain")
        self.assertEqual(title, "ALAG AASMAAN")


if __name__ == '__main__':
    unittest.main()
