import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  MVR_COMMENT_FLASH_STYLES,
  scrollToCommentAnchor,
} from "../../../utils/mvrReviewCommentNavigation";
import { useMvrRestrictedRevisionEdit } from "../../../hooks/useMvrRestrictedRevisionEdit";
import { useAuth } from "@/contexts/AuthContext";
import { Trash2 } from "lucide-react";
import { Btn } from "../../ui";
import { MvrReviewerCommentsSidebar } from "./MvrReviewerCommentsSidebar";
import {
  useReportComments,
  useSaveVisitReport,
  useSubmitReportForReview,
  type ReviewComment,
  type VisitReportQueryData,
} from "@/lib/queries/useMonitoring";
import { reportWorkflowSyncKey } from "../../../utils/visitWorkflowPoll";
import type { MvrFieldDef, MvrTemplateDto, MvrSubmissionData } from "../../../types/mvrTemplate";

type ReportStatus = "Draft" | "In Review" | "Approved" | "Rejected";

/** Normalize label text (e.g. remove stray space before `?`). */
function formatFieldLabel(label: string): string {
  return label.replace(/\s+\?/g, "?").trim();
}

const inputBaseClass =
  "w-full bg-white border border-gray-300 rounded-md shadow-sm px-4 py-2 text-sm text-gray-900 placeholder:text-gray-400 " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 disabled:cursor-not-allowed";

const labelClass = "block text-sm font-medium text-gray-700 mb-1";

// Submit-for-Review modal tokens — mirror the legacy tab (VisitReportTab.tsx `C`,
// `labelBase`, `inputBase`) so both template modes share one modal design.
const MODAL_C = {
  primary: "#1a56db",
  primaryLight: "#e8f0fe",
  text: "#111827",
  textSub: "#6b7280",
  border: "#e5e7eb",
  danger: "#dc2626",
} as const;

const modalLabelBase: CSSProperties = {
  display: "block", fontSize: 12, fontWeight: 600, color: MODAL_C.textSub,
  marginBottom: 5, letterSpacing: ".02em", textTransform: "uppercase",
};

const modalInputBase: CSSProperties = {
  width: "100%", padding: "8px 12px", fontSize: 13.5, lineHeight: 1.5,
  color: MODAL_C.text, background: "#f3f4f6", border: `1.5px solid ${MODAL_C.border}`,
  borderRadius: 8, outline: "none", boxSizing: "border-box",
};

const groupLabelClass = "block text-sm font-medium text-gray-700 mb-2";

function emptyTableRow(cols: { id: string }[]): Record<string, string> {
  const r: Record<string, string> = {};
  for (const c of cols) r[c.id] = "";
  return r;
}

