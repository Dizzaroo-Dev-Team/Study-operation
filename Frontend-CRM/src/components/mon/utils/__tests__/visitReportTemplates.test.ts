/**
 * Visit report template resolution — default (built-in) vs custom templates.
 *
 * These helpers decide which template a report renders with at every stage of
 * the review lifecycle (draft → in review → rejected → approved). A regression
 * here is exactly the class of bug where a rejected/locked report silently
 * falls back to the default template instead of the custom one it was
 * authored with.
 */
import { describe, it, expect } from "vitest";

import {
  reportDataFieldIds,
  filterTemplateSchemaToFieldIds,
  templateSnapshotFromPayload,
  deriveFrozenTemplateFromReport,
} from "../mvrTemplateFreeze";
import {
  legacyFlatFieldValues,
  payloadUsesLegacyLayout,
  shouldUseDynamicReviewBody,
  buildSubmissionDataForReview,
  reportValuesForReview,
} from "../mvrReviewPayload";
import {
  shouldUseDynamicMvrShell,
  isLegacyStaticMvrTemplateSchema,
} from "../../legacyStaticMvrTemplateSchema";
import type { MvrTemplateDto, MvrTemplateSchema } from "../../types/mvrTemplate";

const customSchema: MvrTemplateSchema = {
  fields: [
    { id: "sec_a", type: "section", label: "Section A" },
    { id: "f_summary", type: "textarea", label: "Summary" },
    { id: "f_rating", type: "text", label: "Rating" },
    { id: "sec_b", type: "section", label: "Section B" },
    { id: "f_issues", type: "textarea", label: "Issues" },
  ],
};

const customTemplate: MvrTemplateDto = {
  id: "tpl-custom-1",
  name: "Custom MVR",
  schema: customSchema,
  version: 3,
};

const snapshotPayload: Record<string, unknown> = {
  reportStatus: "Rejected",
  schemaVersion: 1,
  templateId: "tpl-custom-1",
  templateVersion: 3,
  templateSnapshot: {
    id: "tpl-custom-1",
    name: "Custom MVR",
    version: 3,
    schema: customSchema,
  },
  submissionData: { f_summary: "All good", f_rating: "Satisfactory" },
  rejectionReason: "needs numbers",
  revisionBaseline: {
    createdAt: "2026-07-01T00:00:00Z",
    payload: { submissionData: { f_summary: "All good" } },
    submissionData: { f_summary: "All good" },
  },
};

// ── Which renderer: dynamic custom shell vs built-in default form ────────────

describe("shouldUseDynamicMvrShell", () => {
  it("uses the dynamic shell for a real custom template", () => {
    expect(shouldUseDynamicMvrShell(customTemplate)).toBe(true);
  });

  it("falls back to the built-in form when there is no template", () => {
    expect(shouldUseDynamicMvrShell(null)).toBe(false);
    expect(shouldUseDynamicMvrShell(undefined)).toBe(false);
  });

  it("falls back to the built-in form for an empty schema", () => {
    expect(
      shouldUseDynamicMvrShell({ ...customTemplate, schema: { fields: [] } }),
    ).toBe(false);
  });

  it("treats the legacy-static layout as the built-in form, not a custom template", () => {
    const legacy: MvrTemplateDto = {
      ...customTemplate,
      schema: { ...customSchema, layout: "legacy-static-standard" },
    };
    expect(isLegacyStaticMvrTemplateSchema(legacy.schema)).toBe(true);
    expect(shouldUseDynamicMvrShell(legacy)).toBe(false);
  });
});

// ── Frozen snapshot round-trip (what a rejected/locked report renders) ───────

describe("templateSnapshotFromPayload", () => {
  it("reconstructs the frozen custom template from a rejected report payload", () => {
    const dto = templateSnapshotFromPayload(snapshotPayload);
    expect(dto).not.toBeNull();
    expect(dto!.id).toBe("tpl-custom-1");
    expect(dto!.name).toBe("Custom MVR");
    expect(dto!.version).toBe(3);
    expect(dto!.schema).toEqual(customSchema);
    // The snapshot must be usable by the dynamic shell directly.
    expect(shouldUseDynamicMvrShell(dto)).toBe(true);
  });

  it("returns null when the payload has no snapshot (legacy reports)", () => {
    expect(templateSnapshotFromPayload({ reportStatus: "Rejected" })).toBeNull();
  });

  it("returns null for a malformed snapshot instead of rendering garbage", () => {
    expect(
      templateSnapshotFromPayload({ templateSnapshot: { id: "x", schema: "not-an-object" } }),
    ).toBeNull();
  });
});

// ── Which field ids count as report data ─────────────────────────────────────

describe("reportDataFieldIds", () => {
  it("collects ids from submissionData, archivedData and legacy flat keys", () => {
    const ids = reportDataFieldIds({
      submissionData: { f_summary: "x" },
      archivedData: { f_old: "y" },
      studyTitle: "Trial",
    });
    expect(ids.has("f_summary")).toBe(true);
    expect(ids.has("f_old")).toBe(true);
    expect(ids.has("studyTitle")).toBe(true);
  });

  it("counts customTemplateFields answers (legacy-layout custom templates)", () => {
    const ids = reportDataFieldIds({ customTemplateFields: { cf_extra: "answered" } });
    expect(ids.has("cf_extra")).toBe(true);
  });

  it("never treats workflow bookkeeping keys as report fields", () => {
    const ids = reportDataFieldIds(snapshotPayload);
    for (const key of [
      "reportStatus",
      "schemaVersion",
      "templateId",
      "templateVersion",
      "templateName",
      "templateSnapshot",
      "customTemplateFields",
      "rejectionReason",
      "revisionBaseline",
      "submissionData",
      "archivedData",
    ]) {
      expect(ids.has(key)).toBe(false);
    }
    expect(ids.has("f_summary")).toBe(true);
  });
});

