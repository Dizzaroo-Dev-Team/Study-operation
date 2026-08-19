/** Phase 5 TODO: split into VisitReportLegacyTab, DynamicVisitReportTab, and a thin shell. */
import { useCallback, useEffect, useMemo, useRef, useState, Children, isValidElement, cloneElement, type Dispatch, type SetStateAction } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useStudySite } from "@/contexts/StudySiteContext";
import { Btn, SeverityBadge, StatusBadge } from "../../ui";
import {
  fetchActiveMvrTemplate,
  fetchMvrTemplateById,
  findingIdForDisplay,
  generateVisitSummary,
} from "../../../services/monitorService";
import { useVisitFindings } from "@/lib/queries/useMonitoring";
import { canonicalFindingCategory } from "../../../constants/findingCategories";
import {
  FindingAssigneesCell,
  FindingCorrectiveActionsCell,
  FindingDueDatesCell,
} from "../../findings/FindingActionItemsCell";
import { DynamicVisitReportShell } from "./DynamicVisitReportShell";
import { reportWorkflowSyncKey } from "../../../utils/visitWorkflowPoll";
import type { VisitReportQueryData } from "@/lib/queries/useMonitoring";
import {
  useReportComments,
  useSaveVisitReport,
  useSubmitReportForReview,
  type ReviewComment,
} from "@/lib/queries/useMonitoring";
import { useVisitWorkflow } from "../../../context/VisitWorkflowContext";
import type { MvrFieldDef, MvrTemplateDto } from "../../../types/mvrTemplate";
import {
  deriveFrozenTemplateFromReport,
  templateSnapshotFromPayload,
} from "../../../utils/mvrTemplateFreeze";
import type { VisitOverviewPayload } from "../../../types";
import { MvrReviewerCommentsSidebar } from "./MvrReviewerCommentsSidebar";
import {
  SECTION4_CONSENT_QUESTIONS,
  type Section4ConsentQuestionId,
} from "./visitReportSection4Questions";
import {
  SECTION4_SITE_MANAGEMENT_QUESTIONS,
  isSection4SiteManagementQuestionVisible,
  type Section4SiteManagementQuestionId,
} from "./visitReportSection4SiteManagementQuestions";
import {
  SECTION6_SDV_QUESTIONS,
  type Section6SdvQuestionId,
} from "./visitReportSection6SdvQuestions";
import {
  SECTION10_ESSENTIAL_DOCS_QUESTIONS,
  type Section10EssentialDocsQuestionId,
} from "./visitReportSection10EssentialDocsQuestions";
import {
  SECTION10_IMP_QUESTIONS,
  type Section10ImpQuestionId,
} from "./visitReportSection10ImpQuestions";
import {
  SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS,
  type Section9BiologicalSampleQuestionId,
} from "./visitReportSection9BiologicalSampleQuestions";
import {
  mergeVisitReportPayload,
  normalizeVisitReportDates,
  type VisitReportFormState,
} from "./visitReportFormDefaults";
import { createEmptyQuestionComments, mergeQuestionComments, questionCommentKey } from "./visitReportSectionQuestionComments";
import {
  MVR_COMMENT_FLASH_STYLES,
  scrollToCommentAnchor,
} from "../../../utils/mvrReviewCommentNavigation";
import {
  MvrRestrictedEditProvider,
  useMvrRestrictedFieldEdit,
} from "../../../hooks/useMvrRestrictedRevisionEdit";
import { LEGACY_VISIT_REPORT_FIELD_DEFS } from "../../../utils/legacyVisitReportFieldDefs";
import {
  buildLegacyCustomFieldsByAnchor,
  legacyCustomFieldsAfter,
  shouldUseDynamicMvrShell,
} from "../../../legacyStaticMvrTemplateSchema";
import {
  buildPeoplePresentFromSiteProfile,
  personnelRowsAreEmpty,
} from "../../../utils/peoplePresentAutoFill";
import { useSiteProfile } from "@/lib/queries/useSiteProfile";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toReportInputDate(value: string | undefined | null): string {
  if (!value) return "";
  let raw = value.trim();
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  raw = raw.split("·")[0].trim();
  raw = raw.split(/\s+to\s+|–|—/i)[0].trim();
  const ddMmm = raw.match(/^(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s](\d{4})$/);
  if (ddMmm) {
    const d = new Date(`${ddMmm[1]} ${ddMmm[2]} ${ddMmm[3]}`);
    if (!Number.isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}

// ── design tokens (override via CSS vars in your theme) ─────────────────────
const C = {
  primary:      "var(--primary,       #1a56db)",
  primaryLight: "var(--primary-light, #e8f0fe)",
  primaryMid:   "var(--primary-mid,   #c7d9fa)",
  text:         "var(--text-primary,  #111827)",
  textSub:      "var(--text-secondary,#6b7280)",
  border:       "var(--border,        #e5e7eb)",
  borderHover:  "var(--border-hover,  #9ca3af)",
  bg:           "var(--bg,            #ffffff)",
  bgSubtle:     "var(--bg-subtle,     #f9fafb)",
  danger:       "var(--danger,        #dc2626)",
  success:      "var(--success,       #16a34a)",
  warning:      "var(--warning,       #d97706)",
  radius:       "10px",
  shadow:       "0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.05)",
  shadowMd:     "0 4px 6px -1px rgba(0,0,0,.07), 0 2px 4px -1px rgba(0,0,0,.04)",
} as const;

// ── shared styles ────────────────────────────────────────────────────────────
const inputBase: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  fontSize: 13.5,
  lineHeight: 1.5,
  color: C.text,
  background: C.bg,
  border: `1.5px solid ${C.border}`,
  borderRadius: 8,
  outline: "none",
  transition: "border-color .15s, box-shadow .15s",
  boxSizing: "border-box",
};

const labelBase: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  fontWeight: 600,
  color: C.textSub,
  marginBottom: 5,
  letterSpacing: ".02em",
  textTransform: "uppercase",
};

// ── helpers ──────────────────────────────────────────────────────────────────
type YNChoice = "Yes" | "No" | "N/A" | "";
const YN_OPTIONS: YNChoice[] = ["", "Yes", "No", "N/A"];

const ynColor = (v: YNChoice): React.CSSProperties => {
  if (v === "Yes") return { borderColor: C.success, background: "#f0fdf4" };
  if (v === "No")  return { borderColor: C.danger,  background: "#fef2f2" };
  if (v === "N/A") return { borderColor: C.borderHover, background: C.bgSubtle };
  return {};
};

function YNSelect({ value, onChange, disabled }: { value: YNChoice; onChange: (v: YNChoice) => void; disabled?: boolean }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as YNChoice)}
      disabled={disabled}
      style={{
        ...inputBase,
        minWidth: 108,
        width: "auto",
        fontWeight: 600,
        fontSize: 12.5,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.7 : 1,
        ...ynColor(value),
      }}
    >
      {YN_OPTIONS.map((o) => (
        <option key={o} value={o}>{o === "" ? "Choose…" : o}</option>
      ))}
    </select>
  );
}

function SectionHeader({ num, title, na, onNaChange, naFieldKey }: {
  num: string; title: string;
  na?: boolean; onNaChange?: (v: boolean) => void;
  naFieldKey?: string;
}) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const naLocked = naFieldKey ? fieldDisabled(naFieldKey) : false;
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      marginBottom: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 28, height: 28, borderRadius: 7,
          background: C.primaryLight, color: C.primary,
          fontSize: 11, fontWeight: 800, flexShrink: 0,
          letterSpacing: "-.01em",
        }}>{num}</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: C.text, letterSpacing: "-.01em" }}>
          {title}
        </span>
      </div>
      {onNaChange !== undefined && (
        <label style={{
          display: "flex", alignItems: "center", gap: 6, cursor: naLocked ? "default" : "pointer",
          fontSize: 12, fontWeight: 600, color: C.textSub,
          padding: "4px 10px", borderRadius: 6,
          border: `1.5px solid ${na ? C.borderHover : C.border}`,
          background: na ? C.bgSubtle : "transparent",
          transition: "all .15s",
          userSelect: "none",
          opacity: naLocked ? 0.7 : 1,
        }}>
          <input
            type="checkbox" checked={na ?? false}
            disabled={naLocked}
            onChange={(e) => onNaChange(e.target.checked)}
            style={{ accentColor: C.primary, width: 13, height: 13 }}
          />
          Not Applicable
        </label>
      )}
    </div>
  );
}

function CheckRow({ num, label, fieldKey, value, onChange, disabled, commentFieldKey, commentValue, onCommentChange }: {
  num: string; label: string; fieldKey?: string; value: YNChoice; onChange: (v: YNChoice) => void; disabled?: boolean;
  commentFieldKey?: string; commentValue?: string; onCommentChange?: (v: string) => void;
}) {
  const fk = fieldKey ?? `q${num.replace(/\./g, "")}`;
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = disabled ?? fieldDisabled(fk);
  const commentLocked = commentFieldKey ? fieldDisabled(commentFieldKey) : locked;
  const showComment = Boolean(onCommentChange);
  return (
    <div
      data-mvr-field={fk}
      data-mvr-comment-anchor={label}
      style={{
      display: "grid",
      gridTemplateColumns: showComment ? "minmax(0, 1fr) auto minmax(140px, 200px)" : "1fr auto",
      gap: 16, alignItems: "center",
      padding: "10px 14px",
      borderRadius: 8,
      marginBottom: 4,
      background: value ? (
        value === "Yes" ? "#f0fdf4" : value === "No" ? "#fef2f2" : C.bgSubtle
      ) : "transparent",
      border: `1.5px solid ${value ? (
        value === "Yes" ? "#bbf7d0" : value === "No" ? "#fecaca" : C.border
      ) : C.border}`,
      transition: "background .15s, border-color .15s",
    }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <span style={{
          fontSize: 11, fontWeight: 700, color: C.primary,
          background: C.primaryLight, borderRadius: 5,
          padding: "2px 6px", flexShrink: 0, marginTop: 1,
          letterSpacing: ".01em",
        }}>{num}</span>
        <span style={{ fontSize: 13.5, color: C.text, lineHeight: 1.45 }}>{label}</span>
      </div>
      <YNSelect value={value} onChange={onChange} disabled={locked} />
      {showComment && (
        <div
          data-mvr-field={commentFieldKey}
          data-mvr-comment-anchor={`${label} — Comment`}
        >
          <FormInput
            value={commentValue ?? ""}
            onChange={(e) => onCommentChange?.(e.target.value)}
            placeholder="Comment…"
            disabled={commentLocked}
            style={{ fontSize: 12.5, padding: "7px 10px" }}
          />
        </div>
      )}
    </div>
  );
}

// ── card & field wrappers ────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: C.bg,
      border: `1.5px solid ${C.border}`,
      borderRadius: C.radius,
      padding: "20px 22px",
      boxShadow: C.shadow,
      marginBottom: 14,
      ...style,
    }}>{children}</div>
  );
}

function applyFieldLockToChildren(children: React.ReactNode, locked: boolean): React.ReactNode {
  return Children.map(children, (child) => {
    if (!isValidElement(child)) return child;
    const childProps = child.props as { disabled?: boolean; children?: React.ReactNode };
    const isFormControl =
      child.type === FormInput ||
      child.type === FormTextarea ||
      child.type === FormSelect ||
      child.type === "input" ||
      child.type === "textarea" ||
      child.type === "select";
    if (isFormControl) {
      return cloneElement(child, {
        disabled: locked || Boolean(childProps.disabled),
      } as { disabled?: boolean });
    }
    if (childProps.children) {
      return cloneElement(child, {}, applyFieldLockToChildren(childProps.children, locked));
    }
    return child;
  });
}

