import { useState, useEffect, useMemo, useRef } from "react";
import { Modal } from "../ui/Modal";
import { Btn } from "../ui";
import type { Visit, Finding } from "../../types";
import { canonicalFindingCategory, FINDING_CATEGORIES } from "../../constants/findingCategories";
import { getFindingActionItems } from "../../utils/findingActionItems";
import type { StudyTeamAssigneeOption } from "../../utils/studyTeamAssignees";

type ActionItemFormRow = {
  // The action item's own backend row id, present only for items that
  // already existed (came from an already-saved finding). Newly added rows
  // leave this unset so the backend treats them as new and creates a Task.
  id?: string;
  assignee: string;
  due: string;
  closedDate: string;
  resolution: string;
  taskMode: string;
};

export type FindingFormValues = {
  category: string;
  otherCategory: string;
  severity: string;
  finding: string;
  subjectId: string;
  reference: string;
  actionItems: ActionItemFormRow[];
};

function visitTypeToFormValue(t: string): string {
  const s = (t || "").trim();
  const opts = [
    "Site Initiation Visit",
    "Site Qualification Visit",
    "On-Site Monitoring Visit",
    "Remote Monitoring Visit",
    "Ad-Hoc Monitoring Visit",
    "Close-Out Visit",
  ];
  if (opts.includes(s)) return s;
  if (s === "Initiation Visit") return "Site Initiation Visit";
  if (s.startsWith("On-Site")) return "On-Site Monitoring Visit";
  if (s.startsWith("Remote")) return "Remote Monitoring Visit";
  if (/^initiation/i.test(s)) return "Site Initiation Visit";
  if (/site\s*qualification|^sqv$/i.test(s)) return "Site Qualification Visit";
  if (/^routine/i.test(s)) return "On-Site Monitoring Visit";
  if (s.startsWith("Centralized")) return "Remote Monitoring Visit";
  if (/for[-\s]?cause|ad[-\s]?hoc/i.test(s)) return "Ad-Hoc Monitoring Visit";
  if (/close[-\s]?out/i.test(s)) return "Close-Out Visit";
  return "On-Site Monitoring Visit";
}

function dateIsoFromVisit(v: Visit): string {
  return dateFromIso(v.dateIso);
}

