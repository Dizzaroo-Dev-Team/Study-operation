/** Canonical MVR form shape for POST/GET JSON payload (Monitoring Visit Report). */

import {
  createEmptyQuestionComments,
  mergeQuestionComments,
} from "./visitReportSectionQuestionComments";

export type VisitReportYN = "" | "Yes" | "No" | "N/A";
export type VisitReportStatus = "Draft" | "Final" | "Submitted" | "In Review" | "Rejected" | "Approved";
export type MvrTableRow = Record<string, string>;
export type CustomTemplateFieldValues = Record<string, unknown>;

export interface VisitReportFormState {
  schemaVersion: number;
  reportStatus: VisitReportStatus;
  studyTitle: string;
  sponsor: string;
  studyType: string;
  site: string;
  pi: string;
  templateId?: string;
  templateVersion?: number;
  templateName?: string;
  customTemplateFields: CustomTemplateFieldValues;
  /** @deprecated Use visitStartDate; kept for older saved payloads and AI summary. */
  visitDate: string;
  visitStartDate: string;
  visitEndDate: string;
  /** @deprecated Use prevVisitStartDate/prevVisitEndDate; kept for older saved payloads. */
  prevVisitDate: string;
  prevVisitStartDate: string;
  prevVisitEndDate: string;
  prevVisitNA: boolean;
  /** @deprecated Use nextVisitStartDate/nextVisitEndDate; kept for older saved payloads. */
  nextVisitDate: string;
  nextVisitStartDate: string;
  nextVisitEndDate: string;
  nextVisitTbd: boolean;
  visitPurpose: string;
  sitePersonnelRows: MvrTableRow[];
  monitorPersonnelRows: MvrTableRow[];
  otherPersonnelRows: MvrTableRow[];
  /** @deprecated Removed from the report UI; retained so older saved payloads still hydrate safely. */
  ptPlanned?: string;
  ptScreened: string;
  ptEnrolled: string;
  ptActive: string;
  ptDropouts: string;
  ptCompleted: string;
  q21: VisitReportYN;
  q22: VisitReportYN;
  s2Comments: string;
  q3: VisitReportYN;
  /** @deprecated Section 3 sub-questions removed from the report UI; retained so older saved payloads still hydrate safely. */
  q31?: VisitReportYN;
  /** @deprecated See q31. */
  q32?: VisitReportYN;
  /** @deprecated See q31. */
  q33?: VisitReportYN;
  /** @deprecated See q31. */
  q34?: VisitReportYN;
  /** @deprecated See q31. */
  q35?: VisitReportYN;
  /** @deprecated See q31. */
  s3NA?: boolean;
  s3Comments: string;
  q41ec: VisitReportYN;
  q41ra: VisitReportYN;
  q42ec: VisitReportYN;
  q42ra: VisitReportYN;
  q43: VisitReportYN;
  q44: VisitReportYN;
  s4Comments: string;
  docRows: MvrTableRow[];
  q401: VisitReportYN;
  q402: VisitReportYN;
  q403: VisitReportYN;
  q404: VisitReportYN;
  q405: VisitReportYN;
  q406: VisitReportYN;
  q407: VisitReportYN;
  q408: VisitReportYN;
  q409: VisitReportYN;
  q410: VisitReportYN;
  q51: VisitReportYN;
  q52: VisitReportYN;
  q53: VisitReportYN;
  q54: VisitReportYN;
  q55: VisitReportYN;
  q56: VisitReportYN;
  q57: VisitReportYN;
  q58: VisitReportYN;
  q59: VisitReportYN;
  q510: VisitReportYN;
  q511: VisitReportYN;
  s5NA: boolean;
  icfRows: MvrTableRow[];
  q61: VisitReportYN;
  q62: VisitReportYN;
  q63: VisitReportYN;
  q64: VisitReportYN;
  q65: VisitReportYN;
  q66: VisitReportYN;
  q67: VisitReportYN;
  q68: VisitReportYN;
  s6NA: boolean;
  sdvRows: MvrTableRow[];
  s8NA: boolean;
  q81: VisitReportYN;
  q82: VisitReportYN;
  q83: VisitReportYN;
  q84: VisitReportYN;
  q85: VisitReportYN;
  q86: VisitReportYN;
  s9NA: boolean;
  q91: VisitReportYN;
  q92: VisitReportYN;
  q111: VisitReportYN;
  q112: VisitReportYN;
  q113: VisitReportYN;
  q114: VisitReportYN;
  q115: VisitReportYN;
  q116: VisitReportYN;
  q117: VisitReportYN;
  q118: VisitReportYN;
  q119: VisitReportYN;
  s11NA: boolean;
  additionalComments?: string;
  actionRows: MvrTableRow[];
  questionComments: Record<string, string>;
  summary: string;
  preparedByName: string;
  preparedBySignature: string;
  preparedByDate: string;
  reviewedByName: string;
  reviewedBySignature: string;
  reviewedByDate: string;
  /** @deprecated Legacy payloads only — migrated to preparedByName */
  monitorName?: string;
  /** @deprecated Legacy payloads only — migrated to reviewedByName */
  reviewerName?: string;
  /** @deprecated Legacy payloads only */
  sponsorName?: string;
  sponsorComments?: string;
}