function Field({ label, fieldKey, children, full }: {
  label: string; fieldKey?: string; children: React.ReactNode; full?: boolean;
}) {
  const fk = fieldKey ?? label;
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = fieldDisabled(fk);
  return (
    <div
      data-mvr-field={fk}
      data-mvr-comment-anchor={label}
      style={{ gridColumn: full ? "1 / -1" : undefined }}
    >
      <label style={labelBase}>{label}</label>
      {applyFieldLockToChildren(children, locked)}
    </div>
  );
}

const DATE_INPUT_PLACEHOLDER = "DD-MM-YYYY";

const MVR_DATE_INPUT_STYLES = `
  input.mvr-date-input--empty::-webkit-datetime-edit,
  input.mvr-date-input--empty::-webkit-datetime-edit-fields-wrapper {
    color: transparent;
  }
`;

function FormInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { type, value, style, className, onFocus, onBlur, ...rest } = props;
  const focusHandler = (e: React.FocusEvent<HTMLInputElement>) => {
    e.currentTarget.style.borderColor = C.primary;
    e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`;
    onFocus?.(e);
  };
  const blurHandler = (e: React.FocusEvent<HTMLInputElement>) => {
    e.currentTarget.style.borderColor = C.border;
    e.currentTarget.style.boxShadow = "none";
    onBlur?.(e);
  };

  if (type === "date") {
    const hasValue = Boolean(value);
    return (
      <div style={{ position: "relative", width: "100%" }}>
        {!hasValue && (
          <span
            aria-hidden
            style={{
              position: "absolute",
              left: 12,
              top: "50%",
              transform: "translateY(-50%)",
              color: "#9ca3af",
              pointerEvents: "none",
              fontSize: 13,
              zIndex: 1,
            }}
          >
            {DATE_INPUT_PLACEHOLDER}
          </span>
        )}
        <input
          {...rest}
          type="date"
          value={value ?? ""}
          className={[className, !hasValue ? "mvr-date-input--empty" : ""].filter(Boolean).join(" ") || undefined}
          style={{ ...inputBase, ...style }}
          onFocus={focusHandler}
          onBlur={blurHandler}
        />
      </div>
    );
  }

  return (
    <input
      {...props}
      style={{ ...inputBase, ...style }}
      onFocus={focusHandler}
      onBlur={blurHandler}
    />
  );
}

function FormTextarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      style={{ ...inputBase, resize: "vertical", minHeight: 80, ...props.style }}
      onFocus={(e) => { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; }}
      onBlur={(e)  => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
    />
  );
}

function FormSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      style={{ ...inputBase, cursor: "pointer", ...props.style }}
      onFocus={(e) => { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; }}
      onBlur={(e)  => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
    />
  );
}

const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
  gap: "14px 18px",
};

function CommentsField({ fieldKey, value, onChange, placeholder }: {
  fieldKey: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = fieldDisabled(fieldKey);
  return (
    <div
      data-mvr-field={fieldKey}
      data-mvr-comment-anchor="Comments"
      style={{ gridColumn: "1 / -1", marginTop: 4 }}
    >
      <label style={labelBase}>Comments</label>
      <FormTextarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={locked}
      />
    </div>
  );
}

// ── dynamic table ────────────────────────────────────────────────────────────
type Row = Record<string, string>;

const TABLE_YES_NO_OPTIONS = ["", "Yes", "No"] as const;
const TABLE_CONSENT_OBTAINED_BY_OPTIONS = [
  "",
  "Principal Investigator (PI)",
  "Sub-Investigator",
] as const;

type TableColumn = {
  key: string;
  label: string;
  type?: "date" | "text" | "yn" | "select";
  options?: readonly string[];
};

const ICF_REVIEW_TABLE_COLUMNS: TableColumn[] = [
  { key: "screeningNo", label: "Subject screening No." },
  { key: "correctIcfVersion", label: "ICF Version Used (Version No. & Date)" },
  { key: "consentBeforeProcedures", label: "Consent Obtained Before Procedures", type: "yn" },
  { key: "subjectSignatureDate", label: "Subject Signature Date", type: "date" },
  {
    key: "personObtainingConsent",
    label: "Consent obtained by",
    type: "select",
    options: TABLE_CONSENT_OBTAINED_BY_OPTIONS,
  },
  { key: "piSignatureDate", label: "Investigator Signature Date", type: "date" },
  { key: "comments", label: "Comments" },
];

const EMPTY_ICF_REVIEW_ROW: Row = {
  screeningNo: "",
  correctIcfVersion: "",
  consentBeforeProcedures: "",
  subjectSignatureDate: "",
  personObtainingConsent: "",
  piSignatureDate: "",
  comments: "",
};

const SDV_REVIEW_TABLE_COLUMNS: TableColumn[] = [
  { key: "screeningNo", label: "Subject Screening No." },
  { key: "subjectId", label: "Subject ID" },
  { key: "visitCycle", label: "Visit / Cycle" },
  { key: "comments", label: "Comments" },
];

const EMPTY_SDV_REVIEW_ROW: Row = {
  screeningNo: "",
  subjectId: "",
  visitCycle: "",
  comments: "",
};

function DynamicTable({ cols, rows, onChange, onAdd, onRemove, disabled, fieldKey }: {
  cols: TableColumn[];
  rows: Row[];
  onChange: (idx: number, key: string, val: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  disabled?: boolean;
  fieldKey?: string;
}) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = disabled ?? (fieldKey ? fieldDisabled(fieldKey) : false);
  return (
    <div data-mvr-field={fieldKey} style={{ marginTop: 10, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                data-mvr-field-label={c.label}
                style={{
                textAlign: "left", padding: "8px 10px",
                background: C.bgSubtle,
                borderBottom: `2px solid ${C.border}`,
                borderTop: `1.5px solid ${C.border}`,
                color: C.textSub, fontWeight: 700,
                whiteSpace: "nowrap", fontSize: 11,
                letterSpacing: ".04em", textTransform: "uppercase",
              }}>
                {c.label}
              </th>
            ))}
            <th style={{
              width: 36, background: C.bgSubtle,
              borderBottom: `2px solid ${C.border}`,
              borderTop: `1.5px solid ${C.border}`,
            }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? C.bg : C.bgSubtle }}>
              {cols.map((c) => (
                <td key={c.key} style={{ padding: "5px 8px", borderBottom: `1px solid ${C.border}` }}>
                  {c.type === "yn" ? (
                    <select
                      value={row[c.key] ?? ""}
                      onChange={(e) => onChange(i, c.key, e.target.value)}
                      disabled={locked}
                      style={{
                        ...inputBase,
                        minWidth: 96,
                        width: "100%",
                        fontWeight: 600,
                        fontSize: 12.5,
                        padding: "5px 8px",
                        cursor: locked ? "default" : "pointer",
                        opacity: locked ? 0.7 : 1,
                        ...ynColor((row[c.key] ?? "") as YNChoice),
                      }}
                    >
                      {TABLE_YES_NO_OPTIONS.map((o) => (
                        <option key={o || "empty"} value={o}>{o === "" ? "Choose…" : o}</option>
                      ))}
                    </select>
                  ) : c.type === "select" ? (
                    <select
                      value={row[c.key] ?? ""}
                      onChange={(e) => onChange(i, c.key, e.target.value)}
                      disabled={locked}
                      style={{
                        ...inputBase,
                        minWidth: 120,
                        width: "100%",
                        fontSize: 12.5,
                        padding: "5px 8px",
                        cursor: locked ? "default" : "pointer",
                        opacity: locked ? 0.7 : 1,
                      }}
                    >
                      {(c.options ?? [""]).map((o) => (
                        <option key={o || "empty"} value={o}>{o === "" ? "Choose…" : o}</option>
                      ))}
                    </select>
                  ) : c.type === "date" ? (
                    <FormInput
                      type="date"
                      value={row[c.key] ?? ""}
                      onChange={(e) => onChange(i, c.key, e.target.value)}
                      disabled={locked}
                      style={{
                        fontSize: 12.5,
                        padding: "5px 8px",
                        opacity: locked ? 0.7 : 1,
                      }}
                    />
                  ) : (
                  <input
                    type="text"
                    value={row[c.key] ?? ""}
                    onChange={(e) => onChange(i, c.key, e.target.value)}
                    disabled={locked}
                    style={{
                      ...inputBase, fontSize: 12.5, padding: "5px 8px",
                      opacity: locked ? 0.7 : 1,
                    }}
                    onFocus={(e) => { if (!locked) { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; } }}
                    onBlur={(e)  => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
                  />
                  )}
                </td>
              ))}
              {!locked && (
              <td style={{ padding: "5px 8px", textAlign: "center", borderBottom: `1px solid ${C.border}` }}>
                <button
                  type="button" onClick={() => onRemove(i)}
                  title="Remove row"
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: C.textSub, fontSize: 16, lineHeight: 1, borderRadius: 4,
                    width: 24, height: 24, display: "inline-flex",
                    alignItems: "center", justifyContent: "center",
                    transition: "color .1s, background .1s",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = C.danger; e.currentTarget.style.background = "#fef2f2"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = C.textSub; e.currentTarget.style.background = "none"; }}
                >×</button>
              </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!locked && (
      <button
        type="button" onClick={onAdd}
        style={{
          marginTop: 8, fontSize: 12, fontWeight: 600,
          background: "none",
          border: `1.5px dashed ${C.primaryMid}`,
          borderRadius: 7, padding: "6px 14px",
          cursor: "pointer", color: C.primary,
          display: "flex", alignItems: "center", gap: 5,
          transition: "background .15s, border-color .15s",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = C.primaryLight; e.currentTarget.style.borderColor = C.primary; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "none"; e.currentTarget.style.borderColor = C.primaryMid; }}
      >
        <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> Add row
      </button>
      )}
    </div>
  );
}

function useTable(initial: Row[]): [Row[], (i: number, k: string, v: string) => void, () => void, (i: number) => void, Dispatch<SetStateAction<Row[]>>] {
  const [rows, setRows] = useState<Row[]>(initial);
  const change = (i: number, k: string, v: string) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [k]: v } : row)));
  const add = () => setRows((r) => [...r, {}]);
  const remove = (i: number) => setRows((r) => r.filter((_, idx) => idx !== i));
  return [rows, change, add, remove, setRows];
}

function emptyCustomTemplateRow(cols: { id: string }[]): Row {
  const row: Row = {};
  cols.forEach((col) => {
    row[col.id] = "";
  });
  return row;
}

function CustomTemplateField({
  field,
  value,
  onChange,
}: {
  field: MvrFieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = fieldDisabled(field.id);
  const required = field.required ? <span style={{ color: C.danger, marginLeft: 3 }}>*</span> : null;
  const label = field.label?.trim() || field.id;

  if (field.type === "section") {
    return (
      <div
        data-mvr-field={field.id}
        data-mvr-comment-anchor={label}
        style={{ gridColumn: "1 / -1", paddingTop: 6, borderTop: `1px solid ${C.border}` }}
      >
        <div style={{ fontSize: 13.5, fontWeight: 700, color: C.text, marginBottom: field.content ? 4 : 0 }}>
          {label}
        </div>
        {field.content ? (
          <div style={{ fontSize: 12.5, color: C.textSub, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
            {field.content}
          </div>
        ) : null}
      </div>
    );
  }

  if (field.type === "textarea") {
    return (
      <Field label={label} fieldKey={field.id} full>
        <FormTextarea
          value={typeof value === "string" ? value : ""}
          placeholder={field.placeholder || ""}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
          style={{ minHeight: 110 }}
        />
      </Field>
    );
  }

  if (field.type === "number") {
    return (
      <Field label={label} fieldKey={field.id}>
        <FormInput
          type="number"
          value={typeof value === "number" || typeof value === "string" ? String(value) : ""}
          placeholder={field.placeholder || ""}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
        />
      </Field>
    );
  }

  if (field.type === "date") {
    return (
      <Field label={label} fieldKey={field.id}>
        <FormInput
          type="date"
          value={typeof value === "string" ? value : ""}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
        />
      </Field>
    );
  }

  if (field.type === "checkbox") {
    return (
      <div data-mvr-field={field.id} data-mvr-comment-anchor={label}>
        <label style={{ ...labelBase, display: "flex", alignItems: "center", gap: 8, cursor: locked ? "default" : "pointer" }}>
          <input
            type="checkbox"
            checked={value === true}
            disabled={locked}
            onChange={(e) => onChange(e.target.checked)}
            style={{ accentColor: C.primary, width: 14, height: 14 }}
          />
          {label}{required}
        </label>
      </div>
    );
  }

  if (field.type === "radio" || field.type === "select") {
    const options = (field.options?.length ? field.options : ["Yes", "No", "N/A"]).filter((o) => o.trim());
    return (
      <Field label={label} fieldKey={field.id}>
        <FormSelect
          value={typeof value === "string" ? value : ""}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Choose...</option>
          {options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </FormSelect>
      </Field>
    );
  }

  if (field.type === "multiselect") {
    const options = (field.options?.length ? field.options : ["Yes", "No", "N/A"]).filter((o) => o.trim());
    const selected = Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
    return (
      <div data-mvr-field={field.id} data-mvr-comment-anchor={label} style={{ gridColumn: "1 / -1" }}>
        <label style={labelBase}>{label}{required}</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {options.map((option) => (
            <CheckLabel
              key={option}
              checked={selected.includes(option)}
              onChange={(checked) => {
                onChange(checked ? [...selected, option] : selected.filter((item) => item !== option));
              }}
              fieldKey={field.id}
            >
              {option}
            </CheckLabel>
          ))}
        </div>
      </div>
    );
  }

  if (field.type === "table") {
    const cols = field.columns?.length ? field.columns : [{ id: "col_a", label: "Column A" }];
    const rows = Array.isArray(value) && value.length
      ? value.map((row) => (isRecord(row) ? row as Row : emptyCustomTemplateRow(cols)))
      : [emptyCustomTemplateRow(cols)];
    const patchRows = (next: Row[]) => onChange(next);

    return (
      <div data-mvr-field={field.id} data-mvr-comment-anchor={label} style={{ gridColumn: "1 / -1" }}>
        <label style={labelBase}>{label}{required}</label>
        <DynamicTable
          fieldKey={field.id}
          disabled={locked}
          cols={cols.map((col) => ({ key: col.id, label: col.label }))}
          rows={rows}
          onChange={(idx, key, val) => patchRows(rows.map((row, rowIdx) => rowIdx === idx ? { ...row, [key]: val } : row))}
          onAdd={() => patchRows([...rows, emptyCustomTemplateRow(cols)])}
          onRemove={(idx) => patchRows(rows.filter((_, rowIdx) => rowIdx !== idx))}
        />
      </div>
    );
  }

  return (
    <Field label={label} fieldKey={field.id}>
      <FormInput
        value={typeof value === "string" ? value : ""}
        placeholder={field.placeholder || ""}
        disabled={locked}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

function LegacyCustomTemplateFields({
  fields,
  values,
  onChange,
}: {
  fields: MvrFieldDef[];
  values: Record<string, unknown>;
  onChange: (fieldId: string, value: unknown) => void;
}) {
  if (!fields.length) return null;

  return (
    <>
      {fields.map((field) => (
        <CustomTemplateField
          key={field.id}
          field={field}
          value={values[field.id]}
          onChange={(value) => onChange(field.id, value)}
        />
      ))}
    </>
  );
}

// ── inline checkbox-with-label ───────────────────────────────────────────────
function CheckLabel({ checked, onChange, children, fieldKey }: {
  checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode; fieldKey?: string;
}) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = fieldKey ? fieldDisabled(fieldKey) : false;
  return (
    <label style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12.5, fontWeight: 500, color: C.textSub,
      cursor: locked ? "default" : "pointer", userSelect: "none", whiteSpace: "nowrap",
      opacity: locked ? 0.7 : 1,
    }}>
      <input
        type="checkbox"
        checked={checked}
        disabled={locked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ accentColor: C.primary, width: 13, height: 13 }}
      />
      {children}
    </label>
  );
}

// ── status pill ──────────────────────────────────────────────────────────────
function StatusPill({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string; dot: string }> = {
    Draft:      { bg: "#fef3c7", text: "#92400e", dot: C.warning },
    Final:      { bg: "#dcfce7", text: "#14532d", dot: C.success },
    Submitted:  { bg: "#dbeafe", text: "#1e3a8a", dot: C.primary },
    "In Review":{ bg: "#ede9fe", text: "#4c1d95", dot: "#7c3aed" },
    Approved:   { bg: "#dcfce7", text: "#14532d", dot: C.success },
    Rejected:   { bg: "#fee2e2", text: "#991b1b", dot: C.danger },
  };
  const c = cfg[status] ?? cfg.Draft;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: c.bg, color: c.text,
      fontSize: 11.5, fontWeight: 700, letterSpacing: ".05em",
      padding: "4px 11px", borderRadius: 20,
      textTransform: "uppercase",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot, flexShrink: 0 }} />
      {status}
    </span>
  );
}

// ── main component (legacy static MVR — used when no custom template fields exist) ──
function LockedStandaloneTextarea({
  fieldKey,
  anchorLabel,
  ...props
}: { fieldKey: string; anchorLabel: string } & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { fieldDisabled } = useMvrRestrictedFieldEdit();
  const locked = fieldDisabled(fieldKey);
  return (
    <div data-mvr-field={fieldKey} data-mvr-comment-anchor={anchorLabel}>
      <FormTextarea {...props} disabled={locked || props.disabled} />
    </div>
  );
}

function LegacyRestrictedEditHint() {
  const { restrictedRevision } = useMvrRestrictedFieldEdit();
  if (!restrictedRevision) return null;
  return (
    <div style={{ fontSize: 12, color: "#92400e", marginTop: 6 }}>
      Only fields with reviewer comments are editable. Other fields are read-only until you resubmit.
    </div>
  );
}

function LegacyReportStatusMessage({
  isVisitClosed,
  reportStatus,
  isFormReadOnly,
}: {
  isVisitClosed: boolean;
  reportStatus: VisitReportFormState["reportStatus"];
  isFormReadOnly: boolean;
}) {
  const { restrictedRevision } = useMvrRestrictedFieldEdit();
  if (isVisitClosed) {
    return "This visit has been officially closed. The report is locked for audit compliance.";
  }
  if (reportStatus === "Rejected") {
    return restrictedRevision
      ? "Only fields with reviewer comments are editable. Update those fields and resubmit for review."
      : "Address the reviewer's comments, then resubmit for review.";
  }
  if (isFormReadOnly) {
    return "This report is locked. No edits are permitted.";
  }
  return "Save your progress or submit the report for review.";
}

function VisitReportLegacyTab({ visitId, visitSeq, showToast, onStatusChange, authorEmail: authorEmailProp, isVisitClosed = false, initialReport, initialOverview, activeTemplate }: {
  visitId: string;
  visitSeq?: number;
  showToast: (msg: string, type?: string) => void;
  onStatusChange?: (status: VisitReportFormState["reportStatus"]) => void;
  /** Current user's email — passed to submit-for-review so backend can email them on approve/reject */
  authorEmail?: string;
  isVisitClosed?: boolean;
  initialReport?: VisitReportQueryData | null;
  initialOverview?: VisitOverviewPayload | null;
  activeTemplate?: MvrTemplateDto;
}) {
  const { user } = useAuth();
  const { filteredSites, selectedSiteId, selectedStudyId, studies } = useStudySite();
  // Backs the People Present auto-fill below — Site Personnel comes straight
  // from this site's saved Site Profile contacts.
  const siteProfileQuery = useSiteProfile(selectedSiteId);
  // Backs the Findings section snapshot below (Section 3).
  const visitFindingsQuery = useVisitFindings(visitId);
  const authorEmail = authorEmailProp ?? user?.email ?? "";
  const visitHeaderLabel = visitSeq != null ? `#${visitSeq}` : visitId;

  // ── submit-for-review modal state ──────────────────────────────────────────
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewerEmail, setReviewerEmail]     = useState("");
  const [reviewMessage, setReviewMessage]     = useState("");
  const [submitting, setSubmitting]           = useState(false);

  // ── inline annotations (author view) ──────────────────────────────────────
  const [reviewComments, setReviewComments] = useState<ReviewComment[]>([]);
  const [activeCommentId, setActiveCommentId] = useState<string | null>(null);
  const reportBodyRef = useRef<HTMLDivElement>(null);
  /** Apply server payload once per visit — workflow polling refetches must not wipe in-progress edits. */
  const didHydrateFormRef = useRef(false);

  // ── state ──────────────────────────────────────────────────────────────────
  const [studyTitle, setStudyTitle]     = useState("");
  const [sponsor, setSponsor]           = useState("");
  const [studyType, setStudyType]       = useState("");
  const [site, setSite]                 = useState("");
  const [pi, setPi]                     = useState("");
  const [visitStartDate, setVisitStartDate] = useState("");
  const [visitEndDate, setVisitEndDate]     = useState("");
  const [prevVisitStartDate, setPrevVisitStartDate] = useState("");
  const [prevVisitEndDate, setPrevVisitEndDate] = useState("");
  const [prevVisitNA, setPrevVisitNA]   = useState(false);
  const [nextVisitStartDate, setNextVisitStartDate] = useState("");
  const [nextVisitEndDate, setNextVisitEndDate] = useState("");
  const [nextVisitTbd, setNextVisitTbd] = useState(false);
  const [visitPurpose, setVisitPurpose] = useState("");
  const [sitePersonnelRows, sitePersonnelChange, sitePersonnelAdd, sitePersonnelRemove, setSitePersonnelRows] = useTable([{ name: "", role: "" }]);
  const [monitorPersonnelRows, monitorPersonnelChange, monitorPersonnelAdd, monitorPersonnelRemove, setMonitorPersonnelRows] = useTable([{ name: "", role: "" }]);
  const [otherPersonnelRows, otherPersonnelChange, otherPersonnelAdd, otherPersonnelRemove, setOtherPersonnelRows] = useTable([{ name: "", role: "" }]);

  const [ptScreened, setPtScreened]     = useState("");
  const [ptEnrolled, setPtEnrolled]     = useState("");
  const [ptActive, setPtActive]         = useState("");
  const [ptDropouts, setPtDropouts]     = useState("");
  const [ptCompleted, setPtCompleted]   = useState("");
  const [q21, setQ21]                   = useState<YNChoice>("");
  const [q22, setQ22]                   = useState<YNChoice>("");
  const [s2Comments, setS2Comments]     = useState("");

  const [q3, setQ3] = useState<YNChoice>("");
  const [s3Comments, setS3Comments] = useState("");

  const [q401, setQ401] = useState<YNChoice>("");
  const [q402, setQ402] = useState<YNChoice>("");
  const [q403, setQ403] = useState<YNChoice>("");
  const [q404, setQ404] = useState<YNChoice>("");
  const [q405, setQ405] = useState<YNChoice>("");
  const [q406, setQ406] = useState<YNChoice>("");
  const [q407, setQ407] = useState<YNChoice>("");
  const [q408, setQ408] = useState<YNChoice>("");
  const [q409, setQ409] = useState<YNChoice>("");
  const [q410, setQ410] = useState<YNChoice>("");

  const section4SiteValues = useMemo(
    () => ({ q401, q402, q403, q404, q405, q406, q407, q408, q409, q410 }),
    [q401, q402, q403, q404, q405, q406, q407, q408, q409, q410],
  );

  const section4SiteSetters = useMemo(
    (): Record<Section4SiteManagementQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q401: setQ401,
      q402: setQ402,
      q403: setQ403,
      q404: setQ404,
      q405: setQ405,
      q406: setQ406,
      q407: setQ407,
      q408: setQ408,
      q409: setQ409,
      q410: setQ410,
    }),
    [],
  );

  const [questionComments, setQuestionComments] = useState<Record<string, string>>(createEmptyQuestionComments);

  const getQuestionComment = useCallback(
    (questionId: string) => questionComments[questionCommentKey(questionId)] ?? "",
    [questionComments],
  );

  const setQuestionComment = useCallback((questionId: string, value: string) => {
    const key = questionCommentKey(questionId);
    setQuestionComments((prev) => ({ ...prev, [key]: value }));
  }, []);

  useEffect(() => {
    if (q404 !== "Yes") {
      if (q405) setQ405("");
      setQuestionComments((prev) => {
        const key = questionCommentKey("q405");
        if (!prev[key]) return prev;
        return { ...prev, [key]: "" };
      });
    }
  }, [q404, q405]);

  useEffect(() => {
    if (q406 !== "Yes") {
      if (q407) setQ407("");
      setQuestionComments((prev) => {
        const key = questionCommentKey("q407");
        if (!prev[key]) return prev;
        return { ...prev, [key]: "" };
      });
    }
  }, [q406, q407]);

  const [q41ec, setQ41ec] = useState<YNChoice>("");
  const [q41ra, setQ41ra] = useState<YNChoice>("");
  const [q42ec, setQ42ec] = useState<YNChoice>("");
  const [q42ra, setQ42ra] = useState<YNChoice>("");
  const [q43, setQ43]     = useState<YNChoice>("");
  const [q44, setQ44]     = useState<YNChoice>("");
  const [s4Comments, setS4Comments] = useState("");
  const [docRows, , , , setDocRows] = useTable([
    { type: "Protocol / CIP", version: "", ecDate: "", raDate: "" },
    { type: "PIC",            version: "", ecDate: "", raDate: "" },
    { type: "IB / SmPC / IFU", version: "", ecDate: "", raDate: "" },
    { type: "CRF",            version: "", ecDate: "", raDate: "" },
    { type: "Diaries",        version: "", ecDate: "", raDate: "" },
    { type: "Questionnaires", version: "", ecDate: "", raDate: "" },
  ]);

  const [q51, setQ51] = useState<YNChoice>("");
  const [q52, setQ52] = useState<YNChoice>("");
  const [q53, setQ53] = useState<YNChoice>("");
  const [q54, setQ54] = useState<YNChoice>("");
  const [q55, setQ55] = useState<YNChoice>("");
  const [q56, setQ56] = useState<YNChoice>("");
  const [q57, setQ57] = useState<YNChoice>("");
  const [q58, setQ58] = useState<YNChoice>("");
  const [q59, setQ59] = useState<YNChoice>("");
  const [q510, setQ510] = useState<YNChoice>("");
  const [q511, setQ511] = useState<YNChoice>("");
  const [s5NA, setS5NA] = useState(false);
  const section4Values = useMemo(
    () => ({ q51, q52, q53, q54, q55, q56, q57, q58, q59, q510, q511 }),
    [q51, q52, q53, q54, q55, q56, q57, q58, q59, q510, q511],
  );

  const section4Setters = useMemo(
    (): Record<Section4ConsentQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q51: setQ51,
      q52: setQ52,
      q53: setQ53,
      q54: setQ54,
      q55: setQ55,
      q56: setQ56,
      q57: setQ57,
      q58: setQ58,
      q59: setQ59,
      q510: setQ510,
      q511: setQ511,
    }),
    [],
  );

  const [icfRows, icfChange, icfAdd, icfRemove, setIcfRows] = useTable([EMPTY_ICF_REVIEW_ROW]);

  const [q61, setQ61] = useState<YNChoice>("");
  const [q62, setQ62] = useState<YNChoice>("");
  const [q63, setQ63] = useState<YNChoice>("");
  const [q64, setQ64] = useState<YNChoice>("");
  const [q65, setQ65] = useState<YNChoice>("");
  const [q66, setQ66] = useState<YNChoice>("");
  const [q67, setQ67] = useState<YNChoice>("");
  const [q68, setQ68] = useState<YNChoice>("");
  const [s6NA, setS6NA] = useState(false);

  const section6Values = useMemo(
    () => ({ q61, q62, q63, q64, q65, q66, q67, q68 }),
    [q61, q62, q63, q64, q65, q66, q67, q68],
  );

  const section6Setters = useMemo(
    (): Record<Section6SdvQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q61: setQ61,
      q62: setQ62,
      q63: setQ63,
      q64: setQ64,
      q65: setQ65,
      q66: setQ66,
      q67: setQ67,
      q68: setQ68,
    }),
    [],
  );

  const [sdvRows, sdvChange, sdvAdd, sdvRemove, setSdvRows] = useTable([{ ...EMPTY_SDV_REVIEW_ROW }]);

  const [s8NA, setS8NA] = useState(false);
  const [q81, setQ81] = useState<YNChoice>("");
  const [q82, setQ82] = useState<YNChoice>("");
  const [q83, setQ83] = useState<YNChoice>("");
  const [q84, setQ84] = useState<YNChoice>("");
  const [q85, setQ85] = useState<YNChoice>("");
  const [q86, setQ86] = useState<YNChoice>("");

  const sectionImpValues = useMemo(
    () => ({ q81, q82, q83, q84, q85, q86 }),
    [q81, q82, q83, q84, q85, q86],
  );

  const sectionImpSetters = useMemo(
    (): Record<Section10ImpQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q81: setQ81,
      q82: setQ82,
      q83: setQ83,
      q84: setQ84,
      q85: setQ85,
      q86: setQ86,
    }),
    [],
  );

  const [s9NA, setS9NA] = useState(false);
  const [q91, setQ91] = useState<YNChoice>("");
  const [q92, setQ92] = useState<YNChoice>("");

  const sectionBioSampleValues = useMemo(
    () => ({ q91, q92 }),
    [q91, q92],
  );

  const sectionBioSampleSetters = useMemo(
    (): Record<Section9BiologicalSampleQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q91: setQ91,
      q92: setQ92,
    }),
    [],
  );

  const [q111, setQ111] = useState<YNChoice>("");
  const [q112, setQ112] = useState<YNChoice>("");
  const [q113, setQ113] = useState<YNChoice>("");
  const [q114, setQ114] = useState<YNChoice>("");
  const [q115, setQ115] = useState<YNChoice>("");
  const [q116, setQ116] = useState<YNChoice>("");
  const [q117, setQ117] = useState<YNChoice>("");
  const [q118, setQ118] = useState<YNChoice>("");
  const [q119, setQ119] = useState<YNChoice>("");
  const [s11NA, setS11NA] = useState(false);

  const section10Values = useMemo(
    () => ({ q111, q112, q113, q114, q115, q116, q117, q118, q119 }),
    [q111, q112, q113, q114, q115, q116, q117, q118, q119],
  );

  const section10Setters = useMemo(
    (): Record<Section10EssentialDocsQuestionId, Dispatch<SetStateAction<YNChoice>>> => ({
      q111: setQ111,
      q112: setQ112,
      q113: setQ113,
      q114: setQ114,
      q115: setQ115,
      q116: setQ116,
      q117: setQ117,
      q118: setQ118,
      q119: setQ119,
    }),
    [],
  );

  const [actionRows, , , , setActionRows] = useTable([
    { num: "1", description: "", responsible: "", deadline: "", opened: "", closed: "" },
  ]);
  const [customTemplateFields, setCustomTemplateFields] = useState<Record<string, unknown>>({});
  const [summary, setSummary] = useState("");
  const [preparedByName, setPreparedByName] = useState("");
  const [preparedBySignature, setPreparedBySignature] = useState("");
  const [preparedByDate, setPreparedByDate] = useState("");
  const [reviewedByName, setReviewedByName] = useState("");
  const [reviewedBySignature, setReviewedBySignature] = useState("");
  const [reviewedByDate, setReviewedByDate] = useState("");
  const [reportStatus, setReportStatus] = useState<VisitReportFormState["reportStatus"]>("Draft");
  const [rejectionReason, setRejectionReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);

  useEffect(() => {
    onStatusChange?.(reportStatus);
  }, [reportStatus, onStatusChange]);

  // Editable except while awaiting review, approved, or visit closed — rejected = revision mode.
  const isFormReadOnly =
    reportStatus === "In Review" || reportStatus === "Approved" || isVisitClosed;
  const shouldFetchComments =
    reportStatus === "In Review" ||
    reportStatus === "Approved" ||
    reportStatus === "Rejected" ||
    isVisitClosed ||
    String(initialReport?.payload?.reportStatus ?? "") === "In Review" ||
    String(initialReport?.payload?.reportStatus ?? "") === "Approved" ||
    String(initialReport?.payload?.reportStatus ?? "") === "Rejected";
  const reportCommentsQuery = useReportComments(visitId, shouldFetchComments);
  const saveReportMutation = useSaveVisitReport(visitId);
  const submitForReviewMutation = useSubmitReportForReview(visitId);
  const legacyCustomTemplateFieldsByAnchor = useMemo(
    () => buildLegacyCustomFieldsByAnchor(activeTemplate),
    [activeTemplate],
  );
  const legacyCustomTemplateFields = useMemo(
    () => Array.from(legacyCustomTemplateFieldsByAnchor.values()).flat(),
    [legacyCustomTemplateFieldsByAnchor],
  );
  const customFieldsAfterAnchor = useCallback(
    (...anchorIds: string[]) => legacyCustomFieldsAfter(legacyCustomTemplateFieldsByAnchor, ...anchorIds),
    [legacyCustomTemplateFieldsByAnchor],
  );
  const restrictedFieldDefs = useMemo(
    () => [
      ...LEGACY_VISIT_REPORT_FIELD_DEFS,
      ...legacyCustomTemplateFields.map((field) => ({ id: field.id, label: field.label || field.id })),
    ],
    [legacyCustomTemplateFields],
  );

  const setCustomTemplateField = useCallback((fieldId: string, value: unknown) => {
    setCustomTemplateFields((prev) => ({ ...prev, [fieldId]: value }));
  }, []);

  useEffect(() => {
    if (!shouldFetchComments) {
      setReviewComments([]);
      setActiveCommentId(null);
      return;
    }
    setReviewComments(reportCommentsQuery.data ?? []);
  }, [shouldFetchComments, reportCommentsQuery.data]);

  const handleCommentCardClick = useCallback((comment: ReviewComment) => {
    setActiveCommentId(comment.id);
    const anchor = scrollToCommentAnchor(reportBodyRef.current, comment);
    if (!anchor) {
      showToast("Could not locate this text in the report. Try searching for the quoted snippet.", "info");
    }
  }, [showToast]);

  // ── build / apply payload ──────────────────────────────────────────────────
  // Review-workflow state lives in the saved payload but has no form field here;
  // carry it through saves or a legacy-tab save would wipe the frozen template
  // snapshot and the revision baseline the reviewer diffs against on resubmit.
  const preservedWorkflowFields = (): Record<string, unknown> => {
    const raw = isRecord(initialReport?.payload) ? initialReport.payload : {};
    const keep: Record<string, unknown> = {};
    for (const key of [
      "templateSnapshot",
      "revisionBaseline",
      "rejectionReason",
      "archivedData",
      "submissionData",
    ]) {
      if (raw[key] !== undefined) keep[key] = raw[key];
    }
    return keep;
  };

  const buildPayload = (): VisitReportFormState => normalizeVisitReportDates({
    ...preservedWorkflowFields(),
    schemaVersion: 1, reportStatus, studyTitle, sponsor, studyType, site, pi,
    templateId: activeTemplate?.id,
    templateVersion: activeTemplate?.version,
    templateName: activeTemplate?.name,
    customTemplateFields,
    visitDate: visitStartDate,
    visitStartDate,
    visitEndDate,
    prevVisitDate: prevVisitStartDate,
    prevVisitStartDate, prevVisitEndDate, prevVisitNA,
    nextVisitDate: nextVisitStartDate,
    nextVisitStartDate, nextVisitEndDate, nextVisitTbd, visitPurpose,
    sitePersonnelRows, monitorPersonnelRows, otherPersonnelRows, ptScreened, ptEnrolled, ptActive, ptDropouts, ptCompleted,
    q21, q22, s2Comments, q3, s3Comments,
    q401, q402, q403, q404, q405, q406, q407, q408, q409, q410,
    q41ec, q41ra, q42ec, q42ra, q43, q44, s4Comments, docRows,
    q51, q52, q53, q54, q55, q56, q57, q58, q59, q510, q511, s5NA, icfRows,
    q61, q62, q63, q64, q65, q66, q67, q68, s6NA, sdvRows,
    s8NA, q81, q82, q83, q84, q85, q86,
    s9NA, q91, q92,
    q111, q112, q113, q114, q115, q116, q117, q118, q119, s11NA,
    actionRows, questionComments, summary,
    preparedByName, preparedBySignature, preparedByDate,
    reviewedByName, reviewedBySignature, reviewedByDate,
  });

  const handleGenerateSummary = async () => {
    setIsGeneratingSummary(true);
    try {
      // Build the full form payload but omit the summary field itself
      const { summary: _omit, ...payloadWithoutSummary } = buildPayload();
      const result = await generateVisitSummary(payloadWithoutSummary as unknown as Record<string, unknown>);
      setSummary(result.summary);
      showToast("Summary generated successfully", "success");
    } catch {
      showToast("Failed to generate summary. Check your API key or try again.", "error");
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const applyServerForm = (m: VisitReportFormState) => {
    const dates = normalizeVisitReportDates({ ...m });
    setReportStatus(m.reportStatus); setStudyTitle(m.studyTitle); setSponsor(m.sponsor);
    setStudyType(m.studyType); setSite(m.site); setPi(m.pi);
    setVisitStartDate(dates.visitStartDate);
    setVisitEndDate(dates.visitEndDate);
    setPrevVisitStartDate(m.prevVisitStartDate); setPrevVisitEndDate(m.prevVisitEndDate); setPrevVisitNA(m.prevVisitNA);
    setNextVisitStartDate(m.nextVisitStartDate); setNextVisitEndDate(m.nextVisitEndDate); setNextVisitTbd(m.nextVisitTbd);
    setVisitPurpose(m.visitPurpose); 
    setSitePersonnelRows(m.sitePersonnelRows || [{ name: "", role: "" }]); 
    setMonitorPersonnelRows(m.monitorPersonnelRows || [{ name: "", role: "" }]); 
    setOtherPersonnelRows(m.otherPersonnelRows || [{ name: "", role: "" }]);
    setPtScreened(m.ptScreened); setPtEnrolled(m.ptEnrolled);
    setPtActive(m.ptActive); setPtDropouts(m.ptDropouts); setPtCompleted(m.ptCompleted);
    setQ21(m.q21); setQ22(m.q22); setS2Comments(m.s2Comments);
    setQ3(m.q3); setS3Comments(m.s3Comments);
    setQ401(m.q401); setQ402(m.q402); setQ403(m.q403); setQ404(m.q404); setQ405(m.q405);
    setQ406(m.q406); setQ407(m.q407); setQ408(m.q408); setQ409(m.q409); setQ410(m.q410);
    setQ41ec(m.q41ec); setQ41ra(m.q41ra); setQ42ec(m.q42ec); setQ42ra(m.q42ra);
    setQ43(m.q43); setQ44(m.q44); setS4Comments(m.s4Comments); setDocRows(m.docRows);
    setQ51(m.q51); setQ52(m.q52); setQ53(m.q53); setQ54(m.q54); setQ55(m.q55);
    setQ56(m.q56); setQ57(m.q57); setQ58(m.q58); setQ59(m.q59); setQ510(m.q510); setQ511(m.q511);
    setS5NA(m.s5NA); setIcfRows(m.icfRows);
    setQ61(m.q61); setQ62(m.q62); setQ63(m.q63); setQ64(m.q64); setQ65(m.q65);
    setQ66(m.q66); setQ67(m.q67); setQ68(m.q68); setS6NA(m.s6NA); setSdvRows(m.sdvRows);
    setS8NA(m.s8NA); setQ81(m.q81); setQ82(m.q82); setQ83(m.q83); setQ84(m.q84);
    setQ85(m.q85); setQ86(m.q86);
    setS9NA(m.s9NA); setQ91(m.q91); setQ92(m.q92);
    setQ111(m.q111); setQ112(m.q112); setQ113(m.q113); setQ114(m.q114); setQ115(m.q115);
    setQ116(m.q116); setQ117(m.q117); setQ118(m.q118); setQ119(m.q119);
    setS11NA(m.s11NA);
    setActionRows(m.actionRows);
    setQuestionComments(mergeQuestionComments(m.questionComments));
    setSummary(m.summary);
    setPreparedByName(m.preparedByName);
    setPreparedBySignature(m.preparedBySignature);
    setPreparedByDate(m.preparedByDate);
    setReviewedByName(m.reviewedByName);
    setReviewedBySignature(m.reviewedBySignature);
    setReviewedByDate(m.reviewedByDate);
    setCustomTemplateFields(isRecord(m.customTemplateFields) ? { ...m.customTemplateFields } : {});
    // rejectionReason is stored in raw payload, not in VisitReportFormState
  };

  useEffect(() => {
    didHydrateFormRef.current = false;
  }, [visitId]);

  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      if (!initialReport) {
        if (!didHydrateFormRef.current) setLoading(true);
        return;
      }
      if (didHydrateFormRef.current) return;
      // Wait for the site profile fetch (backs People Present auto-fill below)
      // so we don't hydrate with empty Site Personnel rows on first paint.
      if (selectedSiteId && siteProfileQuery.isLoading) return;

      setLoading(true);
      try {
      const reportRes = initialReport;
      const overviewRes = initialOverview;
      const form = reportRes
        ? mergeVisitReportPayload(reportRes.payload)
        : mergeVisitReportPayload({});
      if (reportRes) {
        const raw = reportRes.payload as Record<string, unknown>;
        setRejectionReason(typeof raw.rejectionReason === "string" ? raw.rejectionReason : "");
        const savedCustom =
          isRecord(raw.customTemplateFields)
            ? raw.customTemplateFields
            : isRecord(raw.submissionData)
              ? raw.submissionData
              : {};
        form.customTemplateFields = { ...savedCustom };
      }
      if (overviewRes) {
        const vd = overviewRes?.visitDetails;
        const sc = overviewRes?.siteContact;
        if (!form.studyTitle)   form.studyTitle   = String(vd?.protocol   || "");
        if (!form.sponsor)      form.sponsor      = String(vd?.sponsor    || "");
        if (!form.studyType)    form.studyType    = String(vd?.visitType  || "");
        if (!form.site)         form.site         = String(sc?.institutionName || "");
        if (!form.pi)           form.pi           = String(sc?.principalInvestigator || "");
        if (!form.visitStartDate) form.visitStartDate = toReportInputDate(vd?.visitDate);
        if (!form.visitEndDate)   form.visitEndDate   = toReportInputDate(vd?.endDate);
        const craName = String(vd?.craName || "").trim();
        if (craName) {
          form.preparedByName = craName;
        } else if (!form.preparedByName.trim() && user?.name) {
          form.preparedByName = user.name;
        }
      }

      const shouldAutoFillPeople =
        form.reportStatus === 'Draft' ||
        (
          personnelRowsAreEmpty(form.sitePersonnelRows) &&
          personnelRowsAreEmpty(form.monitorPersonnelRows) &&
          personnelRowsAreEmpty(form.otherPersonnelRows)
        );

      // Site Personnel / Monitor Personnel come from this site's Site Profile
      // contacts (PI, Sub-I, CRC, Site Head) and the CRA assigned to this
      // visit — not the whole study team — so wait for the site profile
      // fetch to settle before auto-filling.
      if (shouldAutoFillPeople && selectedSiteId && !siteProfileQuery.isLoading) {
        const profile = siteProfileQuery.data;
        const people = buildPeoplePresentFromSiteProfile({
          piName: profile?.pi_name,
          subInvestigatorName: profile?.sub_investigator_name,
          siteCoordinatorName: profile?.site_coordinator_name,
          siteHeadName: profile?.site_head_name,
          craName: overviewRes?.visitDetails?.craName,
        });
        if (!cancelled) {
          form.sitePersonnelRows = people.sitePersonnelRows;
          form.monitorPersonnelRows = people.monitorPersonnelRows;
          form.otherPersonnelRows = people.otherPersonnelRows;
        }
      }

      if (cancelled) return;
      normalizeVisitReportDates(form);
      applyServerForm(form);
      didHydrateFormRef.current = true;
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void hydrate();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitId, initialReport, initialOverview, filteredSites, selectedSiteId, selectedStudyId, studies, siteProfileQuery.isLoading]);

  const reportSyncKey = reportWorkflowSyncKey(initialReport);
  useEffect(() => {
    if (!initialReport) return;
    const raw = initialReport.payload as Record<string, unknown>;
    const rs = raw.reportStatus;
    if (
      rs === "Draft" ||
      rs === "In Review" ||
      rs === "Approved" ||
      rs === "Rejected"
    ) {
      setReportStatus(rs);
    }
    setRejectionReason(typeof raw.rejectionReason === "string" ? raw.rejectionReason : "");
  }, [initialReport, reportSyncKey]);

  const handleSave = async () => {
    if (saving || loading) return;
    setSaving(true);
    try {
      await saveReportMutation.mutateAsync(buildPayload() as unknown as Record<string, unknown>);
      showToast("Visit report saved", "success");
    } catch { showToast("Failed to save visit report", "error"); }
    finally { setSaving(false); }
  };

  const handleSubmit = () => {
    // Open the submit-for-review modal instead of directly submitting
    setShowReviewModal(true);
  };

  const handleConfirmSubmitForReview = useCallback(async () => {
    if (!reviewerEmail.trim()) { showToast("Reviewer email is required", "error"); return; }
    setSubmitting(true);
    try {
      // Save the current form first, then submit for review
      const currentPayload = buildPayload();
      await saveReportMutation.mutateAsync(currentPayload as unknown as Record<string, unknown>);
      await submitForReviewMutation.mutateAsync({
        reviewerEmail: reviewerEmail.trim(),
        message: reviewMessage.trim(),
        authorEmail: authorEmail ?? "",
      });
      setReportStatus("In Review");
      setShowReviewModal(false);
      setReviewerEmail("");
      setReviewMessage("");
      showToast("Report submitted for review — email sent to reviewer", "success");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast(
        typeof detail === "string" && detail
          ? `Failed to submit for review: ${detail}`
          : "Failed to submit for review",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitId, reviewerEmail, reviewMessage, authorEmail, buildPayload]);

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <MvrRestrictedEditProvider
      reportStatus={reportStatus}
      reviewComments={reviewComments}
      reportBodyRef={reportBodyRef}
      baseLocked={isFormReadOnly}
      templateFields={restrictedFieldDefs}
      contentReady={!loading}
    >
    <div className="fade-in" style={{ display: "flex", gap: 20, alignItems: "flex-start", maxWidth: 1240, margin: "0 auto" }}>
      <style>{MVR_DATE_INPUT_STYLES}</style>

      {/* ── Submit for Review Modal ── */}
      {showReviewModal && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(0,0,0,.45)", display: "flex",
          alignItems: "center", justifyContent: "center", padding: 16,
        }}>
          <div style={{
            background: "#fff", borderRadius: 14, padding: 28,
            width: "100%", maxWidth: 460, boxShadow: "0 20px 60px rgba(0,0,0,.25)",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 17, fontWeight: 800, color: C.text }}>Submit for Review</div>
                <div style={{ fontSize: 12.5, color: C.textSub, marginTop: 2 }}>The reviewer will receive a secure email link to open and annotate this report.</div>
              </div>
              <button type="button" onClick={() => setShowReviewModal(false)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: C.textSub, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelBase}>Reviewer Email <span style={{ color: C.danger }}>*</span></label>
              <input
                type="email" placeholder="reviewer@organization.com"
                value={reviewerEmail} onChange={(e) => setReviewerEmail(e.target.value)}
                style={{ ...inputBase }}
                onFocus={(e) => { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={labelBase}>Message (optional)</label>
              <textarea
                placeholder="Add a note to the reviewer…"
                value={reviewMessage} onChange={(e) => setReviewMessage(e.target.value)}
                style={{ ...inputBase, resize: "vertical", minHeight: 80 }}
                onFocus={(e) => { e.currentTarget.style.borderColor = C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <Btn variant="secondary" onClick={() => setShowReviewModal(false)} disabled={submitting}>Cancel</Btn>
              <Btn variant="primary" onClick={() => void handleConfirmSubmitForReview()} disabled={submitting || !reviewerEmail.trim()}>
                {submitting ? "Sending…" : "Send to Reviewer"}
              </Btn>
            </div>
          </div>
        </div>
      )}

      {/* ── LEFT COLUMN ── */}
      <div style={{ flex: 1, minWidth: 0 }}>

      {/* ── Rejection Banner ── */}
      {reportStatus === "Rejected" && (
        <div style={{
          background: "#fef2f2", border: `1.5px solid #fecaca`,
          borderRadius: C.radius, padding: "14px 18px", marginBottom: 14,
          display: "flex", gap: 12, alignItems: "flex-start",
        }}>
          <span style={{ fontSize: 18, flexShrink: 0 }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 700, color: C.danger, fontSize: 13.5, marginBottom: 4 }}>
              Report Rejected — Revision Required
            </div>
            {rejectionReason && (
              <div style={{ fontSize: 13, color: "#374151" }}>
                <strong>Reason:</strong> {rejectionReason}
              </div>
            )}
            {reviewComments.length > 0 && (
              <div style={{ fontSize: 12, color: C.textSub, marginTop: 4 }}>
                {reviewComments.length} inline comment{reviewComments.length !== 1 ? "s" : ""} from the reviewer — click a comment on the right to jump to its location.
                <LegacyRestrictedEditHint />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── In Review Banner ── */}
      {reportStatus === "In Review" && (
        <div style={{
          background: "#ede9fe", border: `1.5px solid #c4b5fd`,
          borderRadius: C.radius, padding: "14px 18px", marginBottom: 14,
          display: "flex", gap: 12, alignItems: "center",
        }}>
          <span style={{ fontSize: 18, flexShrink: 0 }}>🔒</span>
          <div style={{ fontSize: 13, color: "#4c1d95" }}>
            <strong>Under Review</strong> — This report is locked while awaiting reviewer feedback. You can view inline comments once the reviewer submits their response.
          </div>
        </div>
      )}

      {/* ── Approved Banner ── */}
      {reportStatus === "Approved" && (
        <div style={{
          background: "#f0fdf4", border: `1.5px solid #bbf7d0`,
          borderRadius: C.radius, padding: "14px 18px", marginBottom: 14,
          display: "flex", gap: 12, alignItems: "center",
        }}>
          <span style={{ fontSize: 18, flexShrink: 0 }}>✅</span>
          <div style={{ fontSize: 13, color: "#14532d" }}>
            <strong>Approved</strong> — This report has been approved and locked. No further edits are allowed.
          </div>
        </div>
      )}

      <div ref={reportBodyRef} style={{ position: "relative" }}>
      {/* Locked overlay — prevents interaction when In Review / Approved / Closed */}
      {(reportStatus === "In Review" || reportStatus === "Approved" || isVisitClosed) && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 5,
          borderRadius: C.radius,
          cursor: "not-allowed",
        }} />
      )}

      {/* ── Header ── */}
      <Card style={{
        background: `linear-gradient(135deg, #1a56db 0%, #1e40af 100%)`,
        border: "none", color: "#fff", marginBottom: 20,
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", opacity: .7, marginBottom: 4 }}>
              Monitoring Visit Report (MVR)
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-.02em", lineHeight: 1.2 }}>
              Visit {visitHeaderLabel}
            </div>
            {loading && (
              <div style={{ fontSize: 12, opacity: .7, marginTop: 6, display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                  display: "inline-block", width: 10, height: 10, borderRadius: "50%",
                  border: "2px solid rgba(255,255,255,.4)", borderTopColor: "#fff",
                  animation: "spin 1s linear infinite",
                }} />
                Loading saved report…
              </div>
            )}
          </div>
          <StatusPill status={reportStatus} />
        </div>
      </Card>

      {/* ── 1. Study & Visit Details ── */}
      <Card>
        <SectionHeader num="1" title="Study and Visit Details" />
        <LegacyCustomTemplateFields
          fields={customFieldsAfterAnchor("__template_start__", "legacy_s1")}
          values={customTemplateFields}
          onChange={setCustomTemplateField}
        />
        <div style={grid}>
          <Field label="Study Title" fieldKey="studyTitle">
            <FormInput value={studyTitle} onChange={(e) => setStudyTitle(e.target.value)} />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor(
              "legacy_s1_study_title",
              "legacy_s1_sponsor",
              "legacy_s1_study_type",
              "legacy_s1_pi",
            )}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
          <Field label="Site Name" fieldKey="site">
            <FormInput value={site} onChange={(e) => setSite(e.target.value)} />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor("legacy_s1_site")}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
          <Field label="Start Visit Date" fieldKey="visitStartDate">
            <FormInput
              type="date"
              value={visitStartDate}
              onChange={(e) => setVisitStartDate(e.target.value)}
            />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor("legacy_s1_visit_start_date")}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
          <Field label="End Visit Date" fieldKey="visitEndDate">
            <FormInput
              type="date"
              value={visitEndDate}
              onChange={(e) => setVisitEndDate(e.target.value)}
            />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor("legacy_s1_visit_end_date")}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
          <Field label="Start Date of Previous Visit" fieldKey="prevVisitStartDate">
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <FormInput type="date" disabled={prevVisitNA} value={prevVisitStartDate}
                onChange={(e) => setPrevVisitStartDate(e.target.value)}
                style={{ opacity: prevVisitNA ? .45 : 1 }} />
              <CheckLabel checked={prevVisitNA} onChange={setPrevVisitNA} fieldKey="prevVisitNA">N/A</CheckLabel>
            </div>
          </Field>
          <Field label="End Date of Previous Visit" fieldKey="prevVisitEndDate">
            <FormInput type="date" disabled={prevVisitNA} value={prevVisitEndDate}
              onChange={(e) => setPrevVisitEndDate(e.target.value)}
              style={{ opacity: prevVisitNA ? .45 : 1 }} />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor("legacy_s1_prev_visit_date", "legacy_s1_prev_visit_note")}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
          <Field label="Start Date of Next Visit" fieldKey="nextVisitStartDate">
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <FormInput type="date" disabled={nextVisitTbd} value={nextVisitStartDate}
                onChange={(e) => setNextVisitStartDate(e.target.value)}
                style={{ opacity: nextVisitTbd ? .45 : 1 }} />
              <CheckLabel checked={nextVisitTbd} onChange={setNextVisitTbd} fieldKey="nextVisitTbd">TBD</CheckLabel>
            </div>
          </Field>
          <Field label="End Date of Next Visit" fieldKey="nextVisitEndDate">
            <FormInput type="date" disabled={nextVisitTbd} value={nextVisitEndDate}
              onChange={(e) => setNextVisitEndDate(e.target.value)}
              style={{ opacity: nextVisitTbd ? .45 : 1 }} />
          </Field>
          <LegacyCustomTemplateFields
            fields={customFieldsAfterAnchor("legacy_s1_next_visit_date", "legacy_s1_next_visit_note")}
            values={customTemplateFields}
            onChange={setCustomTemplateField}
          />
        </div>

        <div style={{ marginTop: 18 }}>
          <label style={labelBase}>People Present</label>
          
          <div
            data-mvr-field="sitePersonnelRows"
            data-mvr-field-label="Site Personnel"
            data-mvr-comment-anchor="Site Personnel"
            style={{ marginBottom: 16 }}
          >
            <div style={{ fontSize: 13.5, fontWeight: 600, color: "#374151", marginBottom: 10 }}>Site Personnel</div>
            <DynamicTable
              fieldKey="sitePersonnelRows"
              cols={[{ key: "name", label: "Name" }, { key: "role", label: "Role" }]}
              rows={sitePersonnelRows} onChange={sitePersonnelChange} onAdd={sitePersonnelAdd} onRemove={sitePersonnelRemove}
            />
          </div>

          <div
            data-mvr-field="monitorPersonnelRows"
            data-mvr-field-label="Monitor Personnel"
            data-mvr-comment-anchor="Monitor Personnel"
            style={{ marginBottom: 16 }}
          >
            <div style={{ fontSize: 13.5, fontWeight: 600, color: "#374151", marginBottom: 10 }}>Monitor Personnel</div>
            <DynamicTable
              fieldKey="monitorPersonnelRows"
              cols={[{ key: "name", label: "Name" }, { key: "role", label: "Role" }]}
              rows={monitorPersonnelRows} onChange={monitorPersonnelChange} onAdd={monitorPersonnelAdd} onRemove={monitorPersonnelRemove}
            />
          </div>

          <div
            data-mvr-field="otherPersonnelRows"
            data-mvr-field-label="Other Personnel"
            data-mvr-comment-anchor="Other Personnel"
          >
            <div style={{ fontSize: 13.5, fontWeight: 600, color: "#374151", marginBottom: 10 }}>Other Personnel</div>
            <DynamicTable
              fieldKey="otherPersonnelRows"
              cols={[{ key: "name", label: "Name" }, { key: "role", label: "Role" }]}
              rows={otherPersonnelRows} onChange={otherPersonnelChange} onAdd={otherPersonnelAdd} onRemove={otherPersonnelRemove}
            />
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <Field label="Purpose of This Visit" fieldKey="visitPurpose" full>
            <FormTextarea
              style={{ minHeight: 90 }}
              placeholder="Describe monitoring activities performed (e.g. SDV, review of informed consent process, ISF, resolution of queries, safety, drug accountability)…"
              value={visitPurpose} onChange={(e) => setVisitPurpose(e.target.value)}
            />
          </Field>
        </div>
      </Card>

      {/* ── 2. Recruitment Participant Status ── */}
      <Card>
        <SectionHeader num="2" title="Recruitment Participant Status" />
        <div style={grid}>
          {([
            ["Screened", "ptScreened", ptScreened, setPtScreened],
            ["Enrolled", "ptEnrolled", ptEnrolled, setPtEnrolled],
            ["Active", "ptActive", ptActive, setPtActive],
            ["Drop-outs", "ptDropouts", ptDropouts, setPtDropouts],
            ["Completed Study", "ptCompleted", ptCompleted, setPtCompleted],
          ] as [string, string, string, Dispatch<SetStateAction<string>>][]).map(([label, fieldKey, val, set]) => (
            <Field key={fieldKey} label={`Participants ${label}`} fieldKey={fieldKey}>
              <FormInput type="number" min={0} value={val} onChange={(e) => set(e.target.value)} />
            </Field>
          ))}
        </div>
        <CommentsField fieldKey="s2Comments" value={s2Comments} onChange={setS2Comments} placeholder="E.g. measures to enhance recruitment or limit drop-out…" />
      </Card>

      {/* ── 3. Findings ── */}
      <Card>
        <SectionHeader num="3" title="Findings" />
        {visitFindingsQuery.isLoading ? (
          <p style={{ margin: "4px 0 16px", fontSize: 13, color: "var(--text-muted)" }}>Loading findings…</p>
        ) : (visitFindingsQuery.data ?? []).length === 0 ? (
          <div style={{ marginBottom: 16, padding: "20px 20px", border: "1px solid var(--border)", borderRadius: 12, background: "var(--surface)" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
              No Findings Recorded
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6 }}>
              No monitoring findings were identified during this visit. Compliance and site conduct were reviewed with no issues requiring follow-up.
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
            {(visitFindingsQuery.data ?? []).map((f) => (
              <div
                key={f.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "12px 14px",
                  background: "var(--surface)",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                      <span style={{ fontFamily: "DM Mono,monospace", fontSize: 11.5, color: "var(--text-muted)" }}>
                        {findingIdForDisplay(f.id, visitId)}
                      </span>
                      <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>·</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                        {canonicalFindingCategory(f.category)}
                      </span>
                      {f.subjectId && (
                        <>
                          <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>·</span>
                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Subject {f.subjectId}</span>
                        </>
                      )}
                    </div>
                    <p style={{ margin: 0, fontSize: 13.5, color: "var(--text-primary)", lineHeight: 1.5 }}>
                      {f.description}
                    </p>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, flexShrink: 0 }}>
                    <SeverityBadge severity={f.severity} />
                    <StatusBadge status={f.status} />
                  </div>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                    gap: 12,
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: "1px solid var(--border)",
                  }}
                >
                  <div>
                    <div style={{ fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-muted)", marginBottom: 4 }}>
                      Responsible Person
                    </div>
                    <FindingAssigneesCell finding={f} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-muted)", marginBottom: 4 }}>
                      Due Date
                    </div>
                    <FindingDueDatesCell finding={f} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-muted)", marginBottom: 4 }}>
                      Action
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <FindingCorrectiveActionsCell finding={f} />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        <CommentsField fieldKey="s3Comments" value={s3Comments} onChange={setS3Comments} placeholder="Summarize findings if any…" />
      </Card>

      {/* ── 4. Site Management & General Site Assessment ── */}
      <Card>
        <SectionHeader num="4" title="Site Management & General Site Assessment" />
        {SECTION4_SITE_MANAGEMENT_QUESTIONS.map((q, i) => {
          if (!isSection4SiteManagementQuestionVisible(q, section4SiteValues)) return null;
          return (
            <CheckRow
              key={q.id}
              num={`4.${i + 1}`}
              label={q.label}
              value={section4SiteValues[q.id]}
              onChange={section4SiteSetters[q.id]}
              fieldKey={q.id}
              commentFieldKey={questionCommentKey(q.id)}
              commentValue={getQuestionComment(q.id)}
              onCommentChange={(v) => setQuestionComment(q.id, v)}
            />
          );
        })}
      </Card>

      {/* ── 5. Informed Consent / Enrolment ── */}
      <Card>
        <SectionHeader num="5" title="Participants Informed Consent / Enrolment" na={s5NA} onNaChange={setS5NA} naFieldKey="s5NA" />
        {!s5NA && (
          <>
            {SECTION4_CONSENT_QUESTIONS.map((q, i) => (
              <CheckRow
                key={q.id}
                num={`5.${i + 1}`}
                label={q.label}
                value={section4Values[q.id]}
                onChange={section4Setters[q.id]}
                fieldKey={q.id}
                commentFieldKey={questionCommentKey(q.id)}
                commentValue={getQuestionComment(q.id)}
                onCommentChange={(v) => setQuestionComment(q.id, v)}
              />
            ))}
            <div
              style={{ marginTop: 12 }}
              data-mvr-field="icfRows"
              data-mvr-field-label="ICF Review Table"
              data-mvr-comment-anchor="ICF Review Table"
            >
              <label style={labelBase}>ICF Review Table</label>
              <DynamicTable
                fieldKey="icfRows"
                cols={ICF_REVIEW_TABLE_COLUMNS}
                rows={icfRows} onChange={icfChange} onAdd={icfAdd} onRemove={icfRemove}
              />
            </div>
          </>
        )}
      </Card>

      {/* ── 6. CRF / SDV ── */}
      <Card>
        <SectionHeader num="6" title="Case Report Form (CRF) / Source Data Verification (SDV)" na={s6NA} onNaChange={setS6NA} naFieldKey="s6NA" />
        {!s6NA && (
          <>
            {SECTION6_SDV_QUESTIONS.map((q, i) => (
              <CheckRow
                key={q.id}
                num={`6.${i + 1}`}
                label={q.label}
                value={section6Values[q.id]}
                onChange={section6Setters[q.id]}
                fieldKey={q.id}
                commentFieldKey={questionCommentKey(q.id)}
                commentValue={getQuestionComment(q.id)}
                onCommentChange={(v) => setQuestionComment(q.id, v)}
              />
            ))}
            <div
              style={{ marginTop: 12 }}
              data-mvr-field="sdvRows"
              data-mvr-field-label="SDV Review Table"
              data-mvr-comment-anchor="SDV Review Table"
            >
              <label style={labelBase}>SDV Review Table</label>
              <DynamicTable
                fieldKey="sdvRows"
                cols={SDV_REVIEW_TABLE_COLUMNS}
                rows={sdvRows} onChange={sdvChange} onAdd={sdvAdd} onRemove={sdvRemove}
              />
            </div>
          </>
        )}
      </Card>

      {/* ── 7. Essential Documents ── */}
      <Card>
        <SectionHeader num="7" title="Essential Documents, ISF or TMF" na={s11NA} onNaChange={setS11NA} naFieldKey="s11NA" />
        {!s11NA && (
          <>
            {SECTION10_ESSENTIAL_DOCS_QUESTIONS.map((q, i) => (
              <CheckRow
                key={q.id}
                num={`7.${i + 1}`}
                label={q.label}
                value={section10Values[q.id]}
                onChange={section10Setters[q.id]}
                fieldKey={q.id}
                commentFieldKey={questionCommentKey(q.id)}
                commentValue={getQuestionComment(q.id)}
                onCommentChange={(v) => setQuestionComment(q.id, v)}
              />
            ))}
          </>
        )}
      </Card>

      {/* ── 8. Investigational Medical Product (IMP) ── */}
      <Card>
        <SectionHeader num="8" title="Investigational Medical Product (IMP)" na={s8NA} onNaChange={setS8NA} naFieldKey="s8NA" />
        {!s8NA && (
          <>
            {SECTION10_IMP_QUESTIONS.map((q, i) => (
              <CheckRow
                key={q.id}
                num={`8.${i + 1}`}
                label={q.label}
                value={sectionImpValues[q.id]}
                onChange={sectionImpSetters[q.id]}
                fieldKey={q.id}
                commentFieldKey={questionCommentKey(q.id)}
                commentValue={getQuestionComment(q.id)}
                onCommentChange={(v) => setQuestionComment(q.id, v)}
              />
            ))}
          </>
        )}
      </Card>

      {/* ── 9. Biological Sample / Laboratory Sample Review ── */}
      <Card>
        <SectionHeader num="9" title="Biological Sample / Laboratory Sample Review" na={s9NA} onNaChange={setS9NA} naFieldKey="s9NA" />
        {!s9NA && (
          <>
            {SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS.map((q, i) => (
              <CheckRow
                key={q.id}
                num={`9.${i + 1}`}
                label={q.label}
                value={sectionBioSampleValues[q.id]}
                onChange={sectionBioSampleSetters[q.id]}
                fieldKey={q.id}
                commentFieldKey={questionCommentKey(q.id)}
                commentValue={getQuestionComment(q.id)}
                onCommentChange={(v) => setQuestionComment(q.id, v)}
              />
            ))}
          </>
        )}
      </Card>

      {/* ── 10. Summary ── */}
      <Card>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <SectionHeader num="10" title="Summary of the Visit" />
          <button
            type="button"
            onClick={() => void handleGenerateSummary()}
            disabled={isGeneratingSummary || isFormReadOnly}
            title="Use Gemini AI to auto-generate a visit summary from form data"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 14px",
              background: isGeneratingSummary
                ? "#e9d5ff"
                : "linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: isGeneratingSummary || isFormReadOnly ? "not-allowed" : "pointer",
              boxShadow: isGeneratingSummary ? "none" : "0 3px 10px rgba(124,58,237,0.35)",
              transition: "all 0.2s",
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}
          >
            {isGeneratingSummary ? (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden
                  style={{ animation: "spin 0.8s linear infinite" }}>
                  <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.35)" strokeWidth="3" />
                  <path d="M12 2a10 10 0 0110 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                </svg>
                Generating…
              </>
            ) : (
              <>✨ Auto-Generate Summary</>
            )}
          </button>
        </div>
        <LockedStandaloneTextarea
          fieldKey="summary"
          anchorLabel="Summary of the Visit"
          style={{ minHeight: 160 }}
          placeholder="Conclusions of the monitoring visit and general comments…"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
        />
      </Card>

      {/* ── 11. Signatures ── */}
      <Card>
        <SectionHeader num="11" title="Signatures" />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)",
            gap: 16,
            alignItems: "end",
            marginBottom: 8,
          }}
        >
          <div />
          <label style={{ ...labelBase, marginBottom: 0 }}>Signature</label>
          <label style={{ ...labelBase, marginBottom: 0 }}>Date</label>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)",
            gap: 16,
            alignItems: "end",
            marginBottom: 18,
          }}
        >
          <Field label="Prepared by" fieldKey="preparedByName">
            <FormInput
              placeholder="Name of CRA"
              value={preparedByName}
              onChange={(e) => setPreparedByName(e.target.value)}
            />
          </Field>
          <Field label=" " fieldKey="preparedBySignature">
            <FormInput
              placeholder="Signature"
              value={preparedBySignature}
              onChange={(e) => setPreparedBySignature(e.target.value)}
            />
          </Field>
          <Field label=" " fieldKey="preparedByDate">
            <FormInput
              type="date"
              value={preparedByDate}
              onChange={(e) => setPreparedByDate(e.target.value)}
            />
          </Field>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)",
            gap: 16,
            alignItems: "end",
          }}
        >
          <Field label="Reviewed & Approved by" fieldKey="reviewedByName">
            <FormInput
              placeholder="Name of reviewer"
              value={reviewedByName}
              onChange={(e) => setReviewedByName(e.target.value)}
            />
          </Field>
          <Field label=" " fieldKey="reviewedBySignature">
            <FormInput
              placeholder="Signature"
              value={reviewedBySignature}
              onChange={(e) => setReviewedBySignature(e.target.value)}
            />
          </Field>
          <Field label=" " fieldKey="reviewedByDate">
            <FormInput
              type="date"
              value={reviewedByDate}
              onChange={(e) => setReviewedByDate(e.target.value)}
            />
          </Field>
        </div>
      </Card>

      </div>{/* end reportBodyRef */}

      {/* ── Report Status & Sign-Off ── */}
      <Card style={{ border: `2px solid ${C.primaryMid}`, background: C.primaryLight }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, marginBottom: 2 }}>Report Status &amp; Sign-Off</div>
            <div style={{ fontSize: 12, color: C.textSub }}>
              <LegacyReportStatusMessage
                isVisitClosed={isVisitClosed}
                reportStatus={reportStatus}
                isFormReadOnly={isFormReadOnly}
              />
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            {!isFormReadOnly && reportStatus !== "Rejected" && (
              <div>
                <label style={{ ...labelBase, marginBottom: 4 }}>Status</label>
                <FormSelect
                  value={reportStatus}
                  onChange={(e) => setReportStatus(e.target.value as VisitReportFormState["reportStatus"])}
                  style={{ width: "auto", minWidth: 130 }}
                >
                  <option>Draft</option>
                  <option>Final</option>
                  <option>Submitted</option>
                  <option value="In Review">In Review</option>
                  <option>Approved</option>
                  <option>Rejected</option>
                </FormSelect>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", paddingBottom: 0, flexWrap: "wrap" }}>
              {isVisitClosed ? (
                <div style={{
                  fontSize: 12.5, color: "#92400e", fontWeight: 600,
                  padding: "8px 14px", background: "#fef3c7",
                  borderRadius: 8, border: "1.5px solid #fcd34d",
                }}>
                  🔒 Visit closed — locked for audit compliance
                </div>
              ) : reportStatus === "Rejected" ? (
                // After rejection: allow author to edit & resubmit
                <>
                  <Btn variant="primary" onClick={() => void handleSave()} disabled={saving || loading}>
                    {saving ? "Saving…" : "Save Draft"}
                  </Btn>
                  <Btn
                    variant="secondary"
                    onClick={() => void handleSubmit()}
                    disabled={saving || loading}
                    style={{ fontWeight: 700, color: "#fff", background: C.success, border: `2px solid ${C.success}` }}
                  >
                    Resubmit for Review
                  </Btn>
                </>
              ) : isFormReadOnly ? (
                <div style={{
                  fontSize: 12.5, color: "#4c1d95", fontWeight: 600,
                  padding: "8px 14px", background: "#ede9fe",
                  borderRadius: 8, border: "1.5px solid #c4b5fd",
                }}>
                  🔒 {reportStatus === "Approved" ? "Approved & locked" : "Locked for review"}
                </div>
              ) : (
                <>
                  <Btn variant="primary" onClick={() => void handleSave()} disabled={saving || loading}>
                    {saving ? "Saving…" : "Save"}
                  </Btn>
                  <Btn
                    variant="secondary"
                    onClick={() => void handleSubmit()}
                    disabled={saving || loading}
                    style={{ fontWeight: 700, color: "#fff", background: C.success, border: `2px solid ${C.success}` }}
                  >
                    Submit for Review
                  </Btn>
                </>
              )}
            </div>
          </div>
        </div>
      </Card>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .fade-in { animation: fadeIn .25s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
        ${MVR_COMMENT_FLASH_STYLES}
      `}</style>

      </div>{/* end left column */}

      {/* ── RIGHT SIDEBAR: Reviewer Comments ── */}
      {reviewComments.length > 0 && (
        <MvrReviewerCommentsSidebar
          visitId={visitId}
          comments={reviewComments}
          activeCommentId={activeCommentId}
          onCommentClick={handleCommentCardClick}
          canReply={reportStatus === "Rejected" && !isVisitClosed}
          onCommentsChange={setReviewComments}
          variant="legacy"
        />
      )}

    </div>
    </MvrRestrictedEditProvider>
  );
}

function templateIdFromReportPayload(payload: unknown): string | undefined {
  if (!isRecord(payload)) return undefined;
  const id = payload.templateId;
  return typeof id === "string" && id.trim() ? id.trim() : undefined;
}

export function VisitReportTab(props: {
  visitId: string;
  visitSeq?: number;
  showToast: (msg: string, type?: string) => void;
  onStatusChange?: (status: VisitReportFormState["reportStatus"]) => void;
  authorEmail?: string;
  isVisitClosed?: boolean;
}) {
  const { report, overview, reportLoading } = useVisitWorkflow();
  const [fetchedLiveTemplate, setFetchedLiveTemplate] = useState<MvrTemplateDto | null>(null);
  const [savedTemplate, setSavedTemplate] = useState<MvrTemplateDto | null>(null);
  const [templatesLoading, setTemplatesLoading] = useState(true);

  const savedTemplateId = useMemo(
    () => templateIdFromReportPayload(report?.payload),
    [report?.payload],
  );

  const payloadReportStatus = useMemo(() => {
    if (!isRecord(report?.payload)) return undefined;
    const status = report.payload.reportStatus;
    return typeof status === "string" ? status : undefined;
  }, [report?.payload]);

  const reportTemplateIsFrozen =
    props.isVisitClosed ||
    payloadReportStatus === "In Review" ||
    payloadReportStatus === "Approved" ||
    payloadReportStatus === "Rejected";

  const snapshotEligible =
    props.isVisitClosed ||
    payloadReportStatus === "In Review" ||
    payloadReportStatus === "Approved" ||
    // Rejected reports are revised against the reviewer's inline comments, which
    // anchor to the template the report was submitted with — keep rendering from
    // the frozen snapshot, never fall back to the built-in default form.
    payloadReportStatus === "Rejected";

  const payloadRecord = isRecord(report?.payload) ? report.payload : null;

  const frozenTemplateSnapshot = useMemo(
    () =>
      snapshotEligible && payloadRecord
        ? templateSnapshotFromPayload(payloadRecord, savedTemplateId)
        : null,
    [snapshotEligible, payloadRecord, savedTemplateId],
  );

  const canUseLiveTemplate = !savedTemplateId && !reportTemplateIsFrozen;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setTemplatesLoading(true);
      try {
        const needsLiveFetch = canUseLiveTemplate && !report?.activeTemplate;
        // Locked reports must never use the live org template — fetch by saved id
        // and derive a frozen schema from the report data when no snapshot exists.
        const needsSavedFetch =
          snapshotEligible && !frozenTemplateSnapshot && !!savedTemplateId;

        const [liveRes, savedById] = await Promise.all([
          needsLiveFetch ? fetchActiveMvrTemplate() : Promise.resolve({ template: null }),
          needsSavedFetch
            ? fetchMvrTemplateById(savedTemplateId!)
                .then((r) => r.template)
                .catch(() => null)
            : Promise.resolve(null),
        ]);
        if (cancelled) return;
        if (needsLiveFetch) setFetchedLiveTemplate(liveRes.template);
        if (!canUseLiveTemplate) setFetchedLiveTemplate(null);
        setSavedTemplate(savedById);
      } catch {
        if (!cancelled) {
          setFetchedLiveTemplate(null);
          setSavedTemplate(null);
        }
      } finally {
        if (!cancelled) setTemplatesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [savedTemplateId, report?.activeTemplate, canUseLiveTemplate, frozenTemplateSnapshot, snapshotEligible]);

  const derivedFrozenTemplate = useMemo(() => {
    if (frozenTemplateSnapshot) return frozenTemplateSnapshot;
    if (!snapshotEligible || !savedTemplate || !payloadRecord) return null;
    return deriveFrozenTemplateFromReport(savedTemplate, payloadRecord);
  }, [frozenTemplateSnapshot, snapshotEligible, savedTemplate, payloadRecord]);

  const liveTemplate = canUseLiveTemplate ? (report?.activeTemplate ?? fetchedLiveTemplate) : null;
  const resolvedTemplate = derivedFrozenTemplate ?? (canUseLiveTemplate ? liveTemplate : null);

  if (reportLoading || templatesLoading) {
    return (
      <div className="fade-in" style={{ padding: 24, color: "var(--text-muted)" }}>
        Loading visit report...
      </div>
    );
  }

  if (shouldUseDynamicMvrShell(resolvedTemplate)) {
    return (
      <div className="fade-in">
        <DynamicVisitReportShell
          key={`dyn-${props.visitId}-${resolvedTemplate!.id}`}
          template={resolvedTemplate!}
          {...props}
          initialReport={report}
        />
      </div>
    );
  }

  return (
    <div className="fade-in">
      <VisitReportLegacyTab
        key={`legacy-${props.visitId}-${resolvedTemplate?.id ?? "builtin"}`}
        {...props}
        initialReport={report}
        initialOverview={overview}
        activeTemplate={resolvedTemplate ?? undefined}
      />
    </div>
  );
}
