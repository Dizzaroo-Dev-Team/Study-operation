import { useEffect, useMemo, useState } from "react";
import { ConfirmationLetterPreview } from "./ConfirmationLetterPreview";
import { ConfirmationLetterSplitEditor } from "./ConfirmationLetterSplitEditor";
import {
  buildLetterValues,
  DEFAULT_CONTENT,
  renderLetterTemplate,
  resolveLetterTemplate,
} from "./confirmationLetterModel";
import { useVisitWorkflow } from "../../../context/VisitWorkflowContext";
import { useSaveConfirmationLetter, useSendConfirmationLetter } from "@/lib/queries/useMonitoring";
import { api } from "../../../../../lib/api";

export function ConfirmationLetterTab({ visitId, showToast, visitStatus, isVisitClosed = false }: {
  visitId: string;
  showToast: (msg: string, type?: string) => void;
  visitStatus?: string;
  isVisitClosed?: boolean;
}) {
  const [editMode, setEditMode] = useState(false);
  const [content, setContent] = useState(DEFAULT_CONTENT);
  const [lastSent, setLastSent] = useState("N/A");
  const [deliveryStatus, setDeliveryStatus] = useState("Draft");
  const [fromLine, setFromLine] = useState("—");
  const [reLine, setReLine] = useState("—");
  const [docDate, setDocDate] = useState("—");
  const [isSending, setIsSending] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isSendModalOpen, setIsSendModalOpen] = useState(false);
  const [ccEmails, setCcEmails] = useState("");

  const { overview: visitOverview, confirmationLetter, confirmationLetterLoading } = useVisitWorkflow();
  const saveLetterMutation = useSaveConfirmationLetter(visitId);
  const sendLetterMutation = useSendConfirmationLetter(visitId);
  const [hydrated, setHydrated] = useState(false);

  const formatTodayLong = () =>
    new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  useEffect(() => {
    if (hydrated || confirmationLetterLoading) return;
    const letterData = confirmationLetter;
    if (letterData) {
      setContent(letterData.content || DEFAULT_CONTENT);
      setLastSent(letterData.last_sent || "N/A");
      setDeliveryStatus(letterData.delivery_status || "Draft");
      if (letterData.last_sent && String(letterData.last_sent).trim() && letterData.last_sent !== "N/A") {
        setDocDate(String(letterData.last_sent).trim());
      } else {
        setDocDate(formatTodayLong());
      }
    } else {
      setLastSent("N/A");
      setDeliveryStatus("Draft");
      setDocDate(formatTodayLong());
    }
    setHydrated(true);
  }, [hydrated, confirmationLetterLoading, confirmationLetter, visitOverview]);

  useEffect(() => {
    const vd = visitOverview?.visitDetails;
    if (!vd) return;
    const visitDate = (vd.visitDate || "").trim() || "TBD";
    const sponsor = (vd.sponsor || "").trim() || "Sponsor";
    const cra = (vd.craName || "").trim() || "Clinical Research Associate";
    setReLine(`Monitoring Visit Confirmation — ${visitDate}`);
    setFromLine(`${cra}, CRA Lead — ${sponsor}`);
  }, [
    visitOverview?.visitDetails?.visitDate,
    visitOverview?.visitDetails?.endDate,
    visitOverview?.visitDetails?.sponsor,
    visitOverview?.visitDetails?.craName,
  ]);

  useEffect(() => {
    setHydrated(false);
  }, [visitId]);

  const letterTemplate = useMemo(() => resolveLetterTemplate(content), [content]);

  const { values, requiresPharmacy } = useMemo(
    () => buildLetterValues(visitOverview, docDate, formatTodayLong),
    [visitOverview, docDate],
  );

  const renderedContent = useMemo(
    () => renderLetterTemplate(letterTemplate, values, requiresPharmacy),
    [letterTemplate, values, requiresPharmacy],
  );

  const normalizedVisitStatus = String(visitStatus || "").trim().toLowerCase();
  const statusLabel = normalizedVisitStatus === "site confirmed"
    ? "Confirmed"
    : normalizedVisitStatus === "reschedule requested" || normalizedVisitStatus === "rescheduled"
      ? "Rescheduled"
      : deliveryStatus;

  const recipientPiName = (visitOverview?.siteContact?.principalInvestigator || "").trim() || "Principal Investigator";
  const recipientPiEmail = (visitOverview?.siteContact?.piEmail || "").trim() || "—";
  const recipientCoordinatorName = (visitOverview?.siteContact?.studyCoordinator || "").trim() || "Study Coordinator";
  const recipientCoordinatorEmail = (visitOverview?.siteContact?.coordinatorEmail || "").trim() || "—";

  const handleDownloadPdf = async () => {
    try {
      setIsDownloading(true);
      const response = await api.get<Blob>(
        `/monitor/visits/${encodeURIComponent(visitId)}/confirmation-letter/pdf`,
        { responseType: "blob" },
      );
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${String(visitId || "visit")}-confirmation-letter.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => {
        window.URL.revokeObjectURL(url);
      }, 0);

      showToast("PDF downloaded", "success");
    } catch {
      showToast("Failed to download PDF", "error");
    } finally {
      setIsDownloading(false);
    }
  };

  const handleCloseSendModal = () => {
    setIsSendModalOpen(false);
    setCcEmails("");
  };

  const handleConfirmSend = async () => {
    if (isSending) return;
    try {
      setIsSending(true);
      const sent = await sendLetterMutation.mutateAsync({ content: renderedContent, ccEmails });
      setLastSent(sent.last_sent || lastSent);
      if (sent.last_sent) setDocDate(String(sent.last_sent));
      setDeliveryStatus(sent.delivery_status || "Delivered");
      showToast("Letter sent to site", "success");
      handleCloseSendModal();
    } catch {
      showToast("Failed to send letter", "error");
    } finally {
      setIsSending(false);
    }
  };

  const statusStyles: Record<string, string> = {
    Draft: "bg-amber-50 text-amber-700 border-amber-200",
    Delivered: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Rescheduled: "bg-violet-50 text-violet-700 border-violet-200",
  };
  const statusPill = statusStyles[statusLabel] || "bg-slate-50 text-slate-600 border-slate-200";

  return (
    <div className="fade-in">
      {/* ── Header card ─────────────────────────────────────────────────── */}
      <div
        className="relative overflow-hidden rounded-t-2xl border border-b-0 border-slate-200"
        style={{ background: "linear-gradient(135deg, #168AAD 0%, #76C893 100%)" }}
      >
        <div className="absolute -right-8 -top-10 h-40 w-40 rounded-full bg-white/10" aria-hidden="true" />
        <div className="absolute -right-20 top-6 h-48 w-48 rounded-full bg-white/[0.07]" aria-hidden="true" />
        <div className="relative flex flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/20 border border-white/30 text-white shadow-sm">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <path d="m2 7 10 6 10-6" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold text-white leading-tight">Confirmation Letter</h2>
                <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${statusPill}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" />
                  {statusLabel}
                </span>
              </div>
              <p className="text-xs text-white/80 mt-0.5 truncate">
                Formal visit notice to the investigative site · Last sent: <span className="font-semibold text-white/95">{lastSent}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              disabled={isVisitClosed}
              onClick={() => {
                void (async () => {
                  if (editMode) {
                    await saveLetterMutation.mutateAsync(letterTemplate);
                    showToast("Letter saved", "success");
                    setContent(letterTemplate);
                    setEditMode(false);
                    return;
                  }
                  setContent(letterTemplate);
                  setEditMode(true);
                })();
              }}
              className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
                editMode
                  ? "border-white bg-white text-[#168AAD] hover:bg-white/90"
                  : "border-white/40 bg-white/15 text-white hover:bg-white/25"
              }`}
            >
              {editMode ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                  <polyline points="17 21 17 13 7 13 7 21" />
                  <polyline points="7 3 7 8 15 8" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              )}
              {editMode ? "Save Letter" : "Edit"}
            </button>

            <button
              type="button"
              disabled={isDownloading}
              onClick={() => void handleDownloadPdf()}
              className="inline-flex items-center gap-2 rounded-lg border border-white/40 bg-white/15 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-white/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isDownloading ? (
                <svg className="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="50" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              )}
              {isDownloading ? "Generating…" : "Download PDF"}
            </button>

            {!isVisitClosed && (
              <button
                type="button"
                disabled={isSending}
                onClick={() => setIsSendModalOpen(true)}
                className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-bold text-[#168AAD] shadow hover:bg-white/90 transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
                {isSending ? "Sending…" : "Send to Site"}
              </button>
            )}
          </div>
        </div>
      </div>

      <div
        className="doc-viewer doc-viewer--letter"
        style={isVisitClosed ? { pointerEvents: "none", userSelect: "none" } : undefined}
      >
        {editMode ? (
          <ConfirmationLetterSplitEditor
            template={letterTemplate}
            values={values}
            requiresPharmacy={requiresPharmacy}
            readOnly={isVisitClosed}
            onTemplateChange={setContent}
          />
        ) : (
          <ConfirmationLetterPreview
            content={renderedContent}
            envelope={{
              fromLine: fromLine !== "—" ? fromLine : undefined,
              reLine: reLine !== "—" ? reLine : undefined,
            }}
          />
        )}
      </div>

      {isSendModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm"
          onClick={handleCloseSendModal}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div
              className="flex items-center justify-between px-6 py-4"
              style={{ background: "linear-gradient(135deg, #168AAD 0%, #76C893 100%)" }}
            >
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/20 border border-white/30 text-white">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-base font-bold text-white leading-tight">Confirm &amp; Send Letter</h2>
                  <p className="text-xs text-white/80 mt-0.5">Delivered to the site's PI and Study Coordinator</p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleCloseSendModal}
                className="text-white/80 hover:text-white text-2xl leading-none"
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="p-6">
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Recipients</div>
                <div className="mt-3 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-100 text-[11px] font-bold text-sky-700">
                        PI
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-800 truncate">{recipientPiName}</div>
                        <div className="text-xs text-slate-500">Principal Investigator</div>
                      </div>
                    </div>
                    <div className="max-w-[240px] break-all text-right text-sm font-medium text-[#168AAD]">
                      {recipientPiEmail}
                    </div>
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-[11px] font-bold text-emerald-700">
                        SC
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-800 truncate">{recipientCoordinatorName}</div>
                        <div className="text-xs text-slate-500">Study Coordinator</div>
                      </div>
                    </div>
                    <div className="max-w-[240px] break-all text-right text-sm font-medium text-[#168AAD]">
                      {recipientCoordinatorEmail}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <label htmlFor="cc-emails" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  CC Emails <span className="font-normal text-slate-400">(optional)</span>
                </label>
                <input
                  id="cc-emails"
                  type="text"
                  value={ccEmails}
                  onChange={(e) => setCcEmails(e.target.value)}
                  placeholder="e.g. coordinator@site.com, cra@sponsor.com"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-[#168AAD] focus:ring-2 focus:ring-[#168AAD]/25"
                />
                <p className="mt-1.5 text-xs text-slate-500">Separate multiple email addresses with a comma.</p>
              </div>

              <div className="mt-6 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={handleCloseSendModal}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleConfirmSend()}
                  disabled={isSending}
                  className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold text-white shadow-md transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
                  style={{ background: "linear-gradient(135deg, #168AAD 0%, #76C893 100%)" }}
                >
                  {isSending ? (
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="50" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <line x1="22" y1="2" x2="11" y2="13" />
                      <polygon points="22 2 15 22 11 13 2 9 22 2" />
                    </svg>
                  )}
                  {isSending ? "Sending…" : "Confirm & Send"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