const YN_FIELD_KEYS = new Set([
  "q21", "q22", "q31", "q32", "q33", "q34", "q35", "q41ec", "q41ra", "q42ec", "q42ra", "q43", "q44",
  "q401", "q402", "q403", "q404", "q405", "q406", "q407", "q408", "q409", "q410",
  "q51", "q52", "q53", "q54", "q55", "q56", "q57", "q58", "q59", "q510", "q511",   "q61", "q62", "q63", "q64", "q65", "q66", "q67", "q68",
  "q81", "q82", "q83", "q84", "q85", "q86",
  "q91", "q92",
  "q111", "q112", "q113", "q114", "q115", "q116", "q117", "q118", "q119",
]);

const ROW_ARRAY_KEYS: (keyof VisitReportFormState)[] = [
  "sitePersonnelRows",
  "monitorPersonnelRows",
  "otherPersonnelRows",
  "docRows",
  "icfRows",
  "sdvRows",
  "actionRows",
];

/** Merge server JSON onto defaults (safe partial update). */
export function mergeVisitReportPayload(raw: unknown): VisitReportFormState {
  const base = createInitialVisitReportForm();
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return base;
  const r = raw as Record<string, unknown>;
  const out: VisitReportFormState = { ...base };

  // Handle backward compatibility: migrate old staffRows to new personnel fields
  if (r.staffRows && Array.isArray(r.staffRows) && r.staffRows.length > 0 && !r.sitePersonnelRows) {
    r.sitePersonnelRows = r.staffRows;
  }

  const keys = Object.keys(base) as (keyof VisitReportFormState)[];
  for (const key of keys) {
    const val = r[key as string];
    if (val === undefined) continue;

    if (ROW_ARRAY_KEYS.includes(key)) {
      if (Array.isArray(val) && val.length > 0) {
        (out as unknown as Record<string, unknown>)[key as string] = val.map((row: unknown) =>
          row && typeof row === "object" && !Array.isArray(row)
            ? { ...(row as MvrTableRow) }
            : {},
        );
      }
      continue;
    }

    if (key === "schemaVersion" && typeof val === "number") {
      out.schemaVersion = val;
      continue;
    }

    if (key === "reportStatus" && isStatus(val)) {
      out.reportStatus = val;
      continue;
    }

    if (key === "questionComments") {
      out.questionComments = mergeQuestionComments(val);
      continue;
    }

    const baseVal = base[key];
    if (typeof baseVal === "boolean" && typeof val === "boolean") {
      (out as unknown as Record<string, unknown>)[key as string] = val;
      continue;
    }

    if (typeof baseVal === "string" && typeof val === "string") {
      if (YN_FIELD_KEYS.has(key as string)) {
        if (isYn(val)) (out as unknown as Record<string, unknown>)[key as string] = val;
      } else {
        (out as unknown as Record<string, unknown>)[key as string] = val;
      }
    }
  }

  if (!out.preparedByName.trim() && typeof r.monitorName === "string") {
    out.preparedByName = r.monitorName;
  }
  if (!out.reviewedByName.trim() && typeof r.reviewerName === "string") {
    out.reviewedByName = r.reviewerName;
  }

  return normalizeVisitReportDates(out);
}

/** Map legacy single visitDate to start/end; mirror start into visitDate for consumers. */
export function normalizeVisitReportDates(form: VisitReportFormState): VisitReportFormState {
  const legacy = (form.visitDate ?? "").trim();
  const start = (form.visitStartDate ?? "").trim();
  const end = (form.visitEndDate ?? "").trim();
  if (!start && legacy) form.visitStartDate = legacy;
  if (!end && legacy) form.visitEndDate = legacy;
  if (!(form.visitDate ?? "").trim() && (form.visitStartDate ?? "").trim()) {
    form.visitDate = form.visitStartDate;
  }

  // Map legacy single prevVisitDate/nextVisitDate onto the new start/end pairs.
  const prevLegacy = (form.prevVisitDate ?? "").trim();
  if (!(form.prevVisitStartDate ?? "").trim() && prevLegacy) form.prevVisitStartDate = prevLegacy;
  if (!(form.prevVisitEndDate ?? "").trim() && prevLegacy) form.prevVisitEndDate = prevLegacy;

  const nextLegacy = (form.nextVisitDate ?? "").trim();
  if (!(form.nextVisitStartDate ?? "").trim() && nextLegacy) form.nextVisitStartDate = nextLegacy;
  if (!(form.nextVisitEndDate ?? "").trim() && nextLegacy) form.nextVisitEndDate = nextLegacy;

  return form;
}

