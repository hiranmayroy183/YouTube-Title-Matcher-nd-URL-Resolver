"""
Intelligent title cleaning, normalization, and token extraction module.
Designed to handle messy input filenames, download tags, punctuation variations,
Indic/Bengali characters, and YouTube title additions.
"""

import re
import unicodedata
from typing import Set, Tuple


# Regex pattern for serial numbering prefix (e.g., "1. ", "669. ")
SERIAL_PREFIX_RE = re.compile(r'^\d+\.\s*')

# Regex for emojis and decorative Unicode symbols
EMOJI_RE = re.compile(
    r'[\U00010000-\U0010ffff]|[\u2600-\u26ff]|[\u2700-\u27bf]'
)

# Common YouTube metadata additions / fluff words
FLUFF_PATTERNS = [
    r'\b(official\s*(music\s*)?video)\b',
    r'\b(official\s*(audio|lyric(al)?\s*video|track|teaser|trailer|visualizer))\b',
    r'\b(lyric(al)?\s*video)\b',
    r'\b(full\s*(video|audio)\s*(song)?)\b',
    r'\b(video\s*song|audio\s*song|full\s*song|full\s*track|title\s*track)\b',
    r'\b(original\s*motion\s*picture\s*soundtrack|motion\s*picture\s*soundtrack|soundtrack|ost)\b',
    r'\b(trending\s*instagram\s*song|whatsapp\s*status|audio\s*jukebox)\b',
    r'\b(hd|4k|8k|1080p|720p|hq|uhd)\b',
    r'\b(remastered|unplugged|acoustic|visualizer)\b',
    r'\(?\bmp3[_\s]*\d*k?\)?',
    r'-?converted\s*\d*',
    r'\bprod(\.|\s+by)\b',
    r'\b(t-series|svf\s*music|zee\s*music\s*company|sony\s*music|yrf|coke\s*studio\s*(bharat|pakistan)?)\b',
]


STOPWORDS: Set[str] = {
    'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'from', 'is', 'are', 'was', 'were', 'it', 'this', 'that', 'song', 'video', 'audio',
    'music', 'full', 'official', 'lyrics', 'lyrical', 'original', 'version', 'feat', 'ft'
}


def strip_serial_prefix(raw_line: str) -> str:
    """Removes leading numbering prefix like '1. ', '42. ' from a line."""
    return SERIAL_PREFIX_RE.sub('', raw_line.strip())


def clean_query_for_search(raw_line: str) -> str:
    """
    Cleans a raw input line into an optimal YouTube search query.
    Strips serial numbering, file artifacts, corruptions, and underscores.
    """
    if not raw_line:
        return ""

    # 1. Strip serial numbering
    text = strip_serial_prefix(raw_line)

    # 2. Check for embedded ".mp3" followed by appended text (e.g. line 647)
    mp3_split = re.split(r'\.\s*mp3\b', text, maxsplit=1, flags=re.I)
    if len(mp3_split) > 1 and len(mp3_split[0].strip()) > 5:
        text = mp3_split[0].strip()

    # 3. Remove file extensions and downloader tags
    text = re.sub(r'\.(mp3|m4a|wav|mp4|flac|aac|ogg)\b', '', text, flags=re.I)
    text = re.sub(r'\(?MP3[_\s]*\d*K?\)?\s*\d*', '', text, flags=re.I)
    text = re.sub(r'\[MP3[_\s]*\d*K?\]', '', text, flags=re.I)
    text = re.sub(r'-converted\s*\d*', '', text, flags=re.I)
    text = re.sub(r'\(audio\)', '', text, flags=re.I)

    # 4. Remove duplicate file count suffix like " (1)", " (2)" at the very end
    text = re.sub(r'\(\s*\d+\s*\)$', '', text)

    # 5. Fix common corruptions seen in input filenames
    text = re.sub(r'\byoutub\s*e\b', 'youtube', text, flags=re.I)
    text = re.sub(r'\b2\s+014\b', '2014', text)
    text = re.sub(r'\bCha\s+mkila\b', 'Chamkila', text, flags=re.I)
    text = re.sub(r'\bI_II\b', "I'll", text)

    # 6. Replace underscores with spaces (handles A_R_Rahman -> A R Rahman)
    text = re.sub(r'_+', ' ', text)

    # 7. Strip emojis and decorative symbols
    text = EMOJI_RE.sub(' ', text)

    # 8. Clean up collapsed spaces
    text = ' '.join(text.split())
    return text


def normalize_title(text: str) -> str:
    """
    Normalizes a title for robust textual and fuzzy comparison.
    Performs NFKC unicode normalization, lowercasing, punctuation stripping,
    and whitespace collapsing.
    """
    if not text:
        return ""

    # Unicode NFKC normalization
    text = unicodedata.normalize('NFKC', text).lower()

    # Strip serial prefix if present
    text = strip_serial_prefix(text)

    # Strip file download tags and extensions
    text = re.sub(r'\.(mp3|m4a|wav|mp4|flac|aac|ogg)\b', '', text)
    text = re.sub(r'\(?mp3[_\s]*\d*k?\)?\s*\d*', '', text)
    text = re.sub(r'\[mp3[_\s]*\d*k?\]', '', text)
    text = re.sub(r'-converted\s*\d*', '', text)
    text = re.sub(r'\(audio\)', '', text)
    text = re.sub(r'\(\s*\d+\s*\)$', '', text)

    # Strip emojis
    text = EMOJI_RE.sub(' ', text)

    # Replace common separators with spaces
    text = re.sub(r'[_|\-—/\\:;~*+•]+', ' ', text)

    # Remove quotes, brackets, parens, and extraneous punctuation
    text = re.sub(r'[\'\"`´‘’“”\[\]\(\)\{\}<>#@$!?,^%&=]', ' ', text)

    # Collapse whitespace
    return ' '.join(text.split())


def strip_fluff(text: str) -> str:
    """
    Strips YouTube video metadata fluff (e.g. 'official video', 'lyrics', 'HD')
    from an already normalized string to produce the core song/artist text.
    """
    if not text:
        return ""
    t = text
    for pattern in FLUFF_PATTERNS:
        t = re.sub(pattern, ' ', t, flags=re.I)
    return ' '.join(t.split())


def extract_significant_tokens(text: str) -> Set[str]:
    """
    Extracts significant word tokens (length >= 2, excluding stopwords).
    Supports English, Bengali, Hindi, and other unicode scripts.
    """
    if not text:
        return set()
    tokens = text.split()
    return {tok for tok in tokens if len(tok) >= 2 and tok not in STOPWORDS}


def split_artist_title(text: str) -> Tuple[str, str]:
    """
    Attempts to split a string into (artist, title) if a clear delimiter exists.
    Returns (artist, title) or ('', text) if no delimiter found.
    """
    cleaned = strip_serial_prefix(text)
    # Check for common artist-title delimiters
    for sep in [' - ', ' — ', ' | ', ': ']:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return '', cleaned.strip()
