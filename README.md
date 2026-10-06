# YouTube Music Title Matcher & URL Resolver

A high-performance, intelligent Python application that processes collections of music titles (including messy filenames, download artifacts, abbreviations, and foreign scripts) and finds the best-matching YouTube video URL for each title.

Designed to process hundreds of songs (600+) rapidly and reliably **without using the official YouTube Data API** and **without launching heavy browser instances**.

---

## 🌟 Key Highlights & Capabilities

### 1. Direct, Lightweight YouTube Search (No API Key Required)
- Uses YouTube's native web client `InnerTube` endpoint (`https://www.youtube.com/youtubei/v1/search`) with persistent session connection pooling and HTTP keep-alive.
- Fast response times (~100–300ms per query), processing hundreds of songs in seconds.
- Secondary fallback parses YouTube search HTML initial data if the primary endpoint ever throttles.
- Zero headless browser overhead (no Selenium, Puppeteer, or Chromium dependencies).

### 2. Intelligent Title Normalization & Punctuation Tolerance
- Automatically handles punctuation differences (`*`, `-`, `_`, `.`, `()`, `[]`, `:`, extra spaces, capitalization).
- Removes downloader artifacts:
  - Underscore-separated words (`A_R_Rahman_Hosanna...` ➔ `A R Rahman Hosanna...`).
  - Bitrate/audio tags (`(MP3_160K)`, `(MP3_320K)`, `[MP3_...]`, `-converted 2`, `.mp3`).
  - File duplicate counts (`(1)`, `(2)`).
  - Common text corruptions (`youtub e` ➔ `youtube`, `2 014` ➔ `2014`, `Cha mkila` ➔ `Chamkila`).
- Strips YouTube promotional and metadata fluff (*Official Video*, *Official Audio*, *Lyrical Video*, *Full Video Song*, *HD*, *4K*, *Visualizer*, *OST*, etc.).
- Complete Unicode support for non-Latin scripts (Bengali, Hindi, Telugu, and other Indic alphabets).

### 3. Multi-Metric Semantic Matching & Quality Control
- **Core Token Set Ratio**: Compares fluff-stripped titles to identify the true song identity.
- **Token Sort Ratio**: Tolerates reordered words (*Artist - Song* vs *Song - Artist*).
- **Fuzzy Token Recall**: Ensures significant query words are genuinely present in the candidate title/channel, rejecting unrelated videos that only share common words.
- **Subset Containment Weighting**: Prevents penalizing concise song titles when matched against rich YouTube video titles that list full movie credits and actors.
- **Channel & Studio Correlation**: Rewards candidates where the uploader channel matches an artist or record label (*T-Series*, *Sony Music*, *SVF*, etc.).
- **Configurable Confidence Threshold** (`--threshold 0.65`): Automatically rejects low-confidence matches as `NOT_FOUND`.

### 4. Interactive Pause, Resume & Checkpoint Facilities
- **Interactive `Ctrl+C` Pause**: Pressing `Ctrl+C` pauses all background worker threads cleanly and opens an interactive console prompt:
  ```text
  ====================================================================
  [PAUSED] Execution paused at 320/669 titles (96.8% matched).
    • Press [ENTER] to resume execution
    • Type 'q' + [ENTER] to save and exit (can resume anytime)
  ====================================================================
  ```
- **Zero-Loss Resume Engine**: When restarted, the program detects existing results in `links.txt` and `.cache/checkpoint.json` and continues processing remaining titles without re-querying completed items.
- **Status Inspector**: Inspect current progress, checkpoint data, and cache statistics at any time with:
  ```bash
  python main.py --status
  ```

### 5. Dedicated Dual Error Logging
- **`yt_matcher.log`**: Detailed general log capturing INFO and DEBUG logs, connection timestamps, and progress.
- **`errors.log`**: Dedicated diagnostic log specifically isolating WARNING and ERROR events:
  - Exact items marked `NOT_FOUND`, including candidate video titles evaluated and confidence percentages.
  - Rate limiting events (HTTP 429) and backoff durations.
  - Network timeouts, connection drops, and retry attempts with line numbers and stack traces.

---

## 📁 Project Architecture

```
YT/
├── config.py                 # Central configuration defaults and endpoints
├── normalizer.py             # Advanced title normalization & query cleaning
├── matcher.py                # Multi-metric fuzzy/semantic matching engine
├── searcher.py               # Direct YouTube search client (InnerTube + HTML fallback)
├── cache.py                  # Thread-safe persistent JSON search cache
├── processor.py              # Batch processing orchestrator (pause, resume, checkpoints)
├── main.py                   # CLI entrypoint with live progress and status inspector
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Package and build specifications
├── links.txt                 # Generated output file (Original Title | URL)
├── unique_music_names_A-Z_serial.txt # Source list of 669 music titles
├── yt_matcher.log            # General activity log
├── errors.log                # Dedicated warnings and error diagnostics log
├── .gitignore                # Git release ignore rules
└── tests/                    # Comprehensive unit test suite
    ├── test_normalizer.py    # Tests for normalization, fluff removal, and scripts
    ├── test_matcher.py       # Tests for scoring accuracy and edge case tolerance
    ├── test_searcher.py      # Tests for response parsing and dataclass serialization
    └── test_cache.py         # Tests for cache hit/miss and atomic persistence
```

