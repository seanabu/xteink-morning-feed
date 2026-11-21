"""Profile loading and schema validation.

Everything user-specific (sources, topics, keywords, targets) lives in a
profile folder. This module only defines the shape of those files; it holds
no sources or topics itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ProfileError(Exception):
    """Raised when a profile is missing or fails validation."""


class _Strict(BaseModel):
    # Unknown keys are an error, so typos in YAML never fail silently.
    model_config = ConfigDict(extra="forbid")


class ProfileSettings(_Strict):
    name: str
    timezone: str = "UTC"
    catalog_title: str = "Morning Feed"
    daily_target: int = Field(14, ge=1, le=50)
    topic_cap: int = Field(5, ge=1)
    retention_days: int = Field(7, ge=1)
    min_read_minutes: float = Field(3, ge=0)
    fetch_window_hours: int = Field(36, ge=1)
    max_images: int = Field(4, ge=0)
    ranking: Literal["keywords", "llm"] = "keywords"
    whole_day_epub: bool = True
    catalog_layout: Literal["nested", "flat"] = "nested"
    nyt_mode: Literal["off", "headlines", "full_text"] = "headlines"

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone {v!r}") from e
        return v


class Source(_Strict):
    name: str
    url: Optional[str] = None
    tier: Literal["always", "filtered"]
    topic: str
    weight: float = 1.0
    enabled: bool = True
    # True until the feed URL has been confirmed by hand; --check flags these.
    verify: bool = False
    notes: Optional[str] = None
    # Per-source behaviours (options, never code branches).
    paywall: Literal["substack", "none"] = "none"
    extract: Literal["feed", "page", "summary"] = "feed"
    min_words: int = Field(300, ge=0)
    max_words: Optional[int] = Field(None, ge=1)
    skip_if_title_matches: list[str] = Field(default_factory=list)
    points_min: Optional[int] = None

    @field_validator("skip_if_title_matches")
    @classmethod
    def _valid_regexes(cls, v: list[str]) -> list[str]:
        for pat in v:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"bad regex {pat!r}: {e}") from e
        return v

    @model_validator(mode="after")
    def _url_or_verify(self) -> "Source":
        if self.enabled and not self.url and not self.verify:
            raise ValueError("url is required unless verify: true or enabled: false")
        return self


class TopicInterest(_Strict):
    label: Optional[str] = None  # how the topic is shown on the device, e.g. "NBA"
    keywords: list[str] = Field(default_factory=list)
    weight: float = 1.0


class Interests(_Strict):
    topics: dict[str, TopicInterest] = Field(default_factory=dict)
    blocklist: list[str] = Field(default_factory=list)


class Profile(_Strict):
    slug: str
    path: Path
    settings: ProfileSettings
    sources: list[Source]
    interests: Interests

    @property
    def active_sources(self) -> list[Source]:
        return [s for s in self.sources if s.enabled]

    def topic_label(self, topic: str) -> str:
        t = self.interests.topics.get(topic)
        return t.label if t and t.label else topic


def _read_yaml(path: Path):
    if not path.exists():
        raise ProfileError(f"missing file: {path}")
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ProfileError(f"{path}: invalid YAML: {e}") from e


def _format_errors(path: Path, err: ValidationError) -> str:
    lines = [f"{path}: {err.error_count()} validation error(s)"]
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        lines.append(f"  - {loc}: {e['msg']}")
    return "\n".join(lines)


def load_profile(profile_dir: Path) -> Profile:
    """Load and validate profile.yaml, sources.yaml and interests.yaml."""
    profile_dir = Path(profile_dir)
    if not profile_dir.is_dir():
        raise ProfileError(f"profile folder not found: {profile_dir}")

    files = {
        "profile": profile_dir / "profile.yaml",
        "sources": profile_dir / "sources.yaml",
        "interests": profile_dir / "interests.yaml",
    }
    raw = {k: _read_yaml(p) for k, p in files.items()}

    try:
        settings = ProfileSettings.model_validate(raw["profile"] or {})
    except ValidationError as e:
        raise ProfileError(_format_errors(files["profile"], e)) from None

    if not isinstance(raw["sources"], list):
        raise ProfileError(f"{files['sources']}: expected a list of sources")
    sources = []
    errors = []
    for i, entry in enumerate(raw["sources"]):
        try:
            sources.append(Source.model_validate(entry))
        except ValidationError as e:
            label = entry.get("name", f"#{i}") if isinstance(entry, dict) else f"#{i}"
            errors.append(_format_errors(Path(f"{files['sources']}[{label}]"), e))
    if errors:
        raise ProfileError("\n".join(errors))

    names = [s.name for s in sources]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ProfileError(f"{files['sources']}: duplicate source names: {', '.join(dupes)}")

    try:
        interests = Interests.model_validate(raw["interests"] or {})
    except ValidationError as e:
        raise ProfileError(_format_errors(files["interests"], e)) from None

    return Profile(
        slug=profile_dir.name,
        path=profile_dir,
        settings=settings,
        sources=sources,
        interests=interests,
    )