function isYn(v: unknown): v is VisitReportYN {
  return v === "" || v === "Yes" || v === "No" || v === "N/A";
}

function isStatus(v: unknown): v is VisitReportStatus {
  return (
    v === "Draft" ||
    v === "Final" ||
    v === "Submitted" ||
    v === "In Review" ||
    v === "Rejected" ||
    v === "Approved"
  );
}

/** Default form used on first load and for missing stored keys (after schema merges). */
export function createInitialVisitReportForm(): VisitReportFormState {
  return {
    schemaVersion: 1,
    reportStatus: "Draft",
    customTemplateFields: {},
    studyTitle: "",
    sponsor: "",
    studyType: "",
    site: "",
    pi: "",
    visitDate: "",
    visitStartDate: "",
    visitEndDate: "",
    prevVisitDate: "",
    prevVisitStartDate: "",
    prevVisitEndDate: "",
    prevVisitNA: false,
    nextVisitDate: "",
    nextVisitStartDate: "",
    nextVisitEndDate: "",
    nextVisitTbd: false,
    visitPurpose: "",
    sitePersonnelRows: [{ name: "", role: "" }],
    monitorPersonnelRows: [{ name: "", role: "" }],
    otherPersonnelRows: [{ name: "", role: "" }],
    ptScreened: "",
    ptEnrolled: "",
    ptActive: "",
    ptDropouts: "",
    ptCompleted: "",
    q21: "",
    q22: "",
    s2Comments: "",
    q3: "",
    q31: "",
    q32: "",
    q33: "",
    q34: "",
    q35: "",
    s3NA: false,
    s3Comments: "",
    q41ec: "",
    q41ra: "",
    q42ec: "",
    q42ra: "",
    q43: "",
    q44: "",
    s4Comments: "",
    docRows: [
      { type: "Protocol / CIP", version: "", ecDate: "", raDate: "" },
      { type: "PIC", version: "", ecDate: "", raDate: "" },
      { type: "IB / SmPC / IFU", version: "", ecDate: "", raDate: "" },
      { type: "CRF", version: "", ecDate: "", raDate: "" },
      { type: "Diaries", version: "", ecDate: "", raDate: "" },
      { type: "Questionnaires", version: "", ecDate: "", raDate: "" },
    ],
    q401: "",
    q402: "",
    q403: "",
    q404: "",
    q405: "",
    q406: "",
    q407: "",
    q408: "",
    q409: "",
    q410: "",
    q51: "",
    q52: "",
    q53: "",
    q54: "",
    q55: "",
    q56: "",
    q57: "",
    q58: "",
    q59: "",
    q510: "",
    q511: "",
    s5NA: false,
    icfRows: [{
      screeningNo: "",
      correctIcfVersion: "",
      consentBeforeProcedures: "",
      subjectSignatureDate: "",
      personObtainingConsent: "",
      piSignatureDate: "",
      comments: "",
    }],
    q61: "",
    q62: "",
    q63: "",
    q64: "",
    q65: "",
    q66: "",
    q67: "",
    q68: "",
    s6NA: false,
    sdvRows: [{ screeningNo: "", subjectId: "", visitCycle: "", comments: "" }],
    s8NA: false,
    q81: "",
    q82: "",
    q83: "",
    q84: "",
    q85: "",
    q86: "",
    s9NA: false,
    q91: "",
    q92: "",
    q111: "",
    q112: "",
    q113: "",
    q114: "",
    q115: "",
    q116: "",
    q117: "",
    q118: "",
    q119: "",
    s11NA: false,
    actionRows: [
      { num: "1", description: "", responsible: "", deadline: "", opened: "", closed: "" },
    ],
    questionComments: createEmptyQuestionComments(),
    summary: "",
    preparedByName: "",
    preparedBySignature: "",
    preparedByDate: "",
    reviewedByName: "",
    reviewedBySignature: "",
    reviewedByDate: "",
  };
}