export function DynamicVisitReportShell({
  template,
  visitId = "",
  visitSeq,
  showToast,
  onStatusChange,
  authorEmail,
  isVisitClosed = false,
  previewMode = false,
  initialReport,
}: {
  template: MvrTemplateDto;
  visitId?: string;
  visitSeq?: number;
  showToast: (msg: string, type?: string) => void;
  onStatusChange?: (status: ReportStatus) => void;
  authorEmail?: string;
  isVisitClosed?: boolean;
  /** When true, no API calls or persistence — interactive form only (e.g. template builder preview). */
  previewMode?: boolean;
  /** Pre-loaded report from VisitWorkflowContext — avoids duplicate GET on tab open. */
  initialReport?: VisitReportQueryData | null;
}) {
  const { user } = useAuth();
  const resolvedAuthorEmail = authorEmail ?? user?.email ?? "";
  const visitHeaderLabel = previewMode ? "Preview" : visitSeq != null ? `#${visitSeq}` : visitId;
  const syncToastShown = useRef(false);

  const [loading, setLoading] = useState(!previewMode);
  const [saving, setSaving] = useState(false);
  const [rawPayload, setRawPayload] = useState<Record<string, unknown>>({});
  const [submissionData, setSubmissionData] = useState<MvrSubmissionData>({});
  const [reportStatus, setReportStatus] = useState<ReportStatus>("Draft");
  const [rejectionReason, setRejectionReason] = useState("");

  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewerEmail, setReviewerEmail] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reviewComments, setReviewComments] = useState<ReviewComment[]>([]);
  const [activeCommentId, setActiveCommentId] = useState<string | null>(null);
  const reportBodyRef = useRef<HTMLDivElement>(null);

  /** Read-only while in review, approved, or visit closed — rejected reports stay editable for revision. */
  const isLocked =
    previewMode
      ? false
      : reportStatus === "In Review" || reportStatus === "Approved" || isVisitClosed;

  const templateFields = useMemo(() => template.schema?.fields ?? [], [template.schema?.fields]);

  const { restrictedRevision, fieldDisabled } = useMvrRestrictedRevisionEdit({
    reportStatus,
    reviewComments,
    reportBodyRef,
    baseLocked: isLocked,
    templateFields,
    contentReady: !loading,
  });

  useEffect(() => {
    if (previewMode) return;
    onStatusChange?.(reportStatus);
  }, [previewMode, reportStatus, onStatusChange]);

  const shouldLoadComments =
    !previewMode &&
    (reportStatus === "In Review" ||
      reportStatus === "Approved" ||
      reportStatus === "Rejected" ||
      isVisitClosed ||
      String(initialReport?.payload?.reportStatus ?? "") === "In Review" ||
      String(initialReport?.payload?.reportStatus ?? "") === "Approved" ||
      String(initialReport?.payload?.reportStatus ?? "") === "Rejected");
  const reportCommentsQuery = useReportComments(visitId, shouldLoadComments);
  const saveReportMutation = useSaveVisitReport(visitId);
  const submitForReviewMutation = useSubmitReportForReview(visitId);

  useEffect(() => {
    if (!shouldLoadComments) {
      setReviewComments([]);
      setActiveCommentId(null);
      return;
    }
    setReviewComments(reportCommentsQuery.data ?? []);
  }, [shouldLoadComments, reportCommentsQuery.data]);

  const handleCommentCardClick = useCallback((comment: ReviewComment) => {
    setActiveCommentId(comment.id);
    const anchor = scrollToCommentAnchor(reportBodyRef.current, comment);
    if (!anchor) {
      showToast("Could not locate this text in the report. Try searching for the quoted snippet.", "info");
    }
  }, [showToast]);

  const applyReportResponse = useCallback((res: VisitReportQueryData) => {
    const pl = (res.payload || {}) as Record<string, unknown>;
    setRawPayload(pl);
    setReportStatus((pl.reportStatus as ReportStatus) || "Draft");
    setRejectionReason(typeof pl.rejectionReason === "string" ? pl.rejectionReason : "");
    const sd = pl.submissionData;
    setSubmissionData(typeof sd === "object" && sd !== null && !Array.isArray(sd) ? { ...(sd as MvrSubmissionData) } : {});

    if (res.templateSynced && !syncToastShown.current) {
      syncToastShown.current = true;
      showToast(
        "ℹ️ The MVR template was recently updated by your organization. Your draft has been automatically refreshed to match the latest requirements.",
        "success",
      );
    }
  }, [showToast]);

  const load = useCallback(async () => {
    if (previewMode) return;
    setLoading(true);
    try {
      if (initialReport) {
        applyReportResponse(initialReport);
        return;
      }
      showToast("Could not load visit report", "error");
    } catch {
      showToast("Could not load visit report", "error");
    } finally {
      setLoading(false);
    }
  }, [visitId, showToast, previewMode, initialReport, applyReportResponse]);

  const didLoadReportRef = useRef(false);
  useEffect(() => {
    didLoadReportRef.current = false;
  }, [visitId]);

  useEffect(() => {
    if (previewMode) return;
    if (!initialReport) {
      if (!didLoadReportRef.current) void load();
      return;
    }
    if (didLoadReportRef.current) return;
    didLoadReportRef.current = true;
    applyReportResponse(initialReport);
    setLoading(false);
  }, [load, previewMode, initialReport, applyReportResponse, visitId]);

  const reportSyncKey = reportWorkflowSyncKey(initialReport);
  useEffect(() => {
    if (previewMode || !initialReport) return;
    const pl = (initialReport.payload || {}) as Record<string, unknown>;
    const nextStatus = (pl.reportStatus as ReportStatus) || "Draft";
    setReportStatus(nextStatus);
    setRejectionReason(typeof pl.rejectionReason === "string" ? pl.rejectionReason : "");
  }, [previewMode, initialReport, reportSyncKey]);

  const setField = (id: string, value: unknown) => {
    if (fieldDisabled(id)) return;
    setSubmissionData((prev) => ({ ...prev, [id]: value }));
  };

  const buildFullPayload = useCallback((): Record<string, unknown> => {
    return {
      ...rawPayload,
      schemaVersion: (rawPayload.schemaVersion as number) || 1,
      reportStatus,
      templateId: template.id,
      templateVersion: template.version,
      // Freeze the exact template used for this report. Once a report is locked
      // (In Review / Approved / Rejected), it renders from this snapshot so later
      // edits to the live template (adding fields, etc.) never mutate it.
      templateSnapshot: {
        id: template.id,
        name: template.name,
        version: template.version,
        schema: template.schema ?? { fields: [] },
      },
      submissionData,
    };
  }, [rawPayload, reportStatus, template.id, template.version, template.name, template.schema, submissionData]);

  const handleSave = async () => {
    if (previewMode || saving || loading || isLocked) return;
    setSaving(true);
    try {
      await saveReportMutation.mutateAsync(buildFullPayload());
      showToast("Visit report saved", "success");
    } catch {
      showToast("Failed to save visit report", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmSubmit = async () => {
    if (previewMode) return;
    if (!reviewerEmail.trim()) {
      showToast("Reviewer email is required", "error");
      return;
    }
    setSubmitting(true);
    try {
      await saveReportMutation.mutateAsync(buildFullPayload());
      await submitForReviewMutation.mutateAsync({
        reviewerEmail: reviewerEmail.trim(),
        message: reviewMessage.trim(),
        authorEmail: resolvedAuthorEmail,
      });
      setReportStatus("In Review");
      setShowReviewModal(false);
      setReviewerEmail("");
      setReviewMessage("");
      showToast("Report submitted for review — email sent to reviewer", "success");
    } catch {
      showToast("Failed to submit for review", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const getFieldWrapperClass = (f: MvrFieldDef) => {
    if (
      f.type === "section" ||
      f.type === "textarea" ||
      f.type === "table" ||
      f.type === "radio" ||
      f.type === "multiselect"
    ) {
      return "md:col-span-2";
    }
    return "";
  };

  const renderField = (f: MvrFieldDef) => {
    const key = f.id;
    const inputId = `mvr-field-${key}`;
    const wrapperClass = getFieldWrapperClass(f);
    const locked = fieldDisabled(key);
    const fieldLabel = formatFieldLabel(f.label);
    const mvrFieldProps = {
      "data-mvr-field": key,
      "data-mvr-field-label": fieldLabel,
      "data-mvr-comment-anchor": fieldLabel,
    } as const;

    if (f.type === "section") {
      return (
        <div key={key} data-mvr-field={key} className={`pb-6 border-b border-gray-200 ${wrapperClass}`}>
          <h3 className="text-base font-semibold text-gray-900 mb-2">{formatFieldLabel(f.label)}</h3>
          {f.content && (
            <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{f.content}</div>
          )}
        </div>
      );
    }

    const commonLabel = (
      <label
        htmlFor={inputId}
        className={labelClass}
        data-mvr-field-label={fieldLabel}
        data-mvr-comment-anchor={fieldLabel}
      >
        {formatFieldLabel(f.label)}
        {f.required ? (
          <span className="text-red-500 ml-1" aria-hidden>
            *
          </span>
        ) : null}
      </label>
    );

    const val = submissionData[key];

    if (f.type === "text") {
      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          {commonLabel}
          <input
            id={inputId}
            type="text"
            value={typeof val === "string" ? val : ""}
            onChange={(e) => setField(key, e.target.value)}
            disabled={locked}
            placeholder={f.placeholder || ""}
            className={inputBaseClass}
          />
        </div>
      );
    }

    if (f.type === "textarea") {
      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          {commonLabel}
          <textarea
            id={inputId}
            value={typeof val === "string" ? val : ""}
            onChange={(e) => setField(key, e.target.value)}
            disabled={locked}
            placeholder={f.placeholder || ""}
            rows={5}
            className={`${inputBaseClass} resize-y min-h-[120px]`}
          />
        </div>
      );
    }

    if (f.type === "number") {
      const sval =
        typeof val === "number" && Number.isFinite(val)
          ? String(val)
          : typeof val === "string"
            ? val
            : "";
      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          {commonLabel}
          <input
            id={inputId}
            type="number"
            inputMode="decimal"
            value={sval}
            onChange={(e) => setField(key, e.target.value)}
            disabled={locked}
            placeholder={f.placeholder || ""}
            className={inputBaseClass}
          />
        </div>
      );
    }

    if (f.type === "date") {
      const sval = typeof val === "string" ? val : "";
      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          {commonLabel}
          <input
            id={inputId}
            type="date"
            value={sval}
            onChange={(e) => setField(key, e.target.value)}
            disabled={locked}
            className={inputBaseClass}
          />
        </div>
      );
    }

    if (f.type === "checkbox") {
      const checked = val === true || val === "true";
      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          <label
            htmlFor={inputId}
            className={`flex items-start gap-3 ${locked ? "cursor-default opacity-70" : "cursor-pointer"}`}
          >
            <input
              id={inputId}
              type="checkbox"
              checked={checked}
              disabled={locked}
              onChange={(e) => setField(key, e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-900 leading-snug">
              {formatFieldLabel(f.label)}
              {f.required ? (
                <span className="text-red-500 ml-1" aria-hidden>
                  *
                </span>
              ) : null}
            </span>
          </label>
        </div>
      );
    }

    if (f.type === "radio" || f.type === "select" || f.type === "multiselect") {
      const rawOpts = Array.isArray(f.options)
        ? f.options.filter((o) => typeof o === "string" && o.trim() !== "")
        : [];
      const opts = rawOpts.length > 0 ? rawOpts : ["Yes", "No", "N/A"];
      const cur = typeof val === "string" ? val : "";
      if (f.type === "radio") {
        return (
          <div key={key} {...mvrFieldProps} className={wrapperClass}>
            <span
            className={groupLabelClass}
            data-mvr-field-label={fieldLabel}
            data-mvr-comment-anchor={fieldLabel}
          >
              {formatFieldLabel(f.label)}
              {f.required ? (
                <span className="text-red-500 ml-1" aria-hidden>
                  *
                </span>
              ) : null}
            </span>
            <div className="flex flex-wrap gap-4 mt-1">
              {opts.map((o) => (
                <label
                  key={o}
                  className={`flex items-center gap-2 cursor-pointer text-sm text-gray-900 ${locked ? "cursor-default opacity-70" : ""}`}
                >
                  <input
                    type="radio"
                    name={key}
                    id={`${inputId}-${o}`}
                    checked={cur === o}
                    disabled={locked}
                    onChange={() => setField(key, o)}
                    className="h-4 w-4 shrink-0 text-blue-600 focus:ring-blue-500 border-gray-300"
                  />
                  <span>{o}</span>
                </label>
              ))}
            </div>
          </div>
        );
      }

      if (f.type === "multiselect") {
        const rawArr = Array.isArray(val) ? val : [];
        const selected = rawArr.filter((x): x is string => typeof x === "string");
        const toggle = (o: string) => {
          const next = selected.includes(o) ? selected.filter((x) => x !== o) : [...selected, o];
          setField(key, next);
        };
        return (
          <div key={key} {...mvrFieldProps} className={wrapperClass}>
            <span
            className={groupLabelClass}
            data-mvr-field-label={fieldLabel}
            data-mvr-comment-anchor={fieldLabel}
          >
              {formatFieldLabel(f.label)}
              {f.required ? (
                <span className="text-red-500 ml-1" aria-hidden>
                  *
                </span>
              ) : null}
            </span>
            <div className="flex flex-wrap gap-4 mt-1">
              {opts.map((o) => (
                <label
                  key={o}
                  className={`flex items-center gap-2 text-sm text-gray-900 ${locked ? "cursor-default opacity-70" : "cursor-pointer"}`}
                >
                  <input
                    type="checkbox"
                    id={`${inputId}-${o}`}
                    checked={selected.includes(o)}
                    disabled={locked}
                    onChange={() => toggle(o)}
                    className="h-4 w-4 shrink-0 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>{o}</span>
                </label>
              ))}
            </div>
          </div>
        );
      }

      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          {commonLabel}
          <select
            id={inputId}
            value={cur}
            onChange={(e) => setField(key, e.target.value)}
            disabled={locked}
            className={inputBaseClass}
          >
            <option value="">Choose…</option>
            {opts.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </div>
      );
    }

    if (f.type === "table") {
      const cols = f.columns?.length ? f.columns : [{ id: "col_a", label: "Column A" }];
      let rows: Record<string, string>[] = Array.isArray(val) ? (val as Record<string, string>[]) : [];
      if (!rows.length) rows = [emptyTableRow(cols)];

      const patchRows = (next: Record<string, string>[]) => setField(key, next);

      return (
        <div key={key} {...mvrFieldProps} className={wrapperClass}>
          <span
            className={groupLabelClass}
            data-mvr-field-label={fieldLabel}
            data-mvr-comment-anchor={fieldLabel}
          >
            {formatFieldLabel(f.label)}
            {f.required ? (
              <span className="text-red-500 ml-1" aria-hidden>
                *
              </span>
            ) : null}
          </span>
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr>
                  {cols.map((c) => (
                    <th
                      key={c.id}
                      data-mvr-field-label={formatFieldLabel(c.label)}
                      className="bg-gray-50 px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider border-b border-gray-200"
                    >
                      {formatFieldLabel(c.label)}
                    </th>
                  ))}
                  {!locked && (
                    <th
                      className="bg-gray-50 w-14 px-2 py-2 border-b border-gray-200"
                      aria-label="Row actions"
                    />
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri} className="border-b border-gray-100 last:border-b-0">
                    {cols.map((c) => (
                      <td key={c.id} className="px-4 py-2 align-middle">
                        <input
                          type="text"
                          value={row[c.id] ?? ""}
                          disabled={locked}
                          onChange={(e) => {
                            const next = rows.map((r, i) => (i === ri ? { ...r, [c.id]: e.target.value } : r));
                            patchRows(next);
                          }}
                          className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
                        />
                      </td>
                    ))}
                    {!locked && (
                      <td className="px-2 py-2 align-middle text-center">
                        <button
                          type="button"
                          title="Remove row"
                          aria-label="Remove row"
                          onClick={() => patchRows(rows.filter((_, i) => i !== ri))}
                          disabled={rows.length <= 1}
                          className="inline-flex p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-gray-400"
                        >
                          <Trash2 className="h-4 w-4" strokeWidth={2} />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {!locked && (
              <div className="border-t border-gray-100 px-4 py-3 bg-gray-50/50">
                <button
                  type="button"
                  onClick={() => patchRows([...rows, emptyTableRow(cols)])}
                  className="mt-0 flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 px-3 py-2 rounded-md transition-colors"
                >
                  + Add row
                </button>
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div
        key={key}
        className={`rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 ${wrapperClass}`}
      >
        This field (“{f.label || key}”) is incomplete or uses an unsupported type. Finish it in the builder.
      </div>
    );
  };

  if (loading) {
    return (
      <div className="fade-in max-w-4xl mx-auto w-full p-6 text-gray-500 text-sm">
        Loading visit report…
      </div>
    );
  }

  const showCommentsSidebar = !previewMode && reviewComments.length > 0;

  return (
    <div
      className={`fade-in w-full p-6 ${
        showCommentsSidebar ? "max-w-[min(100%,90rem)] mx-auto" : "max-w-4xl mx-auto"
      }`}
    >
      {previewMode && (
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          <strong>Preview mode</strong> — this is how the form will look to CRAs. Nothing you enter here is saved.
        </div>
      )}
      {/* Same look and copy as the built-in (legacy) report's Submit for Review modal. */}
      {!previewMode && showReviewModal && (
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
                <div style={{ fontSize: 17, fontWeight: 800, color: MODAL_C.text }}>Submit for Review</div>
                <div style={{ fontSize: 12.5, color: MODAL_C.textSub, marginTop: 2 }}>The reviewer will receive a secure email link to open and annotate this report.</div>
              </div>
              <button type="button" onClick={() => setShowReviewModal(false)}
                style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: MODAL_C.textSub, lineHeight: 1 }}>×</button>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label htmlFor="mvr-reviewer-email" style={modalLabelBase}>Reviewer Email <span style={{ color: MODAL_C.danger }}>*</span></label>
              <input
                id="mvr-reviewer-email"
                type="email" placeholder="reviewer@organization.com"
                value={reviewerEmail} onChange={(e) => setReviewerEmail(e.target.value)}
                style={{ ...modalInputBase }}
                onFocus={(e) => { e.currentTarget.style.borderColor = MODAL_C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${MODAL_C.primaryLight}`; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = MODAL_C.border; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label htmlFor="mvr-review-message" style={modalLabelBase}>Message (optional)</label>
              <textarea
                id="mvr-review-message"
                placeholder="Add a note to the reviewer…"
                value={reviewMessage} onChange={(e) => setReviewMessage(e.target.value)}
                style={{ ...modalInputBase, resize: "vertical", minHeight: 80 }}
                onFocus={(e) => { e.currentTarget.style.borderColor = MODAL_C.primary; e.currentTarget.style.boxShadow = `0 0 0 3px ${MODAL_C.primaryLight}`; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = MODAL_C.border; e.currentTarget.style.boxShadow = "none"; }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <Btn variant="secondary" onClick={() => setShowReviewModal(false)} disabled={submitting}>Cancel</Btn>
              <Btn variant="primary" onClick={() => void handleConfirmSubmit()} disabled={submitting || !reviewerEmail.trim()}>
                {submitting ? "Sending…" : "Send to Reviewer"}
              </Btn>
            </div>
          </div>
        </div>
      )}

      <div
        className={
          showCommentsSidebar
            ? "flex flex-col lg:flex-row lg:items-start gap-6 lg:gap-0"
            : ""
        }
      >
        <div className={showCommentsSidebar ? "flex-1 min-w-0 lg:pr-8" : ""} ref={reportBodyRef}>
          {!previewMode && reportStatus === "Rejected" && (
            <div className="mb-3.5 flex items-start gap-3 rounded-xl border-[1.5px] border-[#fecaca] bg-[#fef2f2] px-[18px] py-[14px]">
              <span className="text-lg shrink-0" aria-hidden>⚠️</span>
              <div>
                <div className="text-[13.5px] font-bold text-[#dc2626] mb-1">
                  Report Rejected — Revision Required
                </div>
                {rejectionReason && (
                  <div className="text-[13px] text-gray-700">
                    <strong>Reason:</strong> {rejectionReason}
                  </div>
                )}
                {reviewComments.length > 0 && (
                  <div className="text-xs text-gray-500 mt-1">
                    {reviewComments.length} inline comment{reviewComments.length !== 1 ? "s" : ""} from the reviewer — click a comment on the right to jump to its location.
                    {restrictedRevision && (
                      <div className="text-xs text-[#92400e] mt-1.5">
                        Only fields with reviewer comments are editable. Other fields are read-only until you resubmit.
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex items-start justify-between gap-3 flex-wrap mb-6 rounded-xl p-6 text-white shadow-md bg-gradient-to-br from-[#1a56db] to-[#1e40af]">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-white/70 mb-1">
                Monitoring Visit Report (MVR)
              </div>
              <h2 className="text-[22px] font-extrabold tracking-tight m-0 leading-tight text-white">
                {previewMode ? "Template preview" : `Visit ${visitHeaderLabel}`}
              </h2>
              <p className="mt-2 text-sm text-white/80 m-0">
                {previewMode
                  ? `“${template.name}” · unsaved draft (preview)`
                  : `Template "${template.name}" v${template.version}`}
              </p>
            </div>
            {!previewMode && (
              <span
                className={`inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide px-3 py-1 rounded-full shrink-0 ${
                  reportStatus === "Draft"
                    ? "bg-amber-100 text-amber-900"
                    : reportStatus === "Approved"
                      ? "bg-green-100 text-green-900"
                      : reportStatus === "Rejected"
                        ? "bg-red-100 text-red-900"
                        : "bg-violet-100 text-violet-900"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    reportStatus === "Draft"
                      ? "bg-amber-500"
                      : reportStatus === "Approved"
                        ? "bg-green-600"
                        : reportStatus === "Rejected"
                          ? "bg-red-600"
                          : "bg-violet-600"
                  }`}
                />
                {reportStatus}
              </span>
            )}
            {previewMode && (
              <span className="inline-flex items-center text-[11px] font-bold uppercase tracking-wide px-3 py-1 rounded-full bg-white/20 text-white border border-white/30 shrink-0">
                Preview
              </span>
            )}
          </div>

          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 md:p-8 mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {(template.schema?.fields || []).map((f) => renderField(f))}
            </div>
            {!isLocked && !previewMode && (
              <div className="mt-8 pt-6 border-t border-gray-100 flex flex-wrap justify-end gap-3">
                <Btn variant="primary" size="sm" onClick={() => void handleSave()} disabled={saving}>
                  {saving ? "Saving…" : "Save draft"}
                </Btn>
                <Btn variant="success" size="sm" onClick={() => setShowReviewModal(true)}>
                  {reportStatus === "Rejected" ? "Resubmit for review" : "Submit for review"}
                </Btn>
              </div>
            )}
            {isLocked && !previewMode && (
              <div className="mt-8 pt-6 border-t border-gray-100">
                <p className="text-sm text-gray-500">This report is locked and cannot be edited.</p>
              </div>
            )}
          </div>
        </div>

        {showCommentsSidebar && (
          <MvrReviewerCommentsSidebar
            visitId={visitId}
            comments={reviewComments}
            activeCommentId={activeCommentId}
            onCommentClick={handleCommentCardClick}
            canReply={reportStatus === "Rejected" && !previewMode && !isVisitClosed}
            onCommentsChange={setReviewComments}
            variant="modern"
          />
        )}
      </div>
      <style>{MVR_COMMENT_FLASH_STYLES}</style>
    </div>
  );
}
