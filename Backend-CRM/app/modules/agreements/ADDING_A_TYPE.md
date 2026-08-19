# Adding a new Agreement type

This module is organised so each agreement type (CDA, CTA, future NDA, MSA, ...) lives in its own self-contained sub-folder. The shared layer never names a specific type — type-specific behaviour is dispatched through a registry. Follow the five steps below to add a new type. Estimated effort: **half a day**, including FE + BE + a migration if the new type needs an enum value.

Read this in tandem with the existing implementations as reference:
- BE: [`types/cda/`](types/cda/) and [`types/cta/`](types/cta/)
- FE: [`Frontend-CRM/src/features/agreements/types/cda/`](../../../../Frontend-CRM/src/features/agreements/types/cda/) and [`types/cta/`](../../../../Frontend-CRM/src/features/agreements/types/cta/)

If you find yourself wanting to add an `if type == 'NEWTYPE'` branch anywhere in the **shared** layer, stop — that's the signal you need a registry hook instead.

---

## Prereq: enum the new type code

If the new type is going to be persisted on `Agreement.agreement_type` or `StudyTemplate.template_type`, add the code to the relevant enum first and ship an Alembic migration. Use the existing additions as reference:

- `TemplateType` and the `agreement_type` enum live in [`app/models/agreement.py`](../../models/agreement.py).
- Single logical migration in [`migrations/versions/`](../../../migrations/versions/).

The rest of this doc assumes the enum value already exists.

---

## Step 1 — Create the backend sub-package

Lay out the folder under `app/modules/agreements/types/<code_lower>/`. Mirror CDA or CTA:

```
app/modules/agreements/types/nda/
├── __init__.py         # KEEP LIGHT — see warning below
├── descriptor.py       # builds the AgreementTypeDescriptor
├── routes.py           # FastAPI router for type-specific endpoints
├── service.py          # business logic + on_create / on_status_change hooks
├── schemas.py          # type-specific Pydantic models
└── models.py           # OPTIONAL — only if this type adds its own SQLAlchemy tables
```

### `__init__.py` — must stay light

```python
"""NDA type sub-module — see app/modules/agreements/ADDING_A_TYPE.md."""
```

That's it. Do **not** import from `.routes`, `.descriptor`, or `app.models` here. If `models.py` exists, you may add `from .models import NdaSomething` so `app/models/__init__.py` can re-import it, but nothing else.

**Why so strict:** during SQLAlchemy model loading, `app/models/agreement.py` may import `from app.modules.agreements.types.<code>.models import ...`. That triggers the package `__init__.py`. If that pulls in `.routes`, routes imports from `app.models`, which is mid-loading → circular ImportError. Phase 1 of this refactor hit this exact trap.

### `descriptor.py`

```python
from app.modules.agreements.registry import AgreementTypeDescriptor
from .routes import router as nda_router
from .service import NDA_ALLOWED_TRANSITIONS, nda_on_create, nda_on_status_change

descriptor = AgreementTypeDescriptor(
    code="NDA",
    label="NDA",
    router=nda_router,
    on_create=nda_on_create,
    on_status_change=nda_on_status_change,
    allowed_transitions=NDA_ALLOWED_TRANSITIONS,
)
```

### `routes.py`

Define a `router = APIRouter(tags=["NDA Workflow"])` and decorate handlers as usual. Endpoints should live under a path that does not collide with the shared `/agreements/{id}/...` shape unless they truly are the type's canonical implementation of a shared verb. Look at `types/cta/routes.py` for the standard pattern.

### `service.py`

Provide three things:

```python
NDA_ALLOWED_TRANSITIONS: Dict[str, List[str]] = {}

async def nda_on_create(agreement, db) -> None:
    ...

async def nda_on_status_change(agreement, old_status, new_status, db) -> None:
    ...
```

If you only need one of the two hooks, leave the other as a no-op returning `None`. Hooks run **inside the same DB transaction** as the shared status change; do not commit, just flush. Hooks that raise are caught and logged by the dispatcher — they will not roll back the status change. Don't depend on hook failure for correctness.

### `models.py` (optional)

Only add this if your type owns its own tables. Define them with the shared `Base` from `app.db`:

```python
from app.db import Base
from sqlalchemy import Column, ...

class NdaSomething(Base):
    __tablename__ = "nda_something"
    ...
```

If you add models, also add a re-import in [`app/models/agreement.py`](../../models/agreement.py) so existing code using `from app.models import NdaSomething` keeps working. See the `AgreementNegotiationRound` example there.

---

## Step 2 — Register the type in the BE registry

Append the descriptor module path to `TYPE_MODULES` in [`registry.py`](registry.py):

