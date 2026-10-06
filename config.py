"""
Configuration settings and default parameters for the YouTube Music Title Matcher.
"""

from pathlib import Path

# Workspace / Project Root
BASE_DIR = Path(__file__).resolve().parent

# Default File Paths
DEFAULT_INPUT_FILE = "unique_music_names_A-Z_serial.txt"
DEFAULT_OUTPUT_FILE = "links.txt"
DEFAULT_URLS_FILE = "urls.txt"
DEFAULT_CACHE_DIR = ".cache"

DEFAULT_CACHE_FILE = ".cache/youtube_search_cache.json"
DEFAULT_CHECKPOINT_FILE = ".cache/checkpoint.json"
DEFAULT_LOG_FILE = "yt_matcher.log"
DEFAULT_ERROR_LOG_FILE = "errors.log"


# Matching Settings
DEFAULT_CONFIDENCE_THRESHOLD = 0.65  # Minimum score (0.0 to 1.0) to accept a match
DEFAULT_TOP_CANDIDATES = 6          # Number of YouTube results to inspect per query

# Concurrency & Performance Settings
DEFAULT_MAX_WORKERS = 4              # Number of parallel worker threads
DEFAULT_REQUEST_TIMEOUT = 12         # Seconds before HTTP timeout
DEFAULT_MAX_RETRIES = 3              # Maximum retries on transient errors
DEFAULT_REQUEST_DELAY = 0.2          # Seconds delay per worker between network requests

# YouTube Endpoints
INNERTUBE_SEARCH_URL = "https://www.youtube.com/youtubei/v1/search"
HTML_SEARCH_URL = "https://www.youtube.com/results"

# Standard User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
