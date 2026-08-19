"""Async SQLite fixtures for site budgeting integration tests."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base
from app.models import Site, Study
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetTemplate,
    BudgetVisitMatrix,
    ConversionFactor,
    ConversionFactorType,
    CostElement,
    CurrencyExchangeRate,
    ElementCostVersion,
    TrialFactorConfiguration,
    VisitSchedule,
)


_TABLES = [
    Study.__table__,
    Site.__table__,
    CostElement.__table__,
    ElementCostVersion.__table__,
    ConversionFactorType.__table__,
    ConversionFactor.__table__,
    TrialFactorConfiguration.__table__,
    CurrencyExchangeRate.__table__,
    BudgetTemplate.__table__,
    BudgetLineItem.__table__,
    VisitSchedule.__table__,
    BudgetVisitMatrix.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_TABLES))

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seed_study_site(db_session: AsyncSession):
    tid = uuid.uuid4()
    sid = uuid.uuid4()
    db_session.add_all(
        [
            Study(id=tid, study_id="SB-TEST-1", name="Test Study"),
            Site(id=sid, site_id="SB-SITE-1", name="Test Site"),
        ]
    )
    await db_session.commit()
    return tid, sid