// ── Deriving a frozen template when no snapshot was stored ───────────────────

describe("filterTemplateSchemaToFieldIds / deriveFrozenTemplateFromReport", () => {
  it("keeps only answered fields plus their section headers", () => {
    const filtered = filterTemplateSchemaToFieldIds(
      customSchema,
      new Set(["f_summary"]),
    );
    expect(filtered.fields.map((f) => f.id)).toEqual(["sec_a", "f_summary"]);
  });

  it("drops sections whose fields were all removed", () => {
    const filtered = filterTemplateSchemaToFieldIds(
      customSchema,
      new Set(["f_issues"]),
    );
    expect(filtered.fields.map((f) => f.id)).toEqual(["sec_b", "f_issues"]);
  });

  it("returns an empty schema when the report has no data", () => {
    const filtered = filterTemplateSchemaToFieldIds(customSchema, new Set());
    expect(filtered.fields).toEqual([]);
  });

  it("derives a frozen template restricted to the report's own fields", () => {
    const frozen = deriveFrozenTemplateFromReport(customTemplate, {
      submissionData: { f_rating: "Good" },
    });
    expect(frozen.schema.fields.map((f) => f.id)).toEqual(["sec_a", "f_rating"]);
  });

  it("derivation sees customTemplateFields answers too", () => {
    const frozen = deriveFrozenTemplateFromReport(customTemplate, {
      customTemplateFields: { f_issues: "two findings" },
    });
    expect(frozen.schema.fields.map((f) => f.id)).toEqual(["sec_b", "f_issues"]);
  });
});

// ── Reviewer page: values shown / legacy detection / diff inputs ─────────────

describe("legacyFlatFieldValues", () => {
  it("excludes every system key, including templateSnapshot and revisionBaseline", () => {
    const flat = legacyFlatFieldValues(snapshotPayload);
    expect(Object.keys(flat)).toEqual([]);
  });

  it("keeps genuine legacy answers and pulls archived ones back", () => {
    const flat = legacyFlatFieldValues({
      ...snapshotPayload,
      q401: "Yes",
      archivedData: { q402: "No" },
    });
    expect(flat).toEqual({ q401: "Yes", q402: "No" });
  });
});

describe("payloadUsesLegacyLayout", () => {
  it("is false for a pure dynamic-template report (snapshot present)", () => {
    expect(payloadUsesLegacyLayout(snapshotPayload)).toBe(false);
  });

  it("is true when built-in form markers exist", () => {
    expect(payloadUsesLegacyLayout({ studyTitle: "Trial X" })).toBe(true);
  });
});

describe("shouldUseDynamicReviewBody", () => {
  it("renders the dynamic body for a submitted custom-template report", () => {
    expect(shouldUseDynamicReviewBody(customTemplate, snapshotPayload)).toBe(true);
  });

  it("falls back to the legacy review body when there is no template", () => {
    expect(shouldUseDynamicReviewBody(null, snapshotPayload)).toBe(false);
    expect(shouldUseDynamicReviewBody(undefined, snapshotPayload)).toBe(false);
  });

  it("falls back when the template is the legacy-static layout", () => {
    const legacy: MvrTemplateDto = {
      ...customTemplate,
      schema: { ...customSchema, layout: "legacy-static-standard" },
    };
    expect(shouldUseDynamicReviewBody(legacy, snapshotPayload)).toBe(false);
  });
});

describe("buildSubmissionDataForReview / reportValuesForReview", () => {
  it("merges submissionData with customTemplateFields (custom wins)", () => {
    const merged = buildSubmissionDataForReview(
      {
        submissionData: { f_summary: "from submission" },
        customTemplateFields: { f_summary: "from custom", f_rating: "A" },
      },
      customTemplate,
    );
    expect(merged.f_summary).toBe("from custom");
    expect(merged.f_rating).toBe("A");
  });

  it("maps legacy flat keys onto legacy template field ids when no submissionData", () => {
    const legacyTemplate: MvrTemplateDto = {
      ...customTemplate,
      schema: {
        fields: [{ id: "legacy_s1_study_title", type: "text", label: "Study Title" }],
      },
    };
    const merged = buildSubmissionDataForReview(
      { studyTitle: "Trial X" },
      legacyTemplate,
    );
    expect(merged.legacy_s1_study_title).toBe("Trial X");
  });

  it("revision-diff values never contain workflow keys (no bogus diff rows)", () => {
    const values = reportValuesForReview(snapshotPayload, customTemplate);
    expect(values).toEqual({ f_summary: "All good", f_rating: "Satisfactory" });
    expect(values.templateSnapshot).toBeUndefined();
    expect(values.revisionBaseline).toBeUndefined();
    expect(values.rejectionReason).toBeUndefined();
  });

  it("legacy report diff values exclude workflow keys too", () => {
    const values = reportValuesForReview(
      { reportStatus: "Rejected", summary: "text", templateSnapshot: { id: "x", schema: { fields: [] } } },
      null,
    );
    expect(values).toEqual({ summary: "text" });
  });
});
