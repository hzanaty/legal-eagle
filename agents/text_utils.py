import re
import hashlib
from typing import List, Set

ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]")
PUNCT_EMOJI = re.compile(r"[\u2000-\u206F\u2E00-\u2E7F\'\"“”‘’—–\-–\.\,\!\?\:\;\(\)\[\]\{\}…•·]|[\U0001F300-\U0001FAFF]")
WHITESPACE = re.compile(r"\s+")
ARABIC_NUMERAL_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Sentence boundaries (Arabic and Latin punctuation)
SENTENCE_SPLIT = re.compile(r"[\.!\?؟؛…]+")

def normalize_arabic(text: str) -> str:
    """
    Normalize text for robust matching:
    - remove diacritics
    - remove punctuation & emojis
    - normalize whitespace
    - normalize Arabic numerals to Latin
    """
    if not text:
        return ""
    t = text
    t = ARABIC_DIACRITICS.sub("", t)
    t = t.translate(ARABIC_NUMERAL_MAP)
    t = PUNCT_EMOJI.sub(" ", t)
    t = WHITESPACE.sub(" ", t).strip().lower()
    return t

def tokenize(text: str) -> Set[str]:
    """
    Simple tokenization after normalization.
    """
    norm = normalize_arabic(text)
    if not norm:
        return set()
    return set(norm.split())

def jaccard(a: Set[str], b: Set[str]) -> float:
    """
    Jaccard similarity between two token sets.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0

def sentence_split(text: str) -> List[str]:
    """
    Split text into sentences using Arabic and Latin punctuation.
    """
    if not text:
        return []
    parts = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    return parts

def hash_signature(title: str, content: str) -> str:
    """
    Create a normalized hash signature combining title + content.
    """
    norm = normalize_arabic((title or "") + " " + (content or ""))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
