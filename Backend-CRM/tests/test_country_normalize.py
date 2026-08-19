"""Tests for IRB country normalization."""
from app.modules.sites.country_normalize import (
    canonical_country_key,
    countries_match,
    resolve_irb_country,
)


def test_us_aliases_normalize():
    assert canonical_country_key("USA") == "united states"
    assert canonical_country_key("United States") == "united states"
    assert countries_match("United States", "USA", None)


def test_texas_jurisdiction_infers_united_states():
    assert resolve_irb_country(None, "Texas") == "United States"
    assert countries_match("United States", None, "Texas")


def test_india_irb_does_not_match_united_states():
    assert resolve_irb_country("India", None) == "India"
    assert not countries_match("United States", "India", None)


def test_australia_irb_matches_australia():
    assert countries_match("Australia", "Australia", None)
