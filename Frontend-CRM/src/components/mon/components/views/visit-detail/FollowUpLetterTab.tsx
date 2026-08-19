import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType,   VerticalAlign,
} from "docx";
import {
  useSaveFollowUpLetter,
  useVisitFindings,
} from "@/lib/queries/useMonitoring";
import { useVisitWorkflow } from "../../../context/VisitWorkflowContext";
import type { VisitOverviewPayload, Finding as MonitoringFinding } from "../../../types";
import { getFindingActionItems } from "../../../utils/findingActionItems";
import { DocxPreviewModal } from "./DocxPreviewModal";

/** Rows for §3 / §4 in DOCX/PDF — sourced from Visit Findings tab only. */
type SummaryFindingRow = {
  subject: string;
  description: string;
  category: string;
  severity: string;
  reference: string;
  dueDate: string;
  resolution: string;
};

/** §4 Action Items table (same underlying findings as §3). */
type ActionItemRow = {
  title: string;
  action: string;
  dueDate: string;
  assignTo: string;
  priority: string;
};

function mapVisitFindingsToSummary(rows: MonitoringFinding[]): SummaryFindingRow[] {
  return rows
    .filter((f) => String(f.status || "").trim().toLowerCase() !== "archived")
    .map((f) => ({
      subject: (f.subjectId || "").trim(),
      description: f.description || "",
      category: f.category || "",
      severity: f.severity || "Major",
      reference: (f.reference || "").trim(),
      dueDate: formatFindingDueDate(f.dueDate),
      resolution: (f.resolution || "").trim(),
    }));
}

function formatFindingDueDate(due: string | undefined): string {
  const d = (due || "").trim();
  if (!d || d.toUpperCase() === "TBD") return "";
  return d;
}

function mapFindingsToActionItems(findings: MonitoringFinding[]): ActionItemRow[] {
  const items: ActionItemRow[] = [];
  for (const f of findings.filter((row) => String(row.status || "").trim().toLowerCase() !== "archived")) {
    const titleBase = [f.category, f.description].filter(Boolean).join(" — ") || "—";
    for (const ai of getFindingActionItems(f)) {
      items.push({
        title: titleBase,
        action: (ai.resolution || "").trim() || "Address per protocol and monitor guidance.",
        dueDate: formatFindingDueDate(ai.dueDate),
        assignTo: (ai.assignee?.name || "").trim() || "—",
        priority: f.severity || "Major",
      });
    }
  }
  return items;
}

function actionItemsOrPlaceholder(rows: ActionItemRow[]): ActionItemRow[] {
  if (rows.length > 0) return rows;
  return [
    {
      title: "No action items — no findings recorded on the Visit Findings tab for this visit.",
      action: "",
      dueDate: "",
      assignTo: "",
      priority: "",
    },
  ];
}

function summaryRowsOrPlaceholder(rows: SummaryFindingRow[]): SummaryFindingRow[] {
  if (rows.length > 0) return rows;
  return [
    {
      subject: "",
      description: "No findings recorded on the Visit Findings tab for this visit.",
      category: "",
      severity: "",
      reference: "",
      dueDate: "",
      resolution: "",
    },
  ];
}

// ─── Types ─────────────────────────────────────────────────────────────────
const AREA_STATUSES = ["Reviewed", "Finding Identified — See Section 3", "N/A", "Not Reviewed"];
const DEFAULT_AREAS: Area[] = [
  { id: 1, name: "Informed Consent Forms (ICF)", status: "Reviewed" },
  { id: 2, name: "Source Documents and Case Report Forms (CRFs)", status: "Reviewed" },
  { id: 3, name: "Investigational Product (IP) Accountability", status: "Reviewed" },
  { id: 4, name: "Adverse Event / SAE Reporting", status: "Reviewed" },
];

type Area    = { id: number; name: string; status: string };

type FormData = {
  letterDate: string; visitDate: string; studyTitle: string; protocolNumber: string;
  siteName: string; siteAddress: string; piName: string; monitorName: string; sponsorName: string;
  monitorEmail: string; sponsorContact: string;
  totalSubjects: string; ongoingSubjects: string;
  criticalTimeline: string; criticalEscalation: string;
  majorTimeline: string; majorEscalation: string;
  minorTimeline: string; minorEscalation: string;
};

type DraftPayload = {
  version: 1;
  form: FormData;
  areas: Area[];
};

// ─── Helpers ───────────────────────────────────────────────────────────────
function formatDateForInput(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function toInputDate(value: string | undefined | null): string {
  if (!value) return "";
  let raw = value.trim();
  if (!raw) return "";

  // Already a clean ISO date
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

  // Strip time part after · bullet (e.g. "June 04, 2026 · 8:00 AM")
  raw = raw.split("·")[0].trim();

  // Take only the first date if range (e.g. "Jun 04 to Jun 06")
  raw = raw.split(/\s+to\s+|–|—/i)[0].trim();

  // DD-MMM-YYYY or DD/MMM/YYYY  (e.g. "04-JUN-2026")
  const ddMmmYyyy = raw.match(/^(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s](\d{4})$/);
  if (ddMmmYyyy) {
    const [, dd, mon, yyyy] = ddMmmYyyy;
    const d = new Date(`${dd} ${mon} ${yyyy}`);
    if (!Number.isNaN(d.getTime())) return formatDateForInput(d);
  }

  // Let the browser parse anything else (handles "June 04, 2026", "2026-06-04T08:00:00Z", etc.)
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return formatDateForInput(parsed);
}

function todayInputDate(): string {
  return formatDateForInput(new Date());
}

function parseSavedDraft(raw: string): DraftPayload | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<DraftPayload>;
    if (parsed && parsed.version === 1 && parsed.form && Array.isArray(parsed.areas)) {
      return { version: 1, form: parsed.form as FormData, areas: parsed.areas as Area[] };
    }
  } catch {
    return null;
  }
  return null;
}