---

## ⚡ Installation & Quick Start

### 1. Prerequisites
- Python 3.9 or higher (tested on Windows, macOS, and Linux).

### 2. Setup
```bash
# Clone or navigate into the directory
cd YT

# Install required dependencies
pip install -r requirements.txt
```

### 3. Run the Matcher
```bash
python main.py
```

---

## 💻 CLI Usage & Commands

```text
usage: main.py [-h] [-i INPUT] [-o OUTPUT] [-t THRESHOLD] [-w WORKERS]
               [-d DELAY] [-l LIMIT] [--cache-file CACHE_FILE]
               [--no-cache] [--no-resume] [--strip-numbers]
               [--log-file LOG_FILE] [--error-log ERROR_LOG]
               [--status] [-v]

options:
  -h, --help            Show this help message and exit
  -i, --input INPUT     Path to input file (default: unique_music_names_A-Z_serial.txt)
  -o, --output OUTPUT   Path to output file (default: links.txt)
  -t, --threshold FLOAT Minimum confidence threshold between 0.0 and 1.0 (default: 0.65)
  -w, --workers INT     Number of concurrent worker threads (default: 4)
  -d, --delay FLOAT     Delay in seconds per worker request for rate limiting (default: 0.2)
  -l, --limit INT       Process only the first N titles (useful for testing)
  --cache-file PATH     Path to persistent JSON search cache file
  --no-cache            Disable disk search caching
  --no-resume           Start fresh and overwrite existing links.txt
  --strip-numbers       Strip leading serial numbers ('1. ') in links.txt
  --log-file PATH       Path to general log file (default: yt_matcher.log)
  --error-log PATH      Path to dedicated error log file (default: errors.log)
  --status              Display current checkpoint status and exit
  -v, --verbose         Enable verbose debug logging
```

### Examples

- **Check Current Status:**
  ```bash
  python main.py --status
  ```

- **Run Test on First 10 Items:**
  ```bash
  python main.py --limit 10
  ```

- **Run with Stricter Confidence (70%) and 6 Workers:**
  ```bash
  python main.py --threshold 0.70 --workers 6
  ```

- **Process a Custom File:**
  ```bash
  python main.py -i my_playlist.txt -o my_links.txt
  ```

---

## 📋 Output Format

The output file ([links.txt](file:///c:/Users/WDAGUtilityAccount/Desktop/YT/links.txt)) preserves the exact input entry order:

```text
Original Title | YouTube Video URL
```

### Sample Output:
```text
1. 'Sooraj Dooba Hain' FULL VIDEO SONG_ Arijit singh Aditi Singh Sharma _ T-SERIES | https://www.youtube.com/watch?v=nJZcbidTutE
2. 2nd Nayok (Official Music Video) _ Pritom Hasan _ Nuhash Humayun Malaika _ Mir Rabby | https://www.youtube.com/watch?v=MfSQfNyWVAI
3. 3 - Why This Kolaveri Di Video_ Dhanush, Shruti _ Anirudh | https://www.youtube.com/watch?v=Ja168gMpb3o
5. [Animation] I_II Start Tomorrow | https://www.youtube.com/watch?v=F8zqVO8UqTM
6. _ভ্রমণের শেষে ফিরে এসো তুমি আগের মতো_কেউ বসে আছে তোমার অপে(MP3_16 | https://www.youtube.com/watch?v=1PaBhKKVmSY
10. A_R_Rahman_Hosanna_Best_Video_Ekk_Deewana_Tha_Amy_Jackson_Prateik | https://www.youtube.com/watch?v=dfNdRsNSFx4
...
57. Apnahi rangme | NOT_FOUND
...
669. 🎵Benche Thakar Gaan _🎤Anupam Roy _ United Mix | https://www.youtube.com/watch?v=Qo885OOwM9g
```

---

## 🧪 Running Unit Tests

Run the full automated test suite:
```bash
python -m unittest discover tests
```

---

## 🏷️ Git Release & Versioning

To commit and tag a new release:

```bash
# Stage changes
git add .

# Create release commit
git commit -m "Release v1.0.0: YouTube Music Title Matcher & URL Resolver"

# Create annotated release tag
git tag -a v1.0.0 -m "Release version 1.0.0"
```
