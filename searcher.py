"""
Direct YouTube Search Client.
Does not require the official YouTube Data API or any browser automation.
Uses YouTube's native web client endpoint (InnerTube API) with HTML scrape fallback,
connection pooling, exponential backoff retries, and rate limiting.
"""

import json
import logging
import random
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any

import requests

from config import (
    INNERTUBE_SEARCH_URL,
    HTML_SEARCH_URL,
    USER_AGENTS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_DELAY,
)

logger = logging.getLogger("yt_matcher.searcher")


@dataclass
class SearchResult:
    video_id: str
    title: str
    channel: str = ""
    duration: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['url'] = self.url
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        return cls(
            video_id=data.get('video_id', ''),
            title=data.get('title', ''),
            channel=data.get('channel', ''),
            duration=data.get('duration', ''),
        )


class YouTubeSearcher:
    """
    Lightweight, high-performance YouTube search client.
    Thread-safe and equipped with automatic retries and rate limiting.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_REQUEST_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self._thread_local = threading.local()

    def _get_session(self) -> requests.Session:
        """Returns or creates a thread-local requests Session with HTTP keep-alive."""
        if not hasattr(self._thread_local, "session"):
            session = requests.Session()
            session.headers.update({
                "User-Agent": random.choice(USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            })
            self._thread_local.session = session
        return self._thread_local.session

    def _extract_innertube_videos(self, data: Any, limit: int = 10) -> List[SearchResult]:
        """Recursively walks InnerTube response JSON and extracts videoRenderer items."""
        results: List[SearchResult] = []
        seen_ids = set()

        def recurse(node: Any):
            if len(results) >= limit:
                return
            if isinstance(node, dict):
                if "videoRenderer" in node:
                    vr = node["videoRenderer"]
                    vid = vr.get("videoId")
                    if vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        title = ""
                        if "title" in vr and "runs" in vr["title"]:
                            title = "".join(r.get("text", "") for r in vr["title"]["runs"])
                        elif "title" in vr and "simpleText" in vr["title"]:
                            title = vr["title"]["simpleText"]

                        channel = ""
                        if "ownerText" in vr and "runs" in vr["ownerText"]:
                            channel = "".join(r.get("text", "") for r in vr["ownerText"]["runs"])
                        elif "longBylineText" in vr and "runs" in vr["longBylineText"]:
                            channel = "".join(r.get("text", "") for r in vr["longBylineText"]["runs"])

                        duration = ""
                        if "lengthText" in vr and "simpleText" in vr["lengthText"]:
                            duration = vr["lengthText"]["simpleText"]

                        if title:
                            results.append(SearchResult(
                                video_id=vid,
                                title=title,
                                channel=channel,
                                duration=duration
                            ))
                for v in node.values():
                    recurse(v)
            elif isinstance(node, list):
                for item in node:
                    recurse(item)

        recurse(data)
        return results

    def _search_innertube(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Searches YouTube using the native InnerTube web endpoint."""
        session = self._get_session()
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240101.00.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "query": query,
        }

        resp = session.post(
            INNERTUBE_SEARCH_URL,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return self._extract_innertube_videos(data, limit=limit)

    def _search_html(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Fallback search using YouTube HTML search page scraping."""
        session = self._get_session()
        url = f"{HTML_SEARCH_URL}?search_query={urllib.parse.quote(query)}"
        resp = session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        html = resp.text

        pattern = r'var ytInitialData = ({.*?});</script>'
        m = re.search(pattern, html)
        if not m:
            pattern = r'ytInitialData\s*=\s*({.+?});'
            m = re.search(pattern, html)
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
            return self._extract_innertube_videos(data, limit=limit)
        except Exception as e:
            logger.warning(f"Error parsing HTML fallback data: {e}")
            return []

    def search(self, query: str, limit: int = 8) -> List[SearchResult]:
        """
        Executes a YouTube search for the given query.
        Handles rate limiting, retries with exponential backoff, and fallback to HTML scraping.
        """
        if not query.strip():
            return []

        # Polite rate-limiting delay
        if self.request_delay > 0:
            time.sleep(self.request_delay + random.uniform(0.02, 0.08))

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                # 1. Primary: Try InnerTube API
                results = self._search_innertube(query, limit=limit)
                if results:
                    return results

                # If InnerTube returned empty, try HTML scrape fallback
                logger.debug(f"InnerTube returned empty for '{query}', trying HTML fallback...")
                results = self._search_html(query, limit=limit)
                if results:
                    return results

                # If both returned empty, query might be too narrow
                return []

            except requests.exceptions.HTTPError as e:
                last_error = e
                status = getattr(e.response, "status_code", 0)
                if status == 429:
                    sleep_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(f"Rate limited (429). Backing off {sleep_time:.1f}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(sleep_time)
                else:
                    logger.warning(f"HTTP error {status} on attempt {attempt}: {e}")
                    time.sleep(1.0)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                sleep_time = (1.5 ** attempt) + random.uniform(0.2, 0.6)
                logger.warning(f"Network error on attempt {attempt}: {e}. Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected search error on query '{query}': {e}")
                break

        # Final attempt with HTML fallback if InnerTube failed
        try:
            return self._search_html(query, limit=limit)
        except Exception:
            pass

        logger.error(f"Search failed for '{query}' after {self.max_retries} retries: {last_error}")
        return []