function serializeDraft(payload: { form: FormData; areas: Area[] }): string {
  return JSON.stringify({ version: 1, ...payload });
}

// ─── Docx generation ───────────────────────────────────────────────────────
function buildDoc(data: FormData & { areas: Area[]; summaryFindings: SummaryFindingRow[]; actionItems: ActionItemRow[] }) {
  const w = 9360;
  const col = Math.floor(w / 4);
  const cb = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
  const borders = { top: cb, bottom: cb, left: cb, right: cb };
  const hFill = { fill: "2E5496", type: ShadingType.CLEAR };
  const aFill = { fill: "EBF1F8", type: ShadingType.CLEAR };
  const wFill = { fill: "FFFFFF", type: ShadingType.CLEAR };
  const lFill = { fill: "D9E1F2", type: ShadingType.CLEAR };
  const cm = { top: 80, bottom: 80, left: 120, right: 120 };

  const hCell = (text: string, width: number) => new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, shading: hFill, margins: cm,
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 20 })] })],
  });
  const dCell = (text: string, width: number, shade = false) => new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, shading: shade ? aFill : wFill, margins: cm,
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: [new TextRun({ text, size: 20 })] })],
  });
  const lCell = (label: string, width: number) => new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, shading: lFill, margins: cm,
    children: [new Paragraph({ children: [new TextRun({ text: label, bold: true, size: 20 })] })],
  });
  const vCell = (text: string, width: number) => new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, shading: wFill, margins: cm,
    children: [new Paragraph({ children: [new TextRun({ text, size: 20 })] })],
  });
  const spacer = () => new Paragraph({ children: [], spacing: { before: 160, after: 0 } });
  const secHead = (num: number, text: string) => new Paragraph({
    children: [new TextRun({ text: `${num}. ${text}`, bold: true, size: 24, color: "2E5496" })],
    spacing: { before: 240, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E5496", space: 1 } },
  });
  const body = (runs: TextRun[]) => new Paragraph({ children: runs, spacing: { before: 80, after: 80 } });
  const r = (text: string) => new TextRun({ text, size: 20 });
  const b = (text: string) => new TextRun({ text, bold: true, size: 20 });

  const headerTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: [col, col, col, col],
    rows: [
      new TableRow({ children: [lCell("Date:", col), vCell(data.letterDate, col), lCell("Visit Date:", col), vCell(data.visitDate, col)] }),
      new TableRow({ children: [lCell("Study Title:", col), vCell(data.studyTitle, col), lCell("Protocol Number:", col), vCell(data.protocolNumber, col)] }),
      new TableRow({ children: [lCell("Site:", col), vCell(data.siteName, col), lCell("Principal Investigator:", col), vCell(data.piName, col)] }),
      new TableRow({
        children: [
          lCell("Site Address:", col),
          new TableCell({
            borders,
            columnSpan: 3,
            width: { size: col * 3, type: WidthType.DXA },
            shading: wFill,
            margins: cm,
            children: [new Paragraph({ children: [new TextRun({ text: data.siteAddress || "—", size: 20 })] })],
          }),
        ],
      }),
      new TableRow({ children: [lCell("Monitor Name:", col), vCell(data.monitorName, col), lCell("Sponsor:", col), vCell(data.sponsorName, col)] }),
    ],
  });

  const areasTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: [600, 5560, 3200],
    rows: [
      new TableRow({ children: [hCell("#", 600), hCell("Area Reviewed", 5560), hCell("Status", 3200)] }),
      ...data.areas.map((a, i) => new TableRow({ children: [
        dCell(String(i + 1), 600, i % 2 !== 0),
        dCell(a.name, 5560, i % 2 !== 0),
        dCell(a.status, 3200, i % 2 !== 0),
      ] })),
    ],
  });

  const fCols = [400, 900, 2800, 1500, 1260, 1500];
  const findingsTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: fCols,
    rows: [
      new TableRow({ children: [hCell("#", fCols[0]), hCell("Subject", fCols[1]), hCell("Finding Description", fCols[2]), hCell("Category", fCols[3]), hCell("Severity", fCols[4]), hCell("Reference", fCols[5])] }),
      ...data.summaryFindings.map((f, i) => new TableRow({ children: [
        dCell(String(i + 1), fCols[0], i % 2 !== 0),
        dCell(f.subject, fCols[1], i % 2 !== 0),
        dCell(f.description, fCols[2], i % 2 !== 0),
        dCell(f.category, fCols[3], i % 2 !== 0),
        new TableCell({
          borders, width: { size: fCols[4], type: WidthType.DXA },
          shading: i % 2 !== 0 ? aFill : wFill, margins: cm,
          children: [new Paragraph({ children: [new TextRun({ text: f.severity, bold: true, size: 20, color: f.severity === "Critical" ? "C00000" : f.severity === "Major" ? "CC6600" : "007000" })] })],
        }),
        dCell(f.reference, fCols[5], i % 2 !== 0),
      ] })),
    ],
  });

  const aCols = [350, 1700, 2200, 1100, 1300, 1710];
  const actionTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: aCols,
    rows: [
      new TableRow({ children: [hCell("#", aCols[0]), hCell("Action Item / Finding", aCols[1]), hCell("Required Action", aCols[2]), hCell("Due Date", aCols[3]), hCell("Assign To", aCols[4]), hCell("Priority", aCols[5])] }),
      ...data.actionItems.map((a, i) => new TableRow({ children: [
        dCell(String(i + 1), aCols[0], i % 2 !== 0),
        dCell(a.title, aCols[1], i % 2 !== 0),
        dCell(a.action, aCols[2], i % 2 !== 0),
        dCell(a.dueDate, aCols[3], i % 2 !== 0),
        dCell(a.assignTo, aCols[4], i % 2 !== 0),
        new TableCell({
          borders, width: { size: aCols[5], type: WidthType.DXA },
          shading: i % 2 !== 0 ? aFill : wFill, margins: cm,
          children: [new Paragraph({ children: [new TextRun({ text: a.priority, bold: true, size: 20, color: a.priority === "Critical" ? "C00000" : a.priority === "Major" ? "CC6600" : "007000" })] })],
        }),
      ] })),
    ],
  });

  const rCols = [2400, 3480, 3480];
  const resTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: rCols,
    rows: [
      new TableRow({ children: [hCell("Severity Level", rCols[0]), hCell("Required Response Timeline", rCols[1]), hCell("Escalation Timeline", rCols[2])] }),
      new TableRow({ children: [dCell("Critical", rCols[0]), dCell(data.criticalTimeline, rCols[1]), dCell(data.criticalEscalation, rCols[2])] }),
      new TableRow({ children: [dCell("Major", rCols[0], true), dCell(data.majorTimeline, rCols[1], true), dCell(data.majorEscalation, rCols[2], true)] }),
      new TableRow({ children: [dCell("Minor", rCols[0]), dCell(data.minorTimeline, rCols[1]), dCell(data.minorEscalation, rCols[2])] }),
    ],
  });

  const authCols = [3000, 6360];
  const authTable = new Table({
    width: { size: w, type: WidthType.DXA }, columnWidths: authCols,
    rows: [
      new TableRow({ children: [lCell("Monitor Name", authCols[0]), vCell(data.monitorName, authCols[1])] }),
      new TableRow({ children: [lCell("Monitor Signature", authCols[0]), vCell("", authCols[1])] }),
      new TableRow({ children: [lCell("Date", authCols[0]), vCell(data.letterDate, authCols[1])] }),
      new TableRow({ children: [lCell("Sponsor / CRO Contact", authCols[0]), vCell(data.sponsorContact, authCols[1])] }),
    ],
  });

  const doc = new Document({
    styles: { default: { document: { run: { font: "Arial", size: 22 } } } },
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 } } },
      children: [
        new Paragraph({ children: [new TextRun({ text: "SITE FOLLOW-UP LETTER", bold: true, size: 32, color: "2E5496" })], alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 } }),
        new Paragraph({ children: [new TextRun({ text: "Monitoring Visit — Post-Visit Communication", size: 20, italics: true, color: "595959" })], alignment: AlignmentType.CENTER, spacing: { before: 0, after: 200 } }),
        headerTable, spacer(),
        secHead(1, "INTRODUCTION"),
        body([r("Dear "), b(data.piName), r(",")]),
        body([r("This letter is issued as a formal follow-up to the monitoring visit conducted at "), b(data.siteName), r(" on "), b(data.visitDate), r(", as part of the "), b(data.studyTitle), r(" (Protocol Number: "), b(data.protocolNumber), r(") sponsored by "), b(data.sponsorName), r(".")]),
        body([r("The purpose of this correspondence is to document the findings, observations, and action items identified during the visit. During the visit, a total of "), b(data.totalSubjects), r(" subjects were reviewed, with "), b(data.ongoingSubjects), r(" currently ongoing in the study.")]),
        body([r("We appreciate the cooperation and assistance provided by you and your study team during the visit.")]),
        spacer(),
        secHead(2, "AREAS REVIEWED"),
        body([r("The following areas were reviewed during the monitoring visit:")]),
        new Paragraph({ children: [], spacing: { before: 100, after: 0 } }),
        areasTable, spacer(),
        secHead(3, "SUMMARY OF FINDINGS"),
        body([r("The following findings were identified during the monitoring visit. Each finding is assigned a severity level in accordance with GCP guidelines.")]),
        new Paragraph({ children: [], spacing: { before: 100, after: 0 } }),
        findingsTable, spacer(),
        secHead(4, "ACTION ITEMS"),
        body([r("The table below summarizes all required actions arising from this monitoring visit.")]),
        new Paragraph({ children: [], spacing: { before: 100, after: 0 } }),
        actionTable, spacer(),
        secHead(5, "RESOLUTION TIMELINES"),
        new Paragraph({ children: [], spacing: { before: 80, after: 0 } }),
        resTable, spacer(),
        secHead(6, "CLOSING REMARKS"),
        body([r("Please confirm receipt of this letter and provide your written response addressing each action item. Your response should be directed to "), b(data.monitorEmail), r(" with a copy to "), b(data.sponsorContact), r(".")]),
        body([r("Should you require clarification on any of the items raised in this letter, please do not hesitate to contact me directly. We look forward to your timely response and continued collaboration on this study.")]),
        body([r("Thank you for your continued support.")]),
        new Paragraph({ children: [r("Sincerely,")], spacing: { before: 80, after: 200 } }),
        new Paragraph({ children: [b("AUTHORIZATION")], spacing: { before: 0, after: 120 } }),
        authTable, spacer(),
        new Paragraph({ children: [new TextRun({ text: "— END OF DOCUMENT —", italics: true, color: "808080", size: 20 })], alignment: AlignmentType.CENTER, spacing: { before: 160, after: 0 } }),
      ],
    }],
  });
  return doc;
}

