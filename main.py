"""
Command-Line Interface for YouTube Music Title Matcher.
Processes music titles from unique_music_names_A-Z_serial.txt, searches YouTube directly,
and generates links.txt with best-matching YouTube video URLs.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from cache import SearchCache
from config import (
    DEFAULT_INPUT_FILE,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_URLS_FILE,
    DEFAULT_CACHE_FILE,
    DEFAULT_LOG_FILE,
    DEFAULT_ERROR_LOG_FILE,
    DEFAULT_CHECKPOINT_FILE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_REQUEST_DELAY,
)

from matcher import TitleMatcher
from processor import BatchProcessor
from searcher import YouTubeSearcher


def setup_logging(
    verbose: bool = False,
    log_file: str = DEFAULT_LOG_FILE,
    error_log_file: str = DEFAULT_ERROR_LOG_FILE,
) -> logging.Logger:
    """Configures project-wide dual logging: general log and dedicated error log."""
    root_logger = logging.getLogger("yt_matcher")
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers.clear()

    gen_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    err_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. General log file handler
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG if verbose else logging.INFO)
        fh.setFormatter(gen_fmt)
        root_logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: Could not open log file {log_file}: {e}", file=sys.stderr)

    # 2. Dedicated Error log file handler (WARNING and ERROR only)
    try:
        efh = logging.FileHandler(error_log_file, encoding="utf-8")
        efh.setLevel(logging.WARNING)
        efh.setFormatter(err_fmt)
        root_logger.addHandler(efh)
    except Exception as e:
        print(f"Warning: Could not open error log file {error_log_file}: {e}", file=sys.stderr)

    return root_logger



def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="YouTube Music Title Matcher - Match music titles with YouTube videos directly.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-i", "--input",
        default=DEFAULT_INPUT_FILE,
        help="Path to the input file containing music names.",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_FILE,
        help="Path to the output links file (Title | URL).",
    )
    parser.add_argument(
        "-u", "--urls-output",
        default=DEFAULT_URLS_FILE,
        help="Path to the output file containing only URLs line after line.",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="Confidence score threshold (0.0 to 1.0) required to accept a match.",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Number of concurrent worker threads.",
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help="Delay in seconds between requests per worker (rate limiting).",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Limit execution to the first N titles (for testing).",
    )
    parser.add_argument(
        "--cache-file",
        default=DEFAULT_CACHE_FILE,
        help="Path to persistent JSON search cache file.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk caching of search results.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume capability (start from scratch and overwrite existing output).",
    )
    parser.add_argument(
        "--strip-numbers",
        action="store_true",
        help="Strip leading serial numbers ('1. ') in the output links.txt (default preserves exact input string).",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help="Path to general log file.",
    )
    parser.add_argument(
        "--error-log",
        default=DEFAULT_ERROR_LOG_FILE,
        help="Path to dedicated error log file (captures warnings and errors).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display current processing checkpoint status and cache statistics without starting a search run.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    return parser.parse_args()


def display_status(args: argparse.Namespace) -> None:
    """Displays current checkpoint and cache status without executing searches."""
    print("=" * 70)
    print("         YouTube Music Matcher - Current Status")
    print("=" * 70)
    out_path = Path(args.output)
    urls_path = Path(args.urls_output)
    ckpt_path = Path(DEFAULT_CHECKPOINT_FILE)
    cache_path = Path(args.cache_file)

    if out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        matched = sum(1 for l in lines if not l.endswith(" | NOT_FOUND"))
        not_found = len(lines) - matched
        print(f"Links File (Title | URL): {out_path.resolve()}")
        print(f"URLs File (Links Only):   {urls_path.resolve()}")
        print(f"Total Processed:          {len(lines)} titles")
        print(f"Matched Videos:           {matched} ({(matched/len(lines)*100):.1f}%)" if lines else "0")
        print(f"Not Found:                {not_found} ({(not_found/len(lines)*100):.1f}%)" if lines else "0")
    else:
        print(f"Output File:              Not found ({out_path})")

    if ckpt_path.exists():
        try:
            import json
            with open(ckpt_path, "r", encoding="utf-8") as f:
                ckpt = json.load(f)
            print(f"\nCheckpoint Timestamp:     {ckpt.get('timestamp')}")
            print(f"Status Completed:         {'YES' if ckpt.get('is_completed') else 'IN PROGRESS'}")
        except Exception:
            pass

    if cache_path.exists():
        try:
            import json
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            print(f"Cached Search Queries:    {len(cache_data)}")
        except Exception:
            pass

    print(f"\nGeneral Log:              {Path(args.log_file).resolve()}")
    print(f"Dedicated Error Log:      {Path(args.error_log).resolve()}")
    print("=" * 70)


def main():
    args = parse_arguments()
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file, error_log_file=args.error_log)

    if args.status:
        display_status(args)
        sys.exit(0)

    print("=" * 70)
    print("         YouTube Music Title Matcher & URL Resolver")
    print("=" * 70)
    print(f"Input file:               {args.input}")
    print(f"Links file (Title | URL): {args.output}")
    print(f"URLs file (Links only):   {args.urls_output}")
    print(f"Confidence threshold:     {args.threshold * 100:.1f}%")
    print(f"Concurrent workers:       {args.workers}")
    print(f"Rate limit delay:         {args.delay}s")
    print(f"Search caching:           {'Disabled' if args.no_cache else 'Enabled'}")
    print(f"Resume mode:              {'Disabled' if args.no_resume else 'Enabled'}")
    print(f"Preserve exact line:      {not args.strip_numbers}")
    print(f"General log file:         {args.log_file}")
    print(f"Dedicated error log:      {args.error_log}")
    if args.limit:
        print(f"Limit:                    First {args.limit} items")
    print("=" * 70)

    try:
        entries = BatchProcessor.load_input_titles(args.input, limit=args.limit)
    except Exception as e:
        print(f"\n[ERROR] Failed to read input file: {e}", file=sys.stderr)
        sys.exit(1)

    if not entries:
        print("\n[WARNING] No titles found in input file.")
        sys.exit(0)

    print(f"\nLoaded {len(entries)} titles to process.")
    print("Starting matching process...\n")

    # Initialize components
    searcher = YouTubeSearcher(request_delay=args.delay)
    matcher = TitleMatcher(confidence_threshold=args.threshold)
    cache = SearchCache(cache_file=args.cache_file, enabled=not args.no_cache)

    processor = BatchProcessor(
        searcher=searcher,
        matcher=matcher,
        cache=cache,
        confidence_threshold=args.threshold,
        max_workers=args.workers,
        output_file=args.output,
        urls_file=args.urls_output,
        resume=not args.no_resume,
        preserve_numbers=not args.strip_numbers,
    )


    start_time = time.time()
    try:
        results = processor.process_all(entries)
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrupted by user. Progress saved! You can resume anytime.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error during processing: {e}")
        print(f"\n[ERROR] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

    total_time = time.time() - start_time
    total_processed = len(results)
    matched_count = sum(1 for r in results if r.is_match)
    not_found_count = total_processed - matched_count
    match_rate = (matched_count / total_processed * 100) if total_processed else 0.0
    avg_confidence = (
        sum(r.confidence for r in results) / total_processed * 100
        if total_processed else 0.0
    )

    print("\n" + "=" * 70)
    print("                         SUMMARY REPORT")
    print("=" * 70)
    print(f"Total Titles Processed: {total_processed}")
    print(f"Matched Videos:         {matched_count} ({match_rate:.1f}%)")
    print(f"Not Found:              {not_found_count} ({100 - match_rate:.1f}%)")
    print(f"Average Confidence:     {avg_confidence:.1f}%")
    print(f"Total Execution Time:   {total_time:.1f} seconds")
    if total_time > 0 and total_processed > 0:
        print(f"Processing Speed:       {total_processed / total_time:.2f} titles/second")
    print(f"Links File (Title | URL): {Path(args.output).resolve()}")
    print(f"URLs File (Links Only):   {Path(args.urls_output).resolve()}")
    print(f"General Log:              {Path(args.log_file).resolve()}")
    print(f"Dedicated Error Log:      {Path(args.error_log).resolve()}")

    print("=" * 70 + "\n")



if __name__ == "__main__":
    main()
