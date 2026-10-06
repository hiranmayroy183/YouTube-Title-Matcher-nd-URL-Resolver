"""
Unit tests for the YouTubeSearcher response parsing and dataclasses.
"""

import unittest
from searcher import YouTubeSearcher, SearchResult


class TestYouTubeSearcher(unittest.TestCase):

    def setUp(self):
        self.searcher = YouTubeSearcher()

    def test_search_result_dataclass(self):
        res = SearchResult(
            video_id="dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            channel="Rick Astley",
            duration="3:33"
        )
        self.assertEqual(res.url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        d = res.to_dict()
        self.assertEqual(d["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        res2 = SearchResult.from_dict(d)
        self.assertEqual(res2.video_id, "dQw4w9WgXcQ")

    def test_extract_innertube_videos(self):
        # Sample simulated InnerTube response payload
        sample_payload = {
            "contents": {
                "twoColumnSearchResultsRenderer": {
                    "primaryContents": {
                        "sectionListRenderer": {
                            "contents": [
                                {
                                    "itemSectionRenderer": {
                                        "contents": [
                                            {
                                                "videoRenderer": {
                                                    "videoId": "test_id_123",
                                                    "title": {
                                                        "runs": [{"text": "Sample Song Title"}]
                                                    },
                                                    "ownerText": {
                                                        "runs": [{"text": "Sample Artist"}]
                                                    },
                                                    "lengthText": {
                                                        "simpleText": "4:15"
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
        results = self.searcher._extract_innertube_videos(sample_payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].video_id, "test_id_123")
        self.assertEqual(results[0].title, "Sample Song Title")
        self.assertEqual(results[0].channel, "Sample Artist")
        self.assertEqual(results[0].duration, "4:15")
        self.assertEqual(results[0].url, "https://www.youtube.com/watch?v=test_id_123")


if __name__ == '__main__':
    unittest.main()