// ─── Sub-components ─────────────────────────────────────────────────────────
const Field = ({ label, value, onChange, type = "text", required, hint }: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; required?: boolean; hint?: string;
}) => (
  <div style={{ marginBottom: 16 }}>
    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#2d3748", marginBottom: 6, letterSpacing: "0.05em", textTransform: "uppercase" }}>
      {label}{required && <span style={{ color: "#e53e3e", marginLeft: 4 }}>*</span>}
    </label>
    <input type={type} value={value} onChange={e => onChange(e.target.value)}
      style={{ width: "100%", boxSizing: "border-box", fontSize: 14, padding: "10px 12px", border: "1.5px solid #e2e8f0", borderRadius: "8px", background: "#fff", transition: "all 0.3s", outline: "none" }}
      onFocus={(e) => { e.target.style.borderColor = "#667eea"; e.target.style.boxShadow = "0 0 0 3px rgba(102, 126, 234, 0.1)"; }}
      onBlur={(e) => { e.target.style.borderColor = "#e2e8f0"; e.target.style.boxShadow = "none"; }} />
    {hint && <p style={{ fontSize: 12, color: "#718096", margin: "4px 0 0", fontStyle: "italic" }}>{hint}</p>}
  </div>
);

const SectionCard = ({ title, icon, children, accent = "#667eea" }: {
  title: string; icon: string; children: React.ReactNode; accent?: string;
}) => (
  <div style={{ background: "#fff", border: "none", borderRadius: "12px", marginBottom: 24, overflow: "hidden", boxShadow: "0 4px 20px rgba(0, 0, 0, 0.08)", transition: "all 0.3s ease" }}
    onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 12px 40px rgba(0, 0, 0, 0.15)"; (e.currentTarget as HTMLDivElement).style.transform = "translateY(-2px)"; }}
    onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 20px rgba(0, 0, 0, 0.08)"; (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)"; }}>
    <div style={{ borderLeft: `4px solid ${accent}`, padding: "16px 20px", background: `linear-gradient(135deg, ${accent}08 0%, ${accent}04 100%)`, display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ width: 40, height: 40, borderRadius: 8, background: `${accent}20`, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <i className={`ti ti-${icon}`} style={{ fontSize: 20, color: accent }} aria-hidden="true" />
      </div>
      <span style={{ fontWeight: 600, fontSize: 15, color: "#2d3748" }}>{title}</span>
    </div>
    <div style={{ padding: "20px" }}>{children}</div>
  </div>
);

const Grid2 = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px", marginBottom: 4 }}>{children}</div>
);

