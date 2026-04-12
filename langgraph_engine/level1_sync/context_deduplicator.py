"""
Context Deduplicator - Remove redundant information across loaded context files.

Targets duplicate content between SRS, README, and CLAUDE.md.
Deduplication is only applied when it saves > 20% of total context space.

Algorithm:
1. Tokenize each context string into sentences/lines
2. Build a fingerprint set (normalized line hashes) from the primary doc
3. Remove lines from secondary docs that already appear in primary
4. Compute space savings: if >= 20%, return deduplicated dict, else return original

Usage:
    from context_deduplicator import deduplicate_context
    deduped = deduplicate_context(context_data)
"""

import hashlib
import sys
from typing import Dict, List, Tuple

# Only apply deduplication if it saves more than this fraction of total size
MIN_SAVINGS_RATIO = 0.20  # 20%

# Priority order: higher priority docs define the "canonical" text
# Lines seen in earlier docs are removed from later docs
PRIORITY_ORDER = ["srs", "readme", "claude_md"]


# ============================================================================
# PUBLIC API
# ============================================================================


def deduplicate_context(contexts: dict) -> dict:
    """Find and remove duplicate information across context files.

    Checks for duplicate content across: SRS, README, CLAUDE.md.
    Only applies deduplication if it saves > 20% of total context space.

    Args:
        contexts: Dict with keys "srs", "readme", "claude_md" (str or None),
                  plus "files_loaded" list and any other metadata.

    Returns:
        Deduplicated context dict (same shape as input).
        If savings < 20%, returns a shallow copy of the original unchanged.
    """
    if not contexts or not isinstance(contexts, dict):
        return contexts

    # Extract text values from context
    texts: Dict[str, str] = {}
    for key in PRIORITY_ORDER:
        val = contexts.get(key)
        if val and isinstance(val, str) and val.strip():
            texts[key] = val

    if len(texts) < 2:
        # Nothing to deduplicate
        return dict(contexts)

    # Calculate original total size
    original_size = sum(len(t.encode("utf-8", errors="ignore")) for t in texts.values())
    if original_size == 0:
        return dict(contexts)

    # Build deduplicated versions
    seen_fingerprints: set = set()
    deduped_texts: Dict[str, str] = {}
    total_removed_bytes = 0

    for key in PRIORITY_ORDER:
        if key not in texts:
            continue

        original_text = texts[key]
        lines = original_text.splitlines(keepends=True)
        kept_lines: List[str] = []

        for line in lines:
            normalized = line.strip().lower()
            if not normalized:
                # Keep empty/whitespace lines to preserve structure
                kept_lines.append(line)
                continue

            fp = _fingerprint(normalized)
            if fp in seen_fingerprints:
                # This line already appeared in a higher-priority doc
                total_removed_bytes += len(line.encode("utf-8", errors="ignore"))
            else:
                seen_fingerprints.add(fp)
                kept_lines.append(line)

        deduped_texts[key] = "".join(kept_lines)

    # Calculate savings ratio
    new_size = sum(len(t.encode("utf-8", errors="ignore")) for t in deduped_texts.values())
    savings_ratio = (original_size - new_size) / original_size if original_size > 0 else 0.0

    # Only apply deduplication if savings >= threshold
    if savings_ratio >= MIN_SAVINGS_RATIO:
        result = dict(contexts)
        for key, deduped_text in deduped_texts.items():
            result[key] = deduped_text
        result["_dedup_applied"] = True
        result["_dedup_savings_ratio"] = round(savings_ratio, 3)
        result["_dedup_original_bytes"] = original_size
        result["_dedup_new_bytes"] = new_size
        print(
            "[CONTEXT DEDUP] Applied: {:.1f}% savings ({} -> {} bytes)".format(
                savings_ratio * 100, original_size, new_size
            ),
            file=sys.stderr,
        )
        return result
    else:
        # Savings below threshold - return original unchanged
        result = dict(contexts)
        result["_dedup_applied"] = False
        result["_dedup_savings_ratio"] = round(savings_ratio, 3)
        result["_dedup_original_bytes"] = original_size
        result["_dedup_new_bytes"] = new_size
        print(
            "[CONTEXT DEDUP] Skipped: {:.1f}% savings < {:.0f}% threshold".format(
                savings_ratio * 100, MIN_SAVINGS_RATIO * 100
            ),
            file=sys.stderr,
        )
        return result


# ============================================================================
# HELPERS
# ============================================================================


def _fingerprint(text: str) -> str:
    """Produce a stable fingerprint for a normalized line of text.

    Uses MD5 (fast, not security-sensitive - just dedup hashing).
    """
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()


def dedup_savings_estimate(contexts: dict) -> Tuple[float, int, int]:
    """Estimate deduplication savings without actually deduplicating.

    Returns:
        (savings_ratio, original_bytes, estimated_new_bytes)
    """
    if not contexts or not isinstance(contexts, dict):
        return 0.0, 0, 0

    texts = {}
    for key in PRIORITY_ORDER:
        val = contexts.get(key)
        if val and isinstance(val, str) and val.strip():
            texts[key] = val

    if len(texts) < 2:
        return 0.0, 0, 0

    original_size = sum(len(t.encode("utf-8", errors="ignore")) for t in texts.values())
    if original_size == 0:
        return 0.0, 0, 0

    seen_fps: set = set()
    removed = 0

    for key in PRIORITY_ORDER:
        if key not in texts:
            continue
        for line in texts[key].splitlines(keepends=True):
            normalized = line.strip().lower()
            if not normalized:
                continue
            fp = _fingerprint(normalized)
            if fp in seen_fps:
                removed += len(line.encode("utf-8", errors="ignore"))
            else:
                seen_fps.add(fp)

    new_size = original_size - removed
    ratio = removed / original_size if original_size > 0 else 0.0
    return round(ratio, 3), original_size, new_size
