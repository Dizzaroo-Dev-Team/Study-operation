import type { MvrFieldDef, MvrTemplateDto, MvrTemplateSchema } from "../types/mvrTemplate";

const PAYLOAD_SYSTEM_KEYS = new Set([
  "reportStatus",
  "schemaVersion",
  "submissionData",
  "archivedData",
  "templateId",
  "templateVersion",
  "templateName",
  "templateSnapshot",
  "customTemplateFields",
  "rejectionReason",
  "revisionBaseline",
]);

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Field ids present in saved report data (submission, archive, or legacy top-level keys). */
export function reportDataFieldIds(payload: Record<string, unknown>): Set<string> {
  const ids = new Set<string>();
  const sub = payload.submissionData;
  if (isRecord(sub)) {
    for (const key of Object.keys(sub)) {
      if (key.trim()) ids.add(key);
    }
  }
  const arch = payload.archivedData;
  if (isRecord(arch)) {
    for (const key of Object.keys(arch)) {
      if (key.trim()) ids.add(key);
    }
  }
  // Legacy-layout custom templates store answers keyed by field id under
  // customTemplateFields — count those or every custom field gets filtered out.
  const custom = payload.customTemplateFields;
  if (isRecord(custom)) {
    for (const key of Object.keys(custom)) {
      if (key.trim()) ids.add(key);
    }
  }
  for (const key of Object.keys(payload)) {
    if (!PAYLOAD_SYSTEM_KEYS.has(key)) ids.add(key);
  }
  return ids;
}

/** Keep only template fields that exist in the saved report data (plus their section headers). */
export function filterTemplateSchemaToFieldIds(
  schema: MvrTemplateSchema,
  fieldIds: Set<string>,
): MvrTemplateSchema {
  const fields = schema.fields ?? [];
  if (fieldIds.size === 0) return { ...schema, fields: [] };

  const kept: MvrFieldDef[] = [];
  let pendingSection: MvrFieldDef | null = null;

  for (const field of fields) {
    if (field.type === "section") {
      pendingSection = field;
      continue;
    }
    if (fieldIds.has(field.id)) {
      if (pendingSection) {
        kept.push(pendingSection);
        pendingSection = null;
      }
      kept.push(field);
    }
  }

  return { ...schema, fields: kept };
}

export function templateSnapshotFromPayload(
  payload: Record<string, unknown>,
  fallbackTemplateId?: string,
): MvrTemplateDto | null {
  const snap = payload.templateSnapshot;
  if (!isRecord(snap) || !isRecord(snap.schema)) return null;
  return {
    id: String(snap.id ?? fallbackTemplateId ?? ""),
    organizationId: "default",
    name: typeof snap.name === "string" ? snap.name : "MVR Template",
    schema: snap.schema as unknown as MvrTemplateSchema,
    version: typeof snap.version === "number" ? snap.version : 1,
    lifecycleStatus: "published",
    isActive: false,
    updatedAt: null,
  };
}

/** Derive a frozen template for locked reports that predate templateSnapshot storage. */
export function deriveFrozenTemplateFromReport(
  template: MvrTemplateDto,
  payload: Record<string, unknown>,
): MvrTemplateDto {
  const fieldIds = reportDataFieldIds(payload);
  return {
    ...template,
    schema: filterTemplateSchemaToFieldIds(template.schema ?? { fields: [] }, fieldIds),
  };
}
