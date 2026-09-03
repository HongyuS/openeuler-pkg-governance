"""Load the YAML governance rules, with a JSON fallback."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app import config


@lru_cache(maxsize=1)
def load_rules() -> dict:
    """Load the governance rules from YAML, falling back to a JSON twin."""
    path: Path = config.RULES_DIR / "governance_rules.yaml"
    if path.exists():
        try:
            import yaml

            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # ruff: ignore[blind-except]
            pass
    # Try a JSON twin if present.
    jpath = config.RULES_DIR / "governance_rules.json"
    if jpath.exists():
        return json.loads(jpath.read_text(encoding="utf-8"))
    return {}


def rules() -> dict:
    """Return the loaded governance rules (cached)."""
    return load_rules()
