"""Normalize country labels for IRB catalog filtering (aliases + US state inference)."""
from __future__ import annotations

# Canonical display labels (match IRB form / Site Profile dropdown values).
_CANONICAL_BY_KEY: dict[str, str] = {
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "india": "India",
    "australia": "Australia",
    "germany": "Germany",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "canada": "Canada",
    "japan": "Japan",
    "france": "France",
    "china": "China",
    "brazil": "Brazil",
    "mexico": "Mexico",
    "singapore": "Singapore",
    "south korea": "South Korea",
    "korea": "South Korea",
    "spain": "Spain",
    "italy": "Italy",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "europe": "Europe",
}

# US state / territory names and abbreviations stored mistakenly in `jurisdiction`.
_US_REGION_KEYS: frozenset[str] = frozenset(
    {
        "alabama",
        "al",
        "alaska",
        "ak",
        "arizona",
        "az",
        "arkansas",
        "ar",
        "california",
        "ca",
        "colorado",
        "co",
        "connecticut",
        "ct",
        "delaware",
        "de",
        "florida",
        "fl",
        "georgia",
        "ga",
        "hawaii",
        "hi",
        "idaho",
        "id",
        "illinois",
        "il",
        "indiana",
        "in",
        "iowa",
        "ia",
        "kansas",
        "ks",
        "kentucky",
        "ky",
        "louisiana",
        "la",
        "maine",
        "me",
        "maryland",
        "md",
        "massachusetts",
        "ma",
        "michigan",
        "mi",
        "minnesota",
        "mn",
        "mississippi",
        "ms",
        "missouri",
        "mo",
        "montana",
        "mt",
        "nebraska",
        "ne",
        "nevada",
        "nv",
        "new hampshire",
        "nh",
        "new jersey",
        "nj",
        "new mexico",
        "nm",
        "new york",
        "ny",
        "north carolina",
        "nc",
        "north dakota",
        "nd",
        "ohio",
        "oh",
        "oklahoma",
        "ok",
        "oregon",
        "or",
        "pennsylvania",
        "pa",
        "rhode island",
        "ri",
        "south carolina",
        "sc",
        "south dakota",
        "sd",
        "tennessee",
        "tn",
        "texas",
        "tx",
        "utah",
        "ut",
        "vermont",
        "vt",
        "virginia",
        "va",
        "washington",
        "wa",
        "west virginia",
        "wv",
        "wisconsin",
        "wi",
        "wyoming",
        "wy",
        "district of columbia",
        "dc",
        "puerto rico",
        "pr",
    }
)


def _normalize_key(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def canonical_country_key(value: str | None) -> str | None:
    """Map any country alias to a canonical lowercase key for equality checks."""
    key = _normalize_key(value)
    if not key:
        return None
    if key in _CANONICAL_BY_KEY:
        return _normalize_key(_CANONICAL_BY_KEY[key])
    if key in _US_REGION_KEYS:
        return "united states"
    return key


def resolve_irb_country(
    country: str | None,
    jurisdiction: str | None,
) -> str | None:
    """
    Best-effort country for an IRB row.

    - Prefer explicit `country` when it maps to a known label.
    - When `country` is empty and `jurisdiction` is a US state, infer United States.
    - Fall back to jurisdiction only when it looks like a country name.
    """
    country_key = _normalize_key(country)
    jurisdiction_key = _normalize_key(jurisdiction)

    if country_key:
        if country_key in _CANONICAL_BY_KEY:
            return _CANONICAL_BY_KEY[country_key]
        if country_key in _US_REGION_KEYS:
            return "United States"
        # Unknown label — return trimmed original for display.
        return str(country).strip()

    if jurisdiction_key in _US_REGION_KEYS:
        return "United States"

    if jurisdiction_key in _CANONICAL_BY_KEY:
        return _CANONICAL_BY_KEY[jurisdiction_key]

    if jurisdiction_key:
        return str(jurisdiction).strip()

    return None


def countries_match(
    requested: str | None,
    irb_country: str | None,
    irb_jurisdiction: str | None,
) -> bool:
    """True when the requested Site Profile country matches this IRB."""
    req_key = canonical_country_key(requested)
    if not req_key:
        return True
    resolved = resolve_irb_country(irb_country, irb_jurisdiction)
    irb_key = canonical_country_key(resolved)
    return irb_key == req_key