```python
TYPE_MODULES: List[str] = [
    "app.modules.agreements.types.cda.descriptor",
    "app.modules.agreements.types.cta.descriptor",
    "app.modules.agreements.types.nda.descriptor",   # NEW
]
```

`safe_import_type` handles import failures — if your descriptor module crashes at import time, the other types still mount. That isolation only kicks in if you wire through the registry. Don't bypass it by adding a direct `app.include_router` call in the aggregator.

---

## Step 3 — Create the frontend sub-package

Mirror the BE shape under `Frontend-CRM/src/features/agreements/types/<code_lower>/`:

```
Frontend-CRM/src/features/agreements/types/nda/
├── index.ts                     # registers a descriptor
└── components/
    └── NDAWorkflowPanel.tsx     # the type's main UI
```

### `index.ts`

```ts
import type React from 'react'
import NDAWorkflowPanel from './components/NDAWorkflowPanel'
import type { AgreementTypeDescriptor } from '../../registry'

export { NDAWorkflowPanel }

export const ndaTypeDescriptor: AgreementTypeDescriptor = {
  code: 'NDA',
  label: 'NDA',
  Panel: NDAWorkflowPanel as React.ComponentType<any>,
}

export default ndaTypeDescriptor
```

### `components/NDAWorkflowPanel.tsx`

A normal React component. It will be mounted by the shared layer inside an `AgreementTypeErrorBoundary` (see Step 4) — so a render crash here only takes down this type's panel, not the entire Agreements UI.

---

## Step 4 — Register the type in the FE registry

Add the import + descriptor to [`registry.tsx`](../../../../Frontend-CRM/src/features/agreements/registry.tsx):

```ts
import ndaTypeDescriptor from './types/nda'

const descriptors: AgreementTypeDescriptor[] = [
  cdaTypeDescriptor,
  ctaTypeDescriptor,
  ndaTypeDescriptor,   // NEW
]
```

That's all. The shared `<AgreementTypePanel typeCode={agreement.agreement_type} ... />` will now resolve `'NDA'` to your panel, wrapped in an `AgreementTypeErrorBoundary`.

If a caller is using the legacy direct-import path (`import NDAWorkflowPanel from '@/features/agreements/components/NDAWorkflowPanel'`), follow the existing CDA/CTA pattern and add a thin shim file at `components/NDAWorkflowPanel.tsx` that re-exports the real implementation wrapped in `AgreementTypeErrorBoundary`. Most new types won't need a shim — only the legacy callers do.

---

## Step 5 — Test the wiring

Quick sanity checks before opening a PR:

1. **BE imports.** From a Python shell or test, confirm the descriptor loads:
   ```python
   from app.modules.agreements.registry import load_all_types, all_descriptors
   load_all_types()
   print([d.code for d in all_descriptors()])   # should include 'NDA'
   ```
2. **BE router mounted.** Boot the app, hit one of the new endpoints. Check `/docs` — the new routes should appear under their tag.
3. **FE panel renders.** Open an agreement of the new type in the UI; the panel renders. Throw an error inside the panel on purpose; confirm the red `AgreementTypeErrorBoundary` fallback appears and the rest of the page still works.
4. **Hook fires.** If you implemented `<type>_on_status_change`, transition an agreement to the relevant status and confirm the hook ran (look for the matching log line, and the DB side-effect you wrote).
5. **Other types untouched.** Open a CDA and a CTA agreement — make sure their panels still load and their endpoints still respond.

---

## Hard rules — don't break these

1. **No type knows about another.** `types/cda/` must not import from `types/cta/` and vice versa. If two types need the same helper, lift it into `app/modules/agreements/services/` or a sibling shared module.
2. **Shared code never branches on type.** `if agreement.agreement_type == 'NDA'` in `routes/crud.py` or `services/agreement_service.py` is a bug — that's what the registry hooks exist for.
3. **Type packages' `__init__.py` stays light.** Heavy imports there will resurrect the circular-import trap from Phase 1.
4. **Hooks must not commit.** Use `db.flush()` only. The shared dispatcher commits once at the end of the request flow.
5. **Hooks must be defensive.** Anything they touch (templates, sites, study sites) should be guarded — return early with a log line rather than raising. The dispatcher catches and logs, but treating hook failure as "abort the status change" is wrong.

---

## What this refactor was, in one line

Three phases: Phase 1 shuffled CDA + CTA into their own sub-packages with a registry and ErrorBoundary/safe-import isolation; Phase 2 lifted CDA-specific dead code out of shared layers into the CDA package; Phase 3 wired the shared status-change dispatcher to actually call the type hooks. Date stamp: 2026-05-27.
