"""Factor match priority (no database)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.modules.site_budgeting.db_models import ConversionFactor
from app.modules.site_budgeting.services.factor_service import pick_best_factor, resolve_factor_match_rank


def _fac(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        factor_type_id=uuid.uuid4(),
        trial_id=None,
        country_code=None,
        site_id=None,
        sequence_order=0,
        value=Decimal("1"),
        currency_code=None,
        label=None,
        scope_element_id=None,
        scope_category=None,
    )
    defaults.update(kwargs)
    return ConversionFactor(**defaults)


def test_element_site_beats_element_country():
    ft = uuid.uuid4()
    trial = uuid.uuid4()
    el = uuid.uuid4()
    site = uuid.uuid4()
    fac_country = _fac(
        factor_type_id=ft,
        trial_id=trial,
        scope_element_id=el,
        country_code="USA",
        value=Decimal("3"),
    )
    fac_site = _fac(
        factor_type_id=ft,
        trial_id=trial,
        scope_element_id=el,
        site_id=site,
        value=Decimal("2"),
    )
    best = pick_best_factor(
        [fac_country, fac_site],
        factor_type_id=ft,
        trial_id=trial,
        element_id=el,
        element_category=None,
        country_code="usa",
        site_id=site,
    )
    assert best is not None
    assert best.value == Decimal("2")


def test_global_country_beats_global_default():
    ft = uuid.uuid4()
    trial = uuid.uuid4()
    el = uuid.uuid4()
    g_default = _fac(factor_type_id=ft, trial_id=trial, value=Decimal("1.1"))
    g_country = _fac(factor_type_id=ft, trial_id=trial, country_code="DEU", value=Decimal("0.95"))
    best = pick_best_factor(
        [g_default, g_country],
        factor_type_id=ft,
        trial_id=trial,
        element_id=el,
        element_category="LAB",
        country_code="DEU",
        site_id=None,
    )
    assert best is not None
    assert best.value == Decimal("0.95")


def test_additive_rank_matches_category_site():
    ft = uuid.uuid4()
    trial = uuid.uuid4()
    el = uuid.uuid4()
    site = uuid.uuid4()
    fac = _fac(
        factor_type_id=ft,
        trial_id=trial,
        scope_category="CHEM",
        site_id=site,
        value=Decimal("5"),
    )
    r = resolve_factor_match_rank(
        fac,
        element_id=el,
        element_category="CHEM",
        country_code=None,
        site_id=site,
    )
    assert r == 6  # Category + Site
