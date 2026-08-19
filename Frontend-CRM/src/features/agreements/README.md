# Agreements feature

Pattern B feature folder for the agreements domain. This folder is the canonical home for everything related to agreement workflows (CDA, CTA, BUDGET, OTHER).

## Current state (in-progress migration)

The bulk of the agreement UI still lives in `src/components/AgreementTab.tsx` (~2,400 lines). Phase 4.2 of the refactor plan moves that component into this folder and splits it into smaller pieces. This folder is set up to receive that work without further structural decisions.

## Target layout

```
src/features/agreements/
  AgreementTab.tsx            (shell, ~250 lines)
  components/
    AgreementEditorPane.tsx
    AgreementVersionsPane.tsx
    AgreementReviewPane.tsx
    (AgreementBudgetTab.tsx already exists in src/components/ — move here too)
  hooks/
    useAgreementWorkflow.ts   (state machine + status transition logic)
  services/
    agreement.api.ts          (codegen-typed; replaces inline fetch in AgreementTab)
    agreementWorkflow.ts      (already here — stage-mapping helpers)
```

## What's already here

- `services/agreementWorkflow.ts` — moved from `src/utils/agreementWorkflow.ts` so the conceptual-stage helpers and the upcoming feature code live together. Two existing importers (`AgreementTab.tsx`, `AgreementWorkflowStepper.tsx`) have been updated.

## Migration order (future sessions)

1. Move `src/components/AgreementBudgetTab.tsx` → `src/features/agreements/components/AgreementBudgetTab.tsx`.
2. Extract the state machine inside `AgreementTab.tsx` (the ~600-line block that handles `getLockReason`, status transitions, OTP-send flow) into `hooks/useAgreementWorkflow.ts`. Keep the same public API.
3. Move `AgreementTab.tsx` itself into this folder; carve sub-tabs into `components/AgreementEditorPane.tsx`, `AgreementVersionsPane.tsx`, `AgreementReviewPane.tsx`.
4. Replace every inline `api.get`/`api.post` call inside the agreement code with calls to `services/agreement.api.ts` (codegen-typed once OpenAPI codegen is in regular use).
5. Add a smoke test in `__tests__/agreementTab.smoke.test.tsx`.

Each step is its own session per the plan's Migration Safety Rules.