const AddBtn = ({ onClick, label }: { onClick: () => void; label: string }) => (
  <button onClick={onClick} style={{ fontSize: 13, padding: "8px 16px", color: "#667eea", border: "1.5px solid #667eea", borderRadius: "8px", background: "transparent", cursor: "pointer", marginTop: 8, fontWeight: 600, transition: "all 0.3s" }}
    onMouseEnter={(e) => { (e.target as HTMLButtonElement).style.background = "#667eea"; (e.target as HTMLButtonElement).style.color = "#fff"; }}
    onMouseLeave={(e) => { (e.target as HTMLButtonElement).style.background = "transparent"; (e.target as HTMLButtonElement).style.color = "#667eea"; }}>
    <i className="ti ti-plus" style={{ fontSize: 13, marginRight: 6, verticalAlign: "middle" }} aria-hidden="true" />
    {label}
  </button>
);

const RemoveBtn = ({ onClick }: { onClick: () => void }) => (
  <button
    type="button"
    onClick={onClick}
    title="Remove"
    aria-label="Remove"
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 8,
      color: "#718096",
      background: "transparent",
      border: "none",
      borderRadius: 6,
      cursor: "pointer",
      transition: "color 0.2s, background 0.2s",
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.color = "#e53e3e";
      e.currentTarget.style.background = "#fef2f2";
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.color = "#718096";
      e.currentTarget.style.background = "transparent";
    }}
  >
    <Trash2 size={18} strokeWidth={2} aria-hidden />
  </button>
);

