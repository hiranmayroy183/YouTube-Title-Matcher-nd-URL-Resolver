"""
Intelligent title matching and confidence scoring engine.
Combines token-based similarity, fuzzy string matching, character/word overlap,
metadata fluff stripping, token recall verification, and channel/uploader correlation.
"""

from typing import Dict, List, Optional, Tuple, Any

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    import difflib

from normalizer import (
    normalize_title,
    strip_fluff,
    extract_significant_tokens,
    strip_serial_prefix,
    split_artist_title,
)


def _pure_python_ratio(s1: str, s2: str) -> float:
    """Fallback Levenshtein-like ratio using difflib if rapidfuzz is not installed."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def _pure_python_token_sort_ratio(s1: str, s2: str) -> float:
    """Fallback token sort ratio using difflib."""
    t1 = ' '.join(sorted(s1.split()))
    t2 = ' '.join(sorted(s2.split()))
    return _pure_python_ratio(t1, t2)


def _pure_python_token_set_ratio(s1: str, s2: str) -> float:
    """Fallback token set ratio using difflib."""
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    intersection = tokens1.intersection(tokens2)
    diff1 = tokens1 - intersection
    diff2 = tokens2 - intersection

    sorted_inter = ' '.join(sorted(intersection))
    sorted_diff1 = ' '.join(sorted(diff1))
    sorted_diff2 = ' '.join(sorted(diff2))

    t0 = sorted_inter.strip()
    t1 = f"{t0} {sorted_diff1}".strip()
    t2 = f"{t0} {sorted_diff2}".strip()

    scores = [
        _pure_python_ratio(t0, t1),
        _pure_python_ratio(t0, t2),
        _pure_python_ratio(t1, t2),
    ]
    return max(scores) if scores else 0.0


def compute_similarity_metrics(s1: str, s2: str) -> Dict[str, float]:
    """Computes basic fuzzy and token similarity metrics between two strings."""
    if not s1 or not s2:
        return {'ratio': 0.0, 'token_sort': 0.0, 'token_set': 0.0}

    if HAS_RAPIDFUZZ:
        return {
            'ratio': fuzz.ratio(s1, s2) / 100.0,
            'token_sort': fuzz.token_sort_ratio(s1, s2) / 100.0,
            'token_set': fuzz.token_set_ratio(s1, s2) / 100.0,
        }
    else:
        return {
            'ratio': _pure_python_ratio(s1, s2),
            'token_sort': _pure_python_token_sort_ratio(s1, s2),
            'token_set': _pure_python_token_set_ratio(s1, s2),
        }


class TitleMatcher:
    """
    Intelligent title matcher and scorer that calculates semantic confidence
    between an input query title and YouTube search result candidates.
    """

    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold

    def score_breakdown(
        self,
        input_raw: str,
        cand_title: str,
        cand_channel: str = "",
        rank: int = 0
    ) -> Dict[str, Any]:
        """
        Computes detailed scoring metrics breakdown for analysis and debugging.
        """
        input_clean = strip_serial_prefix(input_raw)
        norm_in = normalize_title(input_clean)
        norm_cand = normalize_title(cand_title)
        norm_chan = normalize_title(cand_channel)

        if not norm_in or not norm_cand:
            return {'confidence': 0.0, 'reason': 'empty_normalized_string'}

        # Exact match check
        if norm_in == norm_cand:
            return {
                'confidence': 1.0,
                'is_exact': True,
                'norm_in': norm_in,
                'norm_cand': norm_cand,
            }

        # 1. Full normalized comparison
        full_metrics = compute_similarity_metrics(norm_in, norm_cand)

        # 2. Fluff-stripped core comparison
        core_in = strip_fluff(norm_in)
        core_cand = strip_fluff(norm_cand)
        core_metrics = compute_similarity_metrics(
            core_in or norm_in,
            core_cand or norm_cand
        )

        # 3. Fuzzy Token recall (what fraction of essential input words are present)
        sig_in = extract_significant_tokens(core_in or norm_in)
        cand_combined = f"{norm_cand} {norm_chan}"
        sig_cand = extract_significant_tokens(cand_combined)

        if sig_in:
            matched_count = 0
            for tok in sig_in:
                if tok in sig_cand:
                    matched_count += 1
                elif any(
                    (fuzz.ratio(tok, c) >= 80 if HAS_RAPIDFUZZ else _pure_python_ratio(tok, c) >= 0.80) or
                    (len(tok) >= 4 and len(c) >= 4 and (tok.startswith(c) or c.startswith(tok)))
                    for c in sig_cand
                ):
                    matched_count += 1
            recall = matched_count / len(sig_in)
        else:
            recall = 1.0

        # Penalty multiplier based on recall
        # This prevents unrelated videos that only share 1 generic word (e.g. artist only)
        if recall < 0.35:
            recall_multiplier = 0.40
        elif recall < 0.50:
            recall_multiplier = 0.65
        elif recall < 0.70:
            recall_multiplier = 0.85
        elif recall < 0.85:
            recall_multiplier = 0.95
        else:
            recall_multiplier = 1.0

        # Channel artist correlation bonus
        channel_bonus = 0.0
        if norm_chan and len(norm_chan) > 3 and norm_chan in norm_in:
            channel_bonus = 0.04

        # Rank prior bonus (slight preference for higher search rank)
        rank_bonus = max(0.0, 0.03 - rank * 0.008)

        # Artist/title segmentation match bonus
        art_in, tit_in = split_artist_title(input_clean)
        art_bonus = 0.0
        if art_in and tit_in:
            norm_art = normalize_title(art_in)
            norm_tit = normalize_title(tit_in)
            if norm_tit and norm_tit in norm_cand:
                art_bonus += 0.03
            if norm_art and (norm_art in norm_cand or norm_art in norm_chan):
                art_bonus += 0.02

        # Composite base score with subset containment weighting
        # If candidate title contains almost all of the query's core words, don't penalize
        # it excessively for having extra metadata (like movie cast or label names).
        if recall >= 0.80 and core_metrics['token_set'] >= 0.85:
            base_score = (
                0.55 * core_metrics['token_set'] +
                0.25 * full_metrics['token_set'] +
                0.10 * core_metrics['token_sort'] +
                0.10 * full_metrics['ratio']
            )
        else:
            base_score = (
                0.35 * core_metrics['token_set'] +
                0.25 * full_metrics['token_set'] +
                0.20 * core_metrics['token_sort'] +
                0.20 * full_metrics['ratio']
            )

        final_score = (base_score * recall_multiplier) + channel_bonus + rank_bonus + art_bonus
        final_score = min(1.0, max(0.0, round(final_score, 4)))


        return {
            'confidence': final_score,
            'base_score': round(base_score, 4),
            'recall': round(recall, 4),
            'recall_multiplier': recall_multiplier,
            'full_token_set': round(full_metrics['token_set'], 4),
            'core_token_set': round(core_metrics['token_set'], 4),
            'channel_bonus': channel_bonus,
            'rank_bonus': round(rank_bonus, 4),
            'norm_in': norm_in,
            'norm_cand': norm_cand,
        }

    def calculate_confidence(
        self,
        input_raw: str,
        cand_title: str,
        cand_channel: str = "",
        rank: int = 0
    ) -> float:
        """
        Calculates confidence score (0.0 to 1.0) for a candidate video.
        """
        breakdown = self.score_breakdown(input_raw, cand_title, cand_channel, rank)
        return breakdown.get('confidence', 0.0)

    def select_best_match(
        self,
        input_raw: str,
        candidates: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ) -> Tuple[Optional[Dict[str, Any]], float, bool]:
        """
        Ranks multiple YouTube search results and selects the best overall match.
        Returns (best_candidate, best_confidence, is_match).
        If best_confidence is below threshold, returns (best_candidate, best_confidence, False).
        """
        if threshold is None:
            threshold = self.confidence_threshold

        if not candidates:
            return None, 0.0, False

        scored_candidates = []
        for rank, cand in enumerate(candidates):
            title = cand.get('title', '')
            channel = cand.get('channel', '')
            score = self.calculate_confidence(input_raw, title, channel, rank)
            scored_candidates.append((score, rank, cand))

        # Sort descending by score, ascending by rank as tie-breaker
        scored_candidates.sort(key=lambda x: (x[0], -x[1]), reverse=True)

        best_score, best_rank, best_cand = scored_candidates[0]
        is_confident_match = (best_score >= threshold)

        return best_cand, best_score, is_confident_match
