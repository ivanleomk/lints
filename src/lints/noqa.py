"""Tokenize Python `# noqa` comments for custom AST rule suppression."""

from __future__ import annotations

from functools import lru_cache
import io
import re
import tokenize

_NOQA_SEGMENT_RE = re.compile(r"#\s*noqa(?![A-Za-z0-9_-])([^#]*)", re.IGNORECASE)
_RULE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)?$")


@lru_cache(maxsize=8)
def parse_noqa_comments(src: str) -> dict[int, set[str] | None]:
    """Map 1-based line numbers to suppressed rule codes (`None` means bare `# noqa`)."""
    suppressions: dict[int, set[str] | None] = {}
    tokens = tokenize.generate_tokens(io.StringIO(src).readline)
    try:
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            lineno = tok.start[0]
            for match in _NOQA_SEGMENT_RE.finditer(tok.string):
                tail = match.group(1).strip()
                if not tail:
                    suppressions[lineno] = None
                    break
                if not tail.startswith(":"):
                    continue
                parsed = {
                    item
                    for raw in tail[1:].split(",")
                    if (item := raw.strip()) and _RULE_TOKEN_RE.match(item)
                }
                if not parsed:
                    continue
                if lineno not in suppressions:
                    suppressions[lineno] = parsed
                else:
                    existing = suppressions[lineno]
                    if existing is not None:
                        existing.update(parsed)
    except (tokenize.TokenError, IndentationError):
        pass
    return suppressions


def is_noqa_suppressed(src: str, lineno: int, code: str, rule_id: str) -> bool:
    """Return True if `lineno` has a real `# noqa` suppressing `code` or `rule_id`."""
    suppressions = parse_noqa_comments(src)
    if lineno not in suppressions:
        return False
    allowed = suppressions[lineno]
    if allowed is None:
        return True
    return code in allowed or rule_id in allowed