const StatBadge = ({ n, color = "#667eea" }: { n: number; color?: string }) => (
  <span style={{ background: `${color}18`, color, fontSize: 12, fontWeight: 700, padding: "4px 10px", borderRadius: 20, border: `1.5px solid ${color}40`, minWidth: 24, textAlign: "center", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>{n}</span>
);

// ─── Main Component ─────────────────────────────────────────────────────────
function buildInitialForm(overview: VisitOverviewPayload | null): FormData {
  const vd = overview?.visitDetails;
  const sc = overview?.siteContact;
  return {
    letterDate: todayInputDate(),
    visitDate: toInputDate(vd?.visitDate),
    studyTitle: String(vd?.protocol || ""),
    protocolNumber: String(vd?.protocol || ""),
    siteName: String(sc?.institutionName || ""),
    siteAddress: String(sc?.siteAddress || ""),
    piName: String(sc?.principalInvestigator || ""),
    monitorName: String(vd?.craName || ""),
    sponsorName: String(vd?.sponsor || ""),
    monitorEmail: String(vd?.craEmail || ""),
    sponsorContact: "",
    totalSubjects: "",
    ongoingSubjects: "",
    criticalTimeline: "Within 48 hours of receipt",
    criticalEscalation: "Immediate Sponsor notification required",
    majorTimeline: "Within 7 calendar days",
    majorEscalation: "Escalation if unresolved within 14 days",
    minorTimeline: "Within 14 calendar days",
    minorEscalation: "Escalation if unresolved within 30 days",
  };
}

export function FollowUpLetterTab({
  visitId,
  showToast,
  isVisitClosed = false,
  isAcknowledged: isAcknowledgedProp = false,
}: {
  visitId: string;
  showToast: (msg: string, type?: string) => void;
  isVisitClosed?: boolean;
  /** Once the PI/site acknowledges the letter the form locks (read-only). */
  isAcknowledged?: boolean;
}) {
  const [generating, setGenerating] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [previewBlob, setPreviewBlob] = useState<Blob | null>(null);
  const [piEmail, setPiEmail] = useState("");
  const [isSendModalOpen, setIsSendModalOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [localAcknowledged, setLocalAcknowledged] = useState<boolean>(isAcknowledgedProp);
  const [acknowledgedAt, setAcknowledgedAt] = useState<string | null>(null);
  const [localSentAt, setLocalSentAt] = useState<string | null>(null);
  const [localDeliveryStatus, setLocalDeliveryStatus] = useState<string | null>(null);
  // Has the one-shot hydration from queries run? Once true, the form is
  // user-owned and must NOT be re-seeded by background refetches.
  const [hydrated, setHydrated] = useState(false);

  const { overview, followUp, followUpLoading: followUpQueryLoading, overviewLoading: overviewQueryLoading } = useVisitWorkflow();
  const findingsQuery = useVisitFindings(visitId);
  const saveFollowUpMutation = useSaveFollowUpLetter(visitId);
  const overviewLoading =
    !hydrated &&
    (overviewQueryLoading ||
      followUpQueryLoading ||
      findingsQuery.isLoading);

  // Trust the parent's flag too (e.g. when it gets refreshed after a poll).
  useEffect(() => {
    if (isAcknowledgedProp) setLocalAcknowledged(true);
  }, [isAcknowledgedProp]);

  const isAcknowledged = isAcknowledgedProp || localAcknowledged;
  const isReadOnly = isVisitClosed || isAcknowledged;
  const followUpSentAt = localSentAt ?? followUp?.last_sent ?? null;
  const followUpDeliveryStatus = localDeliveryStatus ?? followUp?.delivery_status ?? null;
  const hasFollowUpBeenSent = Boolean(
    followUpSentAt ||
      ["queued", "sent", "delivered"].includes(String(followUpDeliveryStatus ?? "").trim().toLowerCase()),
  );
  const sendDisabled = generating || isSending || overviewLoading || hasFollowUpBeenSent;

  const [form, setForm] = useState<FormData>(() => buildInitialForm(null));
  const [areas, setAreas] = useState<Area[]>(DEFAULT_AREAS);
  /** Monitoring findings from the visit Findings tab — used for §3 in DOCX/PDF only. */
  const [summaryFindingsFromVisitTab, setSummaryFindingsFromVisitTab] = useState<SummaryFindingRow[]>([]);

  // One-shot hydration: when the three feeder queries have all settled
  // (success or error), seed the editable form/areas exactly once.
  // Background refetches MUST NOT re-seed — they'd clobber user edits.
  useEffect(() => {
    if (hydrated) return;
    const allSettled =
      !overviewQueryLoading &&
      !followUpQueryLoading &&
      !findingsQuery.isLoading;
    if (!allSettled) return;

    const overviewData: VisitOverviewPayload | null = overview ?? null;
    const baseForm = buildInitialForm(overviewData);

    if (overviewData?.siteContact?.piEmail) {
      setPiEmail(overviewData.siteContact.piEmail);
    }

    let nextForm: FormData = baseForm;
    let nextAreas: Area[] = DEFAULT_AREAS;

    const draft = followUp;
    if (draft) {
      const rawContent = (draft.content || "").trim();
      const saved = parseSavedDraft(rawContent);
      if (saved) {
        nextForm = { ...baseForm, ...saved.form };
        nextAreas = saved.areas.length ? saved.areas : DEFAULT_AREAS;
      }
      if (draft.ack_status === "acknowledged") {
        setLocalAcknowledged(true);
        setAcknowledgedAt(draft.acknowledged_at ?? null);
      }
      if (draft.last_sent || draft.delivery_status) {
        setLocalSentAt(draft.last_sent ?? null);
        setLocalDeliveryStatus(draft.delivery_status ?? null);
      }
    }

    if (Array.isArray(findingsQuery.data)) {
      setSummaryFindingsFromVisitTab(
        mapVisitFindingsToSummary(findingsQuery.data as MonitoringFinding[]),
      );
    } else {
      setSummaryFindingsFromVisitTab([]);
    }

    setForm(nextForm);
    setAreas(nextAreas);
    setHydrated(true);
  }, [
    hydrated,
    overviewQueryLoading,
    followUpQueryLoading,
    findingsQuery.isLoading,
    overview,
    followUp,
    findingsQuery.data,
  ]);

  // Reset hydration when switching visits so the next visit re-seeds cleanly.
  useEffect(() => {
    setHydrated(false);
    setLocalSentAt(null);
    setLocalDeliveryStatus(null);
  }, [visitId]);

  const set = (key: keyof FormData) => (val: string) => setForm(f => ({ ...f, [key]: val }));
  const setAreaField    = (id: number, key: keyof Area,    val: string) => setAreas(a    => a.map(x => x.id === id ? { ...x, [key]: val } : x));

  const addArea    = () => setAreas(a    => [...a,    { id: Date.now(), name: "", status: "Reviewed" }]);

  const handleSaveDraft = async () => {
    try {
      setSavingDraft(true);
      await saveFollowUpMutation.mutateAsync(serializeDraft({ form, areas }));
      showToast("Draft saved successfully", "success");
    } catch {
      showToast("Failed to save draft", "error");
    } finally {
      setSavingDraft(false);
    }
  };

  const visitFindingsForLetter = (findingsQuery.data as MonitoringFinding[]) ?? [];
  const actionItemCount = mapFindingsToActionItems(visitFindingsForLetter).length;

  const handlePreview = async () => {
    setGenerating(true);
    try {
      const summaryRows = summaryRowsOrPlaceholder(summaryFindingsFromVisitTab);
      const doc = buildDoc({
        ...form,
        areas,
        summaryFindings: summaryRows,
        actionItems: actionItemsOrPlaceholder(mapFindingsToActionItems(visitFindingsForLetter)),
      });
      const blob = await Packer.toBlob(doc);
      setPreviewBlob(blob);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      showToast("Error preparing preview: " + msg, "error");
    } finally {
      setGenerating(false);
    }
  };

  const handleSendToSite = async () => {
    if (hasFollowUpBeenSent) {
      showToast("Follow-up letter has already been sent to the site", "info");
      return;
    }
    if (!piEmail) {
      showToast("No PI email address found for this visit", "error");
      return;
    }
    setIsSending(true);
    try {
      // PDF is now generated server-side (reportlab) and emailed via a
      // background task, so the request returns almost immediately. We send
      // structured form data — no client-side DOCX/PDF build, no upload.
      const { api } = await import("../../../../../lib/api");
      const { data } = await api.post(`/monitor/visits/${visitId}/send-follow-up-letter`, {
        pi_email: piEmail,
        pi_name: form.piName,
        cra_name: form.monitorName,
        form,
        areas,
        findings: summaryRowsOrPlaceholder(summaryFindingsFromVisitTab),
      });

      setLocalSentAt(data?.last_sent ?? new Date().toISOString());
      setLocalDeliveryStatus(data?.delivery_status ?? "Queued");
      setIsSendModalOpen(false);
      showToast(`Follow-up letter sent to ${piEmail}`, "success");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const msg = err.response?.data?.detail ?? err.message ?? String(e);
      if (msg.toLowerCase().includes("already been sent")) {
        setLocalSentAt(new Date().toISOString());
        setLocalDeliveryStatus("Queued");
        setIsSendModalOpen(false);
      }
      showToast("Failed to send follow-up letter: " + msg, "error");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div style={{ minHeight: "100%", background: "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)", fontFamily: "inherit" }}>
      <div style={{ padding: "2rem 1rem 3rem", maxWidth: "900px", margin: "0 auto" }}>

        {isVisitClosed && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "12px 18px", marginBottom: 20,
            background: "#fef3c7", border: "1.5px solid #fcd34d",
            borderRadius: 10, fontSize: 13, fontWeight: 600, color: "#92400e",
          }}>
            🔒 <span>This visit is <strong>closed and locked</strong>. The Follow-up Letter is available for viewing only. No edits can be made.</span>
          </div>
        )}

        {!isVisitClosed && isAcknowledged && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "12px 18px", marginBottom: 20,
            background: "#dcfce7", border: "1.5px solid #86efac",
            borderRadius: 10, fontSize: 13, fontWeight: 600, color: "#14532d",
          }}>
            ✅ <span>
              The site has <strong>acknowledged</strong> this Follow-up Letter
              {acknowledgedAt ? ` on ${new Date(acknowledgedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : ""}.
              The letter is now <strong>locked</strong> and cannot be edited or re-sent.
            </span>
          </div>
        )}

        {overviewLoading && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", background: "#ebf8ff", border: "1.5px solid #bee3f8", borderRadius: "8px", marginBottom: 20, fontSize: 13, color: "#2b6cb0" }}>
            <i className="ti ti-loader-2" style={{ fontSize: 16, animation: "spin 1s linear infinite" }} aria-hidden="true" />
            Loading visit data…
          </div>
        )}

        {/* pointer-events: none blocks ALL browser events on form controls when the visit is closed
            or once the site has acknowledged the letter. More reliable than <fieldset disabled>,
            which React's synthetic event system can bypass. */}
        <div style={isReadOnly ? { pointerEvents: "none", userSelect: "none", opacity: 0.65 } : undefined}>

        {/* Visit Information */}
        <SectionCard title="Visit Information" icon="clipboard" accent="#2E5496">
          <Grid2>
            <Field label="Letter Date" value={form.letterDate} onChange={set("letterDate")} type="date" required />
            <Field label="Visit Date" value={form.visitDate} onChange={set("visitDate")} type="date" required />
            <Field label="Study Title" value={form.studyTitle} onChange={set("studyTitle")} required />
            <Field label="Protocol Number" value={form.protocolNumber} onChange={set("protocolNumber")} required />
            <Field label="Total Subjects Reviewed" value={form.totalSubjects} onChange={set("totalSubjects")} type="number" />
            <Field label="Ongoing Subjects" value={form.ongoingSubjects} onChange={set("ongoingSubjects")} type="number" />
          </Grid2>
        </SectionCard>

        {/* Site & Investigator */}
        <SectionCard title="Site & Investigator" icon="building-hospital" accent="#2E5496">
          <Grid2>
            <Field label="Site Name / Hospital" value={form.siteName} onChange={set("siteName")} required />
            <Field label="Principal Investigator" value={form.piName} onChange={set("piName")} hint="Include title e.g. Dr. Sharma" required />
          </Grid2>
          <Field label="Site Address" value={form.siteAddress} onChange={set("siteAddress")} />
        </SectionCard>

        {/* Monitor & Sponsor */}
        <SectionCard title="Monitor & Sponsor" icon="user-check" accent="#0F6E56">
          <Grid2>
            <Field label="Monitor Name" value={form.monitorName} onChange={set("monitorName")} required />
            <Field label="Monitor Email" value={form.monitorEmail} onChange={set("monitorEmail")} type="email" required />
            <Field label="Sponsor Name" value={form.sponsorName} onChange={set("sponsorName")} required />
            <Field label="Sponsor / CRO Contact" value={form.sponsorContact} onChange={set("sponsorContact")} hint="Name, Role, Company" />
          </Grid2>
        </SectionCard>

        {/* Areas Reviewed */}
        <SectionCard title="Areas Reviewed" icon="checklist" accent="#854F0B">
          {areas.map((a, i) => (
            <div key={a.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 12, alignItems: "end", marginBottom: 12, padding: "14px", background: "#f7fafc", borderRadius: "8px", border: "1px solid #e2e8f0", transition: "all 0.3s" }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#fff"; (e.currentTarget as HTMLDivElement).style.borderColor = "#cbd5e0"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#f7fafc"; (e.currentTarget as HTMLDivElement).style.borderColor = "#e2e8f0"; }}>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "#4a5568", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>Area {i + 1}</label>
                <input value={a.name} onChange={e => setAreaField(a.id, "name", e.target.value)}
                  style={{ width: "100%", boxSizing: "border-box", fontSize: 14, padding: "8px 10px", border: "1px solid #e2e8f0", borderRadius: "6px", outline: "none", transition: "all 0.3s" }}
                  onFocus={(e) => { e.target.style.borderColor = "#667eea"; e.target.style.boxShadow = "0 0 0 2px rgba(102, 126, 234, 0.1)"; }}
                  onBlur={(e) => { e.target.style.borderColor = "#e2e8f0"; e.target.style.boxShadow = "none"; }}
                  placeholder="Area name" />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, color: "#4a5568", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>Status</label>
                <select value={a.status} onChange={e => setAreaField(a.id, "status", e.target.value)}
                  style={{ width: "100%", fontSize: 14, padding: "8px 10px", border: "1px solid #e2e8f0", borderRadius: "6px", outline: "none", cursor: "pointer", transition: "all 0.3s" }}
                  onFocus={(e) => { e.target.style.borderColor = "#667eea"; e.target.style.boxShadow = "0 0 0 2px rgba(102, 126, 234, 0.1)"; }}
                  onBlur={(e) => { e.target.style.borderColor = "#e2e8f0"; e.target.style.boxShadow = "none"; }}>
                  {AREA_STATUSES.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
              <RemoveBtn onClick={() => setAreas(arr => arr.filter(x => x.id !== a.id))} />
            </div>
          ))}
          <AddBtn onClick={addArea} label="Add Area" />
        </SectionCard>

        {/* Resolution Timelines */}
        <SectionCard title="Resolution Timelines" icon="clock" accent="#533AB9">
          {([
            { label: "Critical", tKey: "criticalTimeline" as const, eKey: "criticalEscalation" as const, color: "#A32D2D" },
            { label: "Major",    tKey: "majorTimeline"    as const, eKey: "majorEscalation"    as const, color: "#854F0B" },
            { label: "Minor",    tKey: "minorTimeline"    as const, eKey: "minorEscalation"    as const, color: "#3B6D11" },
          ]).map(row => (
            <div key={row.label} style={{ padding: "14px 16px", background: `${row.color}08`, borderRadius: "8px", border: `1.5px solid ${row.color}30`, borderLeft: `4px solid ${row.color}`, marginBottom: 14 }}>
              <p style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 700, color: row.color }}>{row.label}</p>
              <Grid2>
                <Field label="Response Timeline" value={form[row.tKey]} onChange={set(row.tKey)} />
                <Field label="Escalation Timeline" value={form[row.eKey]} onChange={set(row.eKey)} />
              </Grid2>
            </div>
          ))}
        </SectionCard>

        </div>{/* end read-only form wrapper */}

        {/* Review & Generate */}
        <SectionCard title="Review & Generate" icon="file-download" accent="#2E5496">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 20 }}>
            {[
              { label: "Study Title",  val: form.studyTitle },
              { label: "Protocol",     val: form.protocolNumber },
              { label: "Site",         val: form.siteName },
              { label: "Site Address", val: form.siteAddress },
              { label: "PI",           val: form.piName },
              { label: "Visit Date",   val: form.visitDate },
            ].map(item => (
              <div key={item.label} style={{ background: "#f7fafc", padding: "12px 14px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, fontSize: 11, color: "#718096", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>{item.label}</p>
                <p style={{ margin: "6px 0 0", fontSize: 14, fontWeight: 600, color: "#2d3748" }}>
                  {item.val || <span style={{ color: "#a0aec0", fontStyle: "italic" }}>—</span>}
                </p>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
            {([
              ["Areas", areas.length, "#854F0B"],
              ["Findings", summaryFindingsFromVisitTab.length, "#A32D2D"],
              ["Action items", actionItemCount, "#185FA5"],
            ] as [string, number, string][]).map(([label, n, color]) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--color-text-secondary)" }}>
                <StatBadge n={n} color={color} /> {label}
              </div>
            ))}
          </div>

          <button
            onClick={() => void handleSaveDraft()}
            disabled={isReadOnly || savingDraft || overviewLoading}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              padding: "10px 20px",
              marginBottom: 10,
              background: savingDraft ? "#cbd5e0" : "#ffffff",
              color: savingDraft ? "#4a5568" : "#4c51bf",
              border: "1.5px solid #667eea",
              borderRadius: "8px",
              fontSize: 14,
              fontWeight: 600,
              cursor: savingDraft || overviewLoading ? "not-allowed" : "pointer",
              transition: "all 0.3s",
              width: "100%",
            }}
          >
            <i className={`ti ti-${savingDraft ? "loader-2" : "device-floppy"}`} style={{ fontSize: 16, animation: savingDraft ? "spin 1s linear infinite" : "none" }} aria-hidden="true" />
            {savingDraft ? "Saving draft..." : "Save Draft"}
          </button>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <button onClick={() => void handlePreview()} disabled={generating || isSending}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "12px 16px", background: generating ? "#cbd5e0" : "linear-gradient(135deg, #667eea 0%, #764ba2 100%)", color: "#fff", border: "none", borderRadius: "8px", fontSize: 14, fontWeight: 600, cursor: generating || isSending ? "not-allowed" : "pointer", transition: "all 0.3s", boxShadow: "0 4px 15px rgba(102, 126, 234, 0.4)" }}
              onMouseEnter={(e) => { if (!generating && !isSending) (e.currentTarget).style.boxShadow = "0 8px 25px rgba(102, 126, 234, 0.6)"; }}
              onMouseLeave={(e) => { (e.currentTarget).style.boxShadow = "0 4px 15px rgba(102, 126, 234, 0.4)"; }}>
              <i className={`ti ti-${generating ? "loader-2" : "eye"}`} style={{ fontSize: 16, animation: generating ? "spin 1s linear infinite" : "none" }} aria-hidden="true" />
              {generating ? "Generating..." : "Preview Letter"}
            </button>

            {!isReadOnly && <button onClick={() => setIsSendModalOpen(true)} disabled={sendDisabled}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "12px 16px", background: sendDisabled ? "#cbd5e0" : "linear-gradient(135deg, #0F6E56 0%, #1a9e7a 100%)", color: "#fff", border: "none", borderRadius: "8px", fontSize: 14, fontWeight: 600, cursor: sendDisabled ? "not-allowed" : "pointer", transition: "all 0.3s", boxShadow: sendDisabled ? "none" : "0 4px 15px rgba(15, 110, 86, 0.4)" }}
              onMouseEnter={(e) => { if (!sendDisabled) (e.currentTarget).style.boxShadow = "0 8px 25px rgba(15, 110, 86, 0.6)"; }}
              onMouseLeave={(e) => { (e.currentTarget).style.boxShadow = "0 4px 15px rgba(15, 110, 86, 0.4)"; }}>
              <i className={`ti ti-${hasFollowUpBeenSent ? "check" : "send"}`} style={{ fontSize: 16 }} aria-hidden="true" />
              {hasFollowUpBeenSent ? "Sent to Site" : "Send to Site"}
            </button>}
          </div>

          {hasFollowUpBeenSent && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#15803d", textAlign: "center", fontWeight: 600 }}>
              Follow-up letter already sent
              {followUpSentAt ? ` on ${new Date(followUpSentAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : ""}.
            </p>
          )}
          {piEmail && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#718096", textAlign: "center" }}>
              {hasFollowUpBeenSent ? "Sent to" : "Will be sent to"}: <strong style={{ color: "#2d3748" }}>{piEmail}</strong>
            </p>
          )}
          {!piEmail && !overviewLoading && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#e53e3e", textAlign: "center" }}>
              No PI email on record — update site contact to enable sending.
            </p>
          )}
        </SectionCard>
      </div>

      {previewBlob && (
        <DocxPreviewModal
          blob={previewBlob}
          fileName="Site_FollowUp_Letter.docx"
          onClose={() => setPreviewBlob(null)}
        />
      )}

      {isSendModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          style={{ position: "fixed", inset: 0, zIndex: 2000, background: "rgba(15, 23, 42, 0.65)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}
        >
          <div style={{ background: "#fff", borderRadius: 12, boxShadow: "0 20px 60px rgba(2,6,23,0.25)", width: "100%", maxWidth: 460, overflow: "hidden" }}>
            {/* Header */}
            <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 8, background: "#0F6E5614", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <i className="ti ti-send" style={{ fontSize: 20, color: "#0F6E56" }} aria-hidden="true" />
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Confirm Send to Site</div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>This action will email the PDF to the PI</div>
              </div>
            </div>

            {/* Body */}
            <div style={{ padding: "20px" }}>
              <p style={{ margin: 0, fontSize: 14, color: "#334155", lineHeight: 1.6 }}>
                Are you sure you want to send the <strong>Follow-up Letter</strong> as a PDF to the Principal Investigator?
              </p>
              {piEmail && (
                <div style={{ marginTop: 14, padding: "10px 14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, display: "flex", alignItems: "center", gap: 8 }}>
                  <i className="ti ti-mail" style={{ fontSize: 16, color: "#16a34a" }} aria-hidden="true" />
                  <span style={{ fontSize: 13, color: "#15803d", fontWeight: 500 }}>{piEmail}</span>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ padding: "12px 20px 16px", borderTop: "1px solid #e2e8f0", display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                onClick={() => setIsSendModalOpen(false)}
                disabled={isSending}
                style={{ padding: "9px 18px", border: "1px solid #cbd5e1", background: "#fff", color: "#475569", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: isSending ? "not-allowed" : "pointer" }}
              >
                Cancel
              </button>
              <button
                onClick={() => void handleSendToSite()}
                disabled={isSending || hasFollowUpBeenSent}
                style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 20px", background: isSending || hasFollowUpBeenSent ? "#cbd5e0" : "linear-gradient(135deg, #0F6E56 0%, #1a9e7a 100%)", color: "#fff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: isSending || hasFollowUpBeenSent ? "not-allowed" : "pointer", boxShadow: isSending || hasFollowUpBeenSent ? "none" : "0 4px 12px rgba(15,110,86,0.35)" }}
              >
                <i className={`ti ti-${isSending ? "loader-2" : hasFollowUpBeenSent ? "check" : "send"}`} style={{ fontSize: 15, animation: isSending ? "spin 1s linear infinite" : "none" }} aria-hidden="true" />
                {isSending ? "Sending..." : hasFollowUpBeenSent ? "Already Sent" : "Confirm & Send"}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
