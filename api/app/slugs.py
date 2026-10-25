"""Project slugs: the short, URL-safe identifier of a project, generated from its name.

The slug is what the SDK, the API addresses, the web addresses and the S3 keys use; the name is
only a label. A slug is made of lowercase letters, digits and single hyphens, at most 64
characters, and never changes once the project is created.
"""

import re
import unicodedata
from collections.abc import Collection

MAX_SLUG_LENGTH = 64
FALLBACK_SLUG = "project"  # for a name without any letter or digit (for example "日本語")

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def is_slug(value: str) -> bool:
    return len(value) <= MAX_SLUG_LENGTH and _SLUG.fullmatch(value) is not None


def slugify(name: str) -> str:
    """``Support Desk`` → ``support-desk``; accents are folded (``Café`` → ``cafe``)."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NOT_ALNUM.sub("-", folded.lower()).strip("-")[:MAX_SLUG_LENGTH].strip("-")
    return slug or FALLBACK_SLUG


def next_free_slug(base: str, taken: Collection[str]) -> str:
    """``base`` if it is free, else ``base-2``, ``base-3``... (the smallest number that is free)."""
    if base not in taken:
        return base
    number = 2
    while True:
        suffix = f"-{number}"
        candidate = base[: MAX_SLUG_LENGTH - len(suffix)].rstrip("-") + suffix
        if candidate not in taken:
            return candidate
        number += 1
