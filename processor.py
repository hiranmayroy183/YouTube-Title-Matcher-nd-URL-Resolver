"""
Batch processing orchestrator for YouTube Music Title Matcher.
Handles multithreaded processing, resume capability, order preservation,
atomic file writes, and real-time progress reporting.
"""

import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any

import json
from cache import SearchCache
from config import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_URLS_FILE,
    DEFAULT_REQUEST_DELAY,
    DEFAULT_CHECKPOINT_FILE,
)
from matcher import TitleMatcher
from normalizer import clean_query_for_search, strip_serial_prefix
from searcher import YouTubeSearcher, SearchResult

logger = logging.getLogger("yt_matcher.processor")


@dataclass
class TitleEntry:
    index: int
    raw_title: str
    clean_query: str


@dataclass
class ProcessResult:
    index: int
    raw_title: str
    url: str
    confidence: float
    is_match: bool
    matched_title: str = ""
    channel: str = ""


class BatchProcessor:
    """
    Coordinates title loading, searching, matching, and result output.
    """

    def __init__(
        self,
        searcher: Optional[YouTubeSearcher] = None,
        matcher: Optional[TitleMatcher] = None,
        cache: Optional[SearchCache] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_workers: int = DEFAULT_MAX_WORKERS,
        output_file: str = DEFAULT_OUTPUT_FILE,
        urls_file: Optional[str] = DEFAULT_URLS_FILE,
        checkpoint_file: Optional[str] = None,
        resume: bool = True,
        preserve_numbers: bool = True,
        progress_callback: Optional[Callable[[int, int, int, float], None]] = None,
    ):

        self.searcher = searcher or YouTubeSearcher()
        self.matcher = matcher or TitleMatcher(confidence_threshold=confidence_threshold)
        self.cache = cache or SearchCache()
        self.threshold = confidence_threshold
        self.max_workers = max_workers
        self.checkpoint_file = Path(checkpoint_file or DEFAULT_CHECKPOINT_FILE)
        self.output_file = Path(output_file)
        self.urls_file = Path(urls_file or DEFAULT_URLS_FILE)
        self.resume = resume
        self.preserve_numbers = preserve_numbers
        self.progress_callback = progress_callback


        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Initial state: unpaused
        self._is_paused = False
        self._stop_requested = False

        self._processed_count = 0
        self._matched_count = 0
        self._total_confidence = 0.0

    def pause(self) -> None:
        """Pauses processing across all worker threads."""
        self._is_paused = True
        self._pause_event.clear()
        logger.info("Processing paused by user.")

    def resume_processing(self) -> None:
        """Resumes processing across all worker threads."""
        self._is_paused = False
        self._pause_event.set()
        logger.info("Processing resumed by user.")

    def is_paused(self) -> bool:
        """Returns True if processor is currently paused."""
        return self._is_paused

    def save_checkpoint(self, total: int, results: List[Optional[ProcessResult]]) -> None:
        """Saves current processing state to a persistent checkpoint file."""
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            valid_results = [r for r in results if r is not None]
            matched = sum(1 for r in valid_results if r.is_match)
            not_found = len(valid_results) - matched
            checkpoint_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_titles": total,
                "processed_count": len(valid_results),
                "matched_count": matched,
                "not_found_count": not_found,
                "is_completed": len(valid_results) == total,
            }
            temp_ckpt = self.checkpoint_file.with_suffix(".tmp")
            with open(temp_ckpt, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, indent=2)
            os.replace(temp_ckpt, self.checkpoint_file)
            logger.debug(f"Saved checkpoint to {self.checkpoint_file}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Loads existing checkpoint data if available."""
        if not self.checkpoint_file.exists():
            return None
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read checkpoint from {self.checkpoint_file}: {e}")
            return None


    @staticmethod
    def load_input_titles(input_path: str, limit: Optional[int] = None) -> List[TitleEntry]:
        """
        Loads titles from unique_music_names_A-Z_serial.txt.
        Skips header ('TOTAL UNIQUE NAMES: ...') and empty lines.
        Preserves each original title line exactly as it appears.
        """
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        entries: List[TitleEntry] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.rstrip("\r\n")
                if not stripped:
                    continue
                # Skip header lines like "TOTAL UNIQUE NAMES: 669"
                if re.match(r'^TOTAL\s+UNIQUE\s+NAMES\s*:', stripped, re.I):
                    continue

                idx = len(entries) + 1
                clean_q = clean_query_for_search(stripped)
                entries.append(TitleEntry(
                    index=idx,
                    raw_title=stripped,
                    clean_query=clean_q
                ))

                if limit and len(entries) >= limit:
                    break

        logger.info(f"Loaded {len(entries)} titles from {path}")
        return entries

    def _read_existing_links(self) -> Dict[str, Tuple[str, float]]:
        """
        Reads existing output file to enable resuming without duplicate searches.
        Maps raw_title -> (url, confidence).
        """
        if not self.resume or not self.output_file.exists():
            return {}

        existing: Dict[str, Tuple[str, float]] = {}
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\r\n")
                    if not line or " | " not in line:
                        continue
                    parts = line.rsplit(" | ", 1)
                    raw_title = parts[0].strip()
                    url = parts[1].strip()

                    # Store existing match
                    existing[raw_title] = (url, 1.0 if url != "NOT_FOUND" else 0.0)
            logger.info(f"Resume: Found {len(existing)} previously processed titles in {self.output_file}")
        except Exception as e:
            logger.warning(f"Could not read existing {self.output_file} for resume: {e}")

        return existing

    def _process_single_title(self, entry: TitleEntry) -> ProcessResult:
        """
        Processes a single title: queries YouTube (or cache), evaluates results,
        performs query refinement if necessary, and returns ProcessResult.
        """
        # Check pause state before starting
        self._pause_event.wait()
        if self._stop_requested:
            return ProcessResult(
                index=entry.index,
                raw_title=entry.raw_title,
                url="NOT_FOUND",
                confidence=0.0,
                is_match=False
            )

        query = entry.clean_query
        if not query:
            return ProcessResult(
                index=entry.index,
                raw_title=entry.raw_title,
                url="NOT_FOUND",
                confidence=0.0,
                is_match=False
            )

        # 1. Check cache for query results
        cached_data = self.cache.get(query)
        if cached_data is not None:
            candidates = cached_data
        else:
            search_res = self.searcher.search(query, limit=8)
            candidates = [r.to_dict() for r in search_res]
            self.cache.set(query, candidates)

        # 2. Evaluate candidates
        best_cand, best_score, is_match = self.matcher.select_best_match(
            entry.raw_title,
            candidates,
            threshold=self.threshold
        )

        # 3. Fallback query refinement if not confident match
        if not is_match or best_score < 0.70:
            words = query.split()
            refined_queries = []

            # A. Short query refinement
            if len(words) <= 3 and 'song' not in query.lower():
                refined_queries.append(f"{query} song")

            # B. Parentheses stripping: e.g. "Humsafar (Movie_ Saiyaara)" -> "Humsafar Saiyaara"
            no_parens = re.sub(r'[\(\)\[\]]', ' ', query)
            no_parens = ' '.join(no_parens.split())
            if no_parens != query and no_parens not in refined_queries:
                refined_queries.append(no_parens)

            # C. Long query refinement: take title + primary artist/album
            if len(words) > 6:
                raw_clean = strip_serial_prefix(entry.raw_title)
                segments = [s.strip() for s in re.split(r'[-—|_]+', raw_clean) if len(s.strip()) > 2]
                if len(segments) >= 2:
                    simplified = clean_query_for_search(f"{segments[0]} {segments[1]}")
                    if simplified and simplified not in refined_queries:
                        refined_queries.append(simplified)
                first_five = ' '.join(words[:5])
                if first_five not in refined_queries:
                    refined_queries.append(first_five)

            for ref_q in refined_queries:
                ref_cached = self.cache.get(ref_q)
                if ref_cached is not None:
                    ref_candidates = ref_cached
                else:
                    ref_res = self.searcher.search(ref_q, limit=6)
                    ref_candidates = [r.to_dict() for r in ref_res]
                    self.cache.set(ref_q, ref_candidates)

                ref_cand, ref_score, ref_is_match = self.matcher.select_best_match(
                    entry.raw_title,
                    ref_candidates,
                    threshold=self.threshold
                )
                if ref_score > best_score:
                    best_cand = ref_cand
                    best_score = ref_score
                    is_match = ref_is_match
                    if is_match and best_score >= 0.85:
                        break

        # 4. Construct outcome
        if is_match and best_cand:
            video_id = best_cand.get('video_id', '')
            url = f"https://www.youtube.com/watch?v={video_id}"
            matched_title = best_cand.get('title', '')
            channel = best_cand.get('channel', '')
        else:
            url = "NOT_FOUND"
            matched_title = best_cand.get('title', '') if best_cand else ""
            channel = best_cand.get('channel', '') if best_cand else ""
            logger.warning(
                f"NOT_FOUND [Item {entry.index}]: '{entry.raw_title}' "
                f"(best cand: '{matched_title}' [{channel}], confidence: {best_score*100:.1f}%)"
            )

        return ProcessResult(
            index=entry.index,
            raw_title=entry.raw_title,
            url=url,
            confidence=best_score,
            is_match=is_match,
            matched_title=matched_title,
            channel=channel,
        )

    def _write_links_file(self, results: List[Optional[ProcessResult]]) -> None:
        """
        Atomically writes links.txt preserving the exact input order.
        """
        # 1. Write title + link file
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.output_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                for res in results:
                    if res is None:
                        continue
                    if self.preserve_numbers:
                        title_str = res.raw_title
                    else:
                        title_str = strip_serial_prefix(res.raw_title)

                    f.write(f"{title_str} | {res.url}\n")
            os.replace(temp_file, self.output_file)
        except Exception as e:
            logger.error(f"Error writing output file {self.output_file}: {e}")

        # 2. Write URLs-only file (no titles, no numbering)
        self.urls_file.parent.mkdir(parents=True, exist_ok=True)
        temp_urls = self.urls_file.with_suffix(".tmp")
        try:
            with open(temp_urls, "w", encoding="utf-8") as f:
                for res in results:
                    if res is None:
                        continue
                    f.write(f"{res.url}\n")
            os.replace(temp_urls, self.urls_file)
        except Exception as e:
            logger.error(f"Error writing URLs-only file {self.urls_file}: {e}")


    def process_all(self, entries: List[TitleEntry]) -> List[ProcessResult]:
        """
        Executes parallel processing across all entries with interactive pause/resume,
        checkpoint persistence, real-time progress, and thread-safe output.
        """
        total = len(entries)
        if total == 0:
            return []

        # Load existing results for resume
        existing_links = self._read_existing_links()
        results: List[Optional[ProcessResult]] = [None] * total

        pending_entries: List[TitleEntry] = []
        for i, entry in enumerate(entries):
            key = entry.raw_title
            alt_key = strip_serial_prefix(entry.raw_title)
            if key in existing_links:
                url, conf = existing_links[key]
                is_match = (url != "NOT_FOUND")
                results[i] = ProcessResult(
                    index=entry.index,
                    raw_title=entry.raw_title,
                    url=url,
                    confidence=conf,
                    is_match=is_match
                )
                self._processed_count += 1
                if is_match:
                    self._matched_count += 1
                self._total_confidence += conf
            elif alt_key in existing_links:
                url, conf = existing_links[alt_key]
                is_match = (url != "NOT_FOUND")
                results[i] = ProcessResult(
                    index=entry.index,
                    raw_title=entry.raw_title,
                    url=url,
                    confidence=conf,
                    is_match=is_match
                )
                self._processed_count += 1
                if is_match:
                    self._matched_count += 1
                self._total_confidence += conf
            else:
                pending_entries.append(entry)

        if len(pending_entries) < total:
            logger.info(f"Resuming: {len(results) - len(pending_entries)} already completed, {len(pending_entries)} remaining.")

        if not pending_entries:
            self._write_links_file(results)
            self.save_checkpoint(total, results)
            return [r for r in results if r is not None]

        start_time = time.time()
        last_flush_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_entry = {
                executor.submit(self._process_single_title, entry): entry
                for entry in pending_entries
            }

            try:
                for future in as_completed(future_to_entry):
                    if self._stop_requested:
                        break
                    try:
                        res = future.result()
                        results[res.index - 1] = res

                        with self._lock:
                            self._processed_count += 1
                            if res.is_match:
                                self._matched_count += 1
                            self._total_confidence += res.confidence

                            pct_match = (self._matched_count / self._processed_count * 100) if self._processed_count else 0.0
                            avg_conf = (self._total_confidence / self._processed_count * 100) if self._processed_count else 0.0

                            # Report progress
                            if self.progress_callback:
                                self.progress_callback(self._processed_count, total, self._matched_count, pct_match)
                            else:
                                elapsed = time.time() - start_time
                                rate = self._processed_count / elapsed if elapsed > 0 else 0
                                print(
                                    f"\r{self._processed_count}/{total} processed | {pct_match:.1f}% match "
                                    f"(avg conf: {avg_conf:.1f}%) [{rate:.1f} items/s]",
                                    end="",
                                    flush=True
                                )

                            # Periodically flush results and checkpoint
                            now = time.time()
                            if now - last_flush_time > 10 or (self._processed_count % 15 == 0):
                                self._write_links_file(results)
                                self.cache.flush()
                                self.save_checkpoint(total, results)
                                last_flush_time = now

                    except Exception as e:
                        entry = future_to_entry[future]
                        logger.error(f"Error processing '{entry.raw_title}': {e}", exc_info=True)
                        results[entry.index - 1] = ProcessResult(
                            index=entry.index,
                            raw_title=entry.raw_title,
                            url="NOT_FOUND",
                            confidence=0.0,
                            is_match=False
                        )

            except KeyboardInterrupt:
                # Interactive Pause Facility
                self.pause()
                self._write_links_file(results)
                self.cache.flush()
                self.save_checkpoint(total, results)

                pct_m = (self._matched_count / self._processed_count * 100) if self._processed_count else 0.0
                print("\n" + "=" * 68)
                print(f"[PAUSED] Execution paused at {self._processed_count}/{total} titles ({pct_m:.1f}% matched).")
                print("  • Press [ENTER] to resume execution")
                print("  • Type 'q' + [ENTER] to save and exit (can resume anytime)")
                print("=" * 68)

                try:
                    user_input = input("Action [ENTER / 'q']: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    user_input = "q"

                if user_input == "q":
                    self._stop_requested = True
                    print("\n[SAVED] Progress safely stored in links.txt and checkpoint. Exiting.")
                    return [r for r in results if r is not None]
                else:
                    print("\n[RESUMING] Resuming execution...\n")
                    self.resume_processing()
                    for future in future_to_entry:
                        if not future.done() and not self._stop_requested:
                            try:
                                res = future.result()
                                results[res.index - 1] = res
                                with self._lock:
                                    self._processed_count += 1
                                    if res.is_match:
                                        self._matched_count += 1
                                    self._total_confidence += res.confidence
                            except Exception as e:
                                entry = future_to_entry[future]
                                logger.error(f"Error on resume for '{entry.raw_title}': {e}", exc_info=True)

        # Final write, cache, and checkpoint flush
        self._write_links_file(results)
        self.cache.flush()
        self.save_checkpoint(total, results)
        print()

        return [r for r in results if r is not None]