function dateFromIso(iso: string | undefined | null): string {
  if (iso) {
    const m = String(iso).match(/^(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  return "";
}

function todayInputDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** HH:MM (24h) for <input type="time" />, from stored visit_date_iso */
function timeFromVisitIso(iso: string | undefined | null): string {
  if (!iso) return "08:00";
  const m = String(iso).match(/T(\d{2}):(\d{2})/);
  if (m) return `${m[1]}:${m[2]}`;
  return "08:00";
}

function dueDateToInput(dueDate: string): string {
  if (!dueDate || dueDate === "TBD") return "";
  const trimmed = dueDate.trim();
  const withYear = /^\w{3} \d{1,2}$/.test(trimmed)
    ? `${trimmed}, ${new Date().getFullYear()}`
    : dueDate;
  const parsed = new Date(withYear);
  if (Number.isNaN(parsed.getTime())) return "";
  const y = parsed.getFullYear();
  const mo = String(parsed.getMonth() + 1).padStart(2, "0");
  const da = String(parsed.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

/** Parse YYYY-MM-DD to UTC midnight timestamp (date-only, no TZ ambiguity). */
function utcMsFromYmd(ymd: string): number | null {
  const m = String(ymd).trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (!y || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  const t = Date.UTC(y, mo - 1, d);
  return Number.isNaN(t) ? null : t;
}

/** Inclusive calendar days from visit start date through visit end date (both YYYY-MM-DD). */
function computeInclusiveVisitDays(startDate: string, endDate: string): string {
  const t0 = utcMsFromYmd(startDate);
  const t1 = utcMsFromYmd(endDate);
  if (t0 == null || t1 == null) return "";
  const diffDays = Math.round((t1 - t0) / 86_400_000);
  if (diffDays < 0) return "";
  return String(diffDays + 1);
}

export function CreateVisitModal({ open, onClose, onSubmit, sites, studies, cras, craOptionsLoading, initialVisit, lockedSite, lockedStudy }: {
  open: boolean;
  onClose: () => void;
  onSubmit: (form: any) => void | Promise<void>;
  sites?: string[];
  studies?: string[];
  /** When set (including `[]`), replaces static CRA list — use IAM study team from parent. */
  cras?: string[];
  /** True while study team names are loading (first fetch for current study). */
  craOptionsLoading?: boolean;
  /** When set, modal is in edit mode (title, status, save label). */
  initialVisit?: Visit | null;
  /** If provided, site/study are fixed from top navbar selection. */
  lockedSite?: string;
  lockedStudy?: string;
}) {
  const siteList = sites ?? [];
  const studyList = studies ?? [];
  const craList = cras ?? [];
  const craLoading = Boolean(craOptionsLoading);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [dateError, setDateError] = useState("");
  const minVisitDate = useMemo(() => todayInputDate(), []);
  const [form, setForm] = useState({
    site: "", study: "",
    type: "On-Site Monitoring Visit",
    startDate: "", endDate: "",
    startTime: "08:00", endTime: "17:00",
    cra: "",
    status: "Scheduled",
  });

  const estimatedDurationDays = useMemo(
    () => computeInclusiveVisitDays(form.startDate, form.endDate),
    [form.startDate, form.endDate],
  );

  useEffect(() => {
    if (!open) return;
    setDateError("");
    if (initialVisit) {
      const craName = initialVisit.cra.name;
      const visitStartDate = dateIsoFromVisit(initialVisit);
      const visitStartTime = timeFromVisitIso(initialVisit.dateIso);
      const visitEndDate = dateFromIso(initialVisit.endDateIso);
      const visitEndTime = initialVisit.endDateIso ? timeFromVisitIso(initialVisit.endDateIso) : visitStartTime;
      setForm({
        site: lockedSite || initialVisit.site,
        study: lockedStudy || initialVisit.study,
        type: visitTypeToFormValue(initialVisit.type),
        startDate: visitStartDate,
        endDate: visitEndDate || visitStartDate,
        startTime: visitStartTime,
        endTime: visitEndTime,
        cra: craList.includes(craName) ? craName : (craList[0] ?? craName),
        status: initialVisit.status ?? "Scheduled",
      });
      return;
    }
    setForm({
      site: lockedSite || siteList[0] || "",
      study: lockedStudy || studyList[0] || "",
      type: "On-Site Monitoring Visit",
      startDate: "",
      endDate: "",
      startTime: "08:00",
      endTime: "17:00",
      cra: craList[0] ?? "",
      status: "Scheduled",
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialVisit?.id, siteList.join(","), studyList.join(","), craList.join(","), lockedSite, lockedStudy]);

  useEffect(() => {
    if (!open) {
      submittingRef.current = false;
      setSubmitting(false);
      setDateError("");
    }
  }, [open]);

  const set = (k: string, v: string) => setForm(p => ({ ...p, [k]: v }));
  const isEdit = !!initialVisit;
  const cannotSubmitCra = !isEdit && (craLoading || craList.length === 0);
  const originalStartDate = initialVisit ? dateIsoFromVisit(initialVisit) : "";
  const originalEndDate = initialVisit ? (dateFromIso(initialVisit.endDateIso) || originalStartDate) : "";
  const validateVisitDates = () => {
    if (form.startDate && form.startDate < minVisitDate && (!isEdit || form.startDate !== originalStartDate)) {
      return "Visit start date cannot be in the past.";
    }
    if (form.endDate && form.endDate < minVisitDate && (!isEdit || form.endDate !== originalEndDate)) {
      return "Visit end date cannot be in the past.";
    }
    if (form.startDate && form.endDate && form.endDate < form.startDate) {
      return "Visit end date cannot be before the start date.";
    }
    return "";
  };
  const handleStartDateChange = (value: string) => {
    if (value && value < minVisitDate) {
      setDateError("Visit start date cannot be in the past.");
      return;
    }
    setDateError("");
    setForm((prev) => ({
      ...prev,
      startDate: value,
      endDate: prev.endDate && value && prev.endDate < value ? value : prev.endDate,
    }));
  };
  const handleEndDateChange = (value: string) => {
    const minEndDate = form.startDate && form.startDate > minVisitDate ? form.startDate : minVisitDate;
    if (value && value < minVisitDate) {
      setDateError("Visit end date cannot be in the past.");
      return;
    }
    if (value && value < minEndDate) {
      setDateError("Visit end date cannot be before the start date.");
      return;
    }
    setDateError("");
    set("endDate", value);
  };
  const handleClose = () => {
    if (submittingRef.current) return;
    onClose();
  };
  const handleSubmit = async () => {
    if (submittingRef.current || cannotSubmitCra) return;
    const nextDateError = validateVisitDates();
    if (nextDateError) {
      setDateError(nextDateError);
      return;
    }
    setDateError("");
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await onSubmit(submitPayload());
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };
  const submitPayload = () => {
    const payload = {
      site: form.site,
      study: form.study,
      type: form.type,
      priority: initialVisit?.priority ?? "Medium",
      date: form.startDate,
      time: form.startTime,
      end_date: form.endDate,
      end_time: form.endTime,
      cra: form.cra,
      estimated_duration_days: estimatedDurationDays,
    };
    return isEdit ? { ...payload, status: form.status } : payload;
  };
  return (
    <Modal open={open} title={isEdit ? "Edit Visit" : "Create New Visit"} onClose={handleClose}
      footer={<><Btn variant="secondary" onClick={handleClose} disabled={submitting}>Cancel</Btn><Btn variant="primary" disabled={cannotSubmitCra || submitting} onClick={() => void handleSubmit()}>{submitting ? (isEdit ? "Saving…" : "Creating…") : (isEdit ? "Save changes" : "Create Visit")}</Btn></>}>
      <div className="form-grid">
        {!lockedSite && (
          <div className="form-group"><label className="form-label">Site</label>
            <select className="form-select" value={form.site} onChange={e => set("site", e.target.value)}>
              {siteList.map(s => <option key={s} value={s}>{s}</option>)}
            </select></div>
        )}
        {!lockedStudy && (
          <div className="form-group"><label className="form-label">Study</label>
            <select className="form-select" value={form.study} onChange={e => set("study", e.target.value)}>
              {studyList.map(s => <option key={s} value={s}>{s}</option>)}
            </select></div>
        )}
        <div className="form-group"><label className="form-label">Visit type</label>
          <select className="form-select" value={form.type} onChange={e => set("type", e.target.value)}>
            <option value="Site Initiation Visit">Site Initiation Visit</option>
            <option value="Site Qualification Visit">Site Qualification Visit</option>
            <option value="On-Site Monitoring Visit">On-Site Monitoring Visit</option>
            <option value="Remote Monitoring Visit">Remote Monitoring Visit</option>
            <option value="Ad-Hoc Monitoring Visit">Ad-Hoc Monitoring Visit</option>
            <option value="Close-Out Visit">Close-Out Visit</option>
          </select></div>
        <div className="form-group"><label className="form-label">Assign CRA</label>
          <select
            className="form-select"
            value={form.cra}
            onChange={e => set("cra", e.target.value)}
            disabled={craLoading || craList.length === 0}
            title={craLoading ? "Loading study team from IAM" : craList.length === 0 ? "No active study team members for this study" : undefined}
          >
            {craLoading ? (
              <option value="" disabled>Loading study team…</option>
            ) : craList.length === 0 ? (
              <option value="" disabled>No study team members</option>
            ) : (
              craList.map(c => <option key={c} value={c}>{c}</option>)
            )}
          </select></div>
        <div style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 20 }}>
          <div className="form-group"><label className="form-label">Visit start date</label>
            <input className="form-input" type="date" value={form.startDate} min={minVisitDate} aria-invalid={Boolean(dateError)} onChange={e => handleStartDateChange(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Visit end date</label>
            <input className="form-input" type="date" value={form.endDate} min={form.startDate && form.startDate > minVisitDate ? form.startDate : minVisitDate} aria-invalid={Boolean(dateError)} onChange={e => handleEndDateChange(e.target.value)} /></div>
        </div>
        {dateError && (
          <div className="form-group full">
            <p className="m-0 text-xs font-semibold text-red-600">{dateError}</p>
          </div>
        )}
        <div style={{ gridColumn: "1 / -1", display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 20 }}>
          <div className="form-group"><label className="form-label">Start time</label>
            <input
              className="form-input"
              type="time"
              value={form.startTime}
              onChange={e => set("startTime", e.target.value)}
              title="Time is stored in UTC in the system (same as the visit schedule clock you pick here)"
            /></div>
          <div className="form-group"><label className="form-label">End time</label>
            <input
              className="form-input"
              type="time"
              value={form.endTime}
              onChange={e => set("endTime", e.target.value)}
              title="Time is stored in UTC in the system (same as the visit schedule clock you pick here)"
            /></div>
        </div>
        {isEdit && (
          <div className="form-group"><label className="form-label">Status</label>
            <select className="form-select" value={form.status} onChange={e => set("status", e.target.value)}>
              <option>Scheduled</option><option>Site Confirmed</option><option>Reschedule Requested</option><option>In Progress</option><option>Post-Visit Action</option><option>Completed</option><option>Cancelled</option>
            </select></div>
        )}
      </div>
    </Modal>
  );
}

function newActionItemRow(defaultAssignee: string): ActionItemFormRow {
  return { assignee: defaultAssignee, due: "", closedDate: "", resolution: "", taskMode: "" };
}

function actionItemsFromFinding(finding: Finding, assigneeList: string[]): ActionItemFormRow[] {
  return getFindingActionItems(finding).map((item) => {
    const name = item.assignee.name;
    return {
      id: item.id,
      assignee: assigneeList.includes(name) ? name : (assigneeList[0] ?? name),
      due: dueDateToInput(item.dueDate),
      closedDate: dueDateToInput(item.closedDate || ""),
      resolution: item.resolution ?? "",
      taskMode: item.taskMode ?? "",
    };
  });
}

export function AddFindingModal({ open, onClose, onSubmit, assignees, assigneeOptions, assigneesLoading, initialFinding }: {
  open: boolean;
  onClose: () => void;
  onSubmit: (form: FindingFormValues) => void;
  assignees?: string[];
  assigneeOptions?: StudyTeamAssigneeOption[];
  assigneesLoading?: boolean;
  initialFinding?: Finding | null;
}) {
  const [form, setForm] = useState<FindingFormValues>({
    category: "ICF/Consent Issue",
    otherCategory: "",
    severity: "Major",
    finding: "",
    subjectId: "",
    reference: "",
    actionItems: [newActionItemRow("")],
  });
  const assigneeList = assignees ?? [];
  const assigneeLabelByName = useMemo(() => {
    const map = new Map<string, string>();
    assigneeOptions?.forEach((option) => map.set(option.name, option.label));
    return map;
  }, [assigneeOptions]);
  const assigneeLoading = Boolean(assigneesLoading);
  const cannotPickAssignee = assigneeLoading || assigneeList.length === 0;
  const isEdit = !!initialFinding;
  const minActionDueDate = useMemo(() => todayInputDate(), []);
  const originalActionDueDates = useMemo(
    () => initialFinding ? actionItemsFromFinding(initialFinding, assigneeList).map((item) => item.due) : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [initialFinding?.id, assigneeList.join(",")],
  );
  const isPastActionDueDate = (due: string, index: number) =>
    Boolean(due && due < minActionDueDate && (!isEdit || due !== originalActionDueDates[index]));
  const actionDueDateError = useMemo(() => {
    const invalidIndex = form.actionItems.findIndex((item, index) => isPastActionDueDate(item.due, index));
    if (invalidIndex < 0) return "";
    return `Action item ${invalidIndex + 1} due date cannot be in the past.`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.actionItems, isEdit, minActionDueDate, originalActionDueDates]);

  useEffect(() => {
    if (!open) return;
    const defaultAssignee = assigneeList[0] ?? "";
    if (initialFinding) {
      setForm({
        category: canonicalFindingCategory(initialFinding.category),
        otherCategory: canonicalFindingCategory(initialFinding.category) === "Other" ? initialFinding.category : "",
        severity: initialFinding.severity,
        finding: initialFinding.description,
        subjectId: (initialFinding.subjectId ?? "").trim(),
        reference: (initialFinding.reference ?? "").trim(),
        actionItems: actionItemsFromFinding(initialFinding, assigneeList),
      });
      return;
    }
    setForm({
      category: "ICF/Consent Issue",
      otherCategory: "",
      severity: "Major",
      finding: "",
      subjectId: "",
      reference: "",
      actionItems: [newActionItemRow(defaultAssignee)],
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialFinding?.id, assigneeList.join(",")]);

  const setField = (k: keyof Omit<FindingFormValues, "actionItems">, v: string) =>
    setForm((p) => ({ ...p, [k]: v }));

  const setActionItem = (index: number, patch: Partial<ActionItemFormRow>) => {
    setForm((p) => ({
      ...p,
      actionItems: p.actionItems.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    }));
  };

  const addActionItem = () => {
    setForm((p) => ({
      ...p,
      actionItems: [...p.actionItems, newActionItemRow(assigneeList[0] ?? "")],
    }));
  };

  const removeActionItem = (index: number) => {
    setForm((p) => ({
      ...p,
      actionItems: p.actionItems.length <= 1 ? p.actionItems : p.actionItems.filter((_, i) => i !== index),
    }));
  };

  const addDisabled = !form.finding.trim() || (!isEdit && cannotPickAssignee) || Boolean(actionDueDateError);
  return (
    <Modal
      open={open}
      title={isEdit ? "Edit Finding" : "Add Finding"}
      subtitle={isEdit ? "Update the finding and its follow-up actions" : "Log a monitoring finding and assign follow-up actions"}
      icon={
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 22V4a2 2 0 0 1 2-2h11l3 3v9l-3 3H7a2 2 0 0 0-2 2v3" />
          <path d="M4 15h9" />
        </svg>
      }
      onClose={onClose}
      footer={<><Btn variant="secondary" onClick={onClose}>Cancel</Btn><Btn variant="primary" onClick={() => onSubmit(form)} disabled={addDisabled}>{isEdit ? "Save changes" : "Add Finding"}</Btn></>}>
      <div className="form-grid">
        <div className="form-group full"><label className="form-label">Finding *</label>
          <input
            className="form-input"
            type="text"
            placeholder="Enter the finding"
            value={form.finding}
            onChange={e => setField("finding", e.target.value)}
          /></div>
        <div className="form-group"><label className="form-label">Category</label>
          <select className="form-select" value={form.category} onChange={e => setField("category", e.target.value)}>
            {!FINDING_CATEGORIES.includes(form.category as (typeof FINDING_CATEGORIES)[number]) && form.category ? (
              <option value={form.category}>{form.category}</option>
            ) : null}
            {FINDING_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select></div>
        {form.category === "Other" && (
          <div className="form-group"><label className="form-label">Please specify category</label>
            <input
              className="form-input"
              type="text"
              placeholder="Enter custom category"
              value={form.otherCategory}
              onChange={e => setField("otherCategory", e.target.value)}
            /></div>
        )}
        <div className="form-group">
          <label className="form-label">Severity</label>
          <select className="form-select" value={form.severity} onChange={e => setField("severity", e.target.value)}>
            <option>No Findings</option><option>Critical</option><option>Major</option><option>Minor</option>
          </select>
        </div>
        <div className="form-group full">
          <label className="form-label">
            Subject ID{" "}
            <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(if applicable)</span>
          </label>
          <input
            className="form-input"
            type="text"
            placeholder="e.g. 101-001"
            value={form.subjectId}
            onChange={(e) => setField("subjectId", e.target.value)}
          />
        </div>

        <div className="form-group full">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
            <label className="form-label" style={{ margin: 0 }}>Action Items</label>
            <Btn variant="secondary" size="sm" onClick={addActionItem}>＋ Add action item</Btn>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {form.actionItems.map((item, index) => (
              <div key={`action-item-${index}`} className="action-item-card">
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>
                    <span className="action-item-badge">{index + 1}</span>
                    Action item
                  </span>
                  {form.actionItems.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeActionItem(index)}
                      className="action-item-remove"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      </svg>
                      Remove
                    </button>
                  )}
                </div>
                <div className="form-grid" style={{ marginBottom: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Responsible Person</label>
                    <select
                      className="form-select"
                      value={item.assignee}
                      onChange={(e) => setActionItem(index, { assignee: e.target.value })}
                      disabled={assigneeLoading || assigneeList.length === 0}
                      title={assigneeLoading ? "Loading study team from IAM" : assigneeList.length === 0 ? "No active study team members for this study" : undefined}
                    >
                      {assigneeLoading ? (
                        <option value="" disabled>Loading study team…</option>
                      ) : assigneeList.length === 0 ? (
                        <option value="" disabled>No study team members</option>
                      ) : (
                        assigneeList.map(c => <option key={c} value={c}>{assigneeLabelByName.get(c) || c}</option>)
                      )}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Due Date</label>
                    {(() => {
                      const dueDateInvalid = isPastActionDueDate(item.due, index);
                      return (
                        <>
                          <input
                            className="form-input"
                            type="date"
                            value={item.due}
                            min={minActionDueDate}
                            aria-invalid={dueDateInvalid}
                            onChange={(e) => setActionItem(index, { due: e.target.value })}
                          />
                          {dueDateInvalid && (
                            <p className="m-0 mt-1 text-xs font-semibold text-red-600">
                              Due date cannot be in the past.
                            </p>
                          )}
                        </>
                      );
                    })()}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Task Mode</label>
                    <select
                      className="form-select"
                      value={item.taskMode}
                      onChange={(e) => setActionItem(index, { taskMode: e.target.value })}
                    >
                      <option value="">— Select —</option>
                      <option value="remote">Remote</option>
                      <option value="on-site">On-site</option>
                    </select>
                  </div>
                </div>
                <div className="form-group full" style={{ marginBottom: 0 }}>
                  <label className="form-label">Action</label>
                  <textarea
                    className="form-textarea"
                    style={{ minHeight: 60 }}
                    placeholder="Describe what the assignee should do to address this finding…"
                    value={item.resolution}
                    onChange={(e) => setActionItem(index, { resolution: e.target.value })}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
