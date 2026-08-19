import { useEffect, useMemo, useRef, type ElementType, type ReactNode } from "react";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  CalendarDays,
  ClipboardCheck,
  Clock3,
  FileCheck2,
  FileWarning,
  Flag,
  Gauge,
  PackageCheck,
  SearchCheck,
  ShieldAlert,
  ShieldCheck,
  Target,
  Users,
} from "lucide-react";
import { useMarkPreVisitReviewed } from "@/lib/queries/useMonitoring";
import { useVisitWorkflow } from "../../../context/VisitWorkflowContext";
import { findingIdForDisplay } from "../../../services/monitorService";
import type { Finding } from "../../../types";
import { extractApiErrorMessage } from "../../../utils/apiError";

type Tone = "red" | "amber" | "green" | "blue" | "teal" | "slate" | "purple";

type FollowUpFinding = {
  id: string;
  visitDate: string;
  category: string;
  severity: string;
  description: string;
  status: string;
  age: string;
};

type CapaRow = {
  id: string;
  finding: string;
  description: string;
  responsible: string;
  dueDate: string;
  status: string;
  age: string;
};

type SubjectRow = {
  subject: string;
  currentVisit: string;
  sdvStatus: string;
  queries: string;
  protocolDeviation: string;
  sae: string;
  priority: Tone;
};

type InsightCard = {
  title: string;
  detail: string;
  tone: Tone;
};

type PriorityPlanItem = {
  title: string;
  detail: string;
  icon: ElementType;
  tone: Tone;
  badge: string;
};

type RiskCellModel = {
  title: string;
  subtitle: string;
  tone: Tone;
};

type ReviewLine = {
  label: string;
  value: ReactNode;
  tone: Tone;
};

const toneClasses: Record<Tone, { text: string; bg: string; border: string; dot: string; soft: string }> = {
  red: {
    text: "text-red-700",
    bg: "bg-red-50",
    border: "border-red-200",
    dot: "bg-red-500",
    soft: "bg-red-100 text-red-700",
  },
  amber: {
    text: "text-amber-700",
    bg: "bg-amber-50",
    border: "border-amber-200",
    dot: "bg-amber-500",
    soft: "bg-amber-100 text-amber-800",
  },
  green: {
    text: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    dot: "bg-emerald-500",
    soft: "bg-emerald-100 text-emerald-800",
  },
  blue: {
    text: "text-blue-700",
    bg: "bg-blue-50",
    border: "border-blue-200",
    dot: "bg-blue-500",
    soft: "bg-blue-100 text-blue-700",
  },
  teal: {
    text: "text-teal-700",
    bg: "bg-teal-50",
    border: "border-teal-200",
    dot: "bg-teal-500",
    soft: "bg-teal-100 text-teal-800",
  },
  slate: {
    text: "text-slate-700",
    bg: "bg-slate-50",
    border: "border-slate-200",
    dot: "bg-slate-400",
    soft: "bg-slate-100 text-slate-700",
  },
  purple: {
    text: "text-violet-700",
    bg: "bg-violet-50",
    border: "border-violet-200",
    dot: "bg-violet-500",
    soft: "bg-violet-100 text-violet-700",
  },
};

function joinClasses(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function parseCountPair(text: string | null | undefined) {
  if (!text) return null;
  const matches = String(text).match(/\d+/g)?.map(Number) ?? [];
  if (matches.length >= 2) return { current: matches[0], target: matches[1] };
  if (matches.length === 1) return { current: matches[0], target: 25 };
  return null;
}

function parseDate(value: string | null | undefined) {
  const raw = String(value || "").trim();
  if (!raw || raw.toUpperCase() === "TBD") return null;

  const isoDate = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|T)/);
  if (isoDate) {
    const parsedIso = new Date(Number(isoDate[1]), Number(isoDate[2]) - 1, Number(isoDate[3]));
    if (!Number.isNaN(parsedIso.getTime())) return parsedIso;
  }

  const monthDay = raw.match(/^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
  if (monthDay) {
    const [, month, day, year] = monthDay;
    const parsedMonthDay = new Date(`${month} ${day}, ${year || new Date().getFullYear()}`);
    if (!Number.isNaN(parsedMonthDay.getTime())) return parsedMonthDay;
  }

  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) return parsed;
  return null;
}

function formatDate(value: string | Date | null | undefined, fallback = "TBD", includeYear = true) {
  const date = value instanceof Date ? value : parseDate(value);
  if (!date) return fallback;
  const year = includeYear ? "numeric" : "2-digit";
  return date
    .toLocaleDateString("en-GB", { day: "2-digit", month: "short", year })
    .replace(/ /g, "-");
}

function startOfDay(date: Date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function daysBetween(from: Date, to = new Date()) {
  const ms = startOfDay(to).getTime() - startOfDay(from).getTime();
  return Math.max(1, Math.round(ms / 86_400_000));
}

function formatVisitCode(value: number | string | null | undefined) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `MV-${String(value).padStart(2, "0")}`;
  }
  const text = String(value || "").trim();
  if (!text) return "Current visit";
  const numeric = Number(text);
  if (Number.isFinite(numeric)) return `MV-${String(numeric).padStart(2, "0")}`;
  return text.length > 12 ? `MV-${text.slice(-4).toUpperCase()}` : `MV-${text}`;
}

function normalizeStatus(status: string | null | undefined) {
  return String(status || "").trim().toLowerCase();
}

function isFindingOpen(finding: Finding) {
  const status = normalizeStatus(finding.status);
  return status !== "resolved" && status !== "archived" && status !== "closed";
}

function isOverdueFinding(finding: Finding) {
  if (finding.isOverdue) return true;
  const status = normalizeStatus(finding.status);
  if (status.includes("overdue")) return true;
  const due = parseDate(finding.dueDate);
  return Boolean(due && startOfDay(due).getTime() < startOfDay(new Date()).getTime() && isFindingOpen(finding));
}

function ageForFinding(finding: Finding, fallback = "Not dated") {
  const due = parseDate(finding.dueDate);
  if (!due) return fallback;
  const today = startOfDay(new Date());
  const dueDay = startOfDay(due);
  if (dueDay.getTime() === today.getTime()) return "Due today";
  if (dueDay.getTime() > today.getTime()) return `Due in ${daysBetween(today, dueDay)}d`;
  return `${daysBetween(due)}d`;
}

function toneForSeverity(severity: string | null | undefined): Tone {
  const s = normalizeStatus(severity);
  if (s.includes("critical")) return "red";
  if (s.includes("major") || s.includes("high")) return "amber";
  if (s.includes("minor") || s.includes("medium")) return "blue";
  return "green";
}

function toneForRisk(risk: string | null | undefined): Tone {
  const r = normalizeStatus(risk);
  if (r.includes("high") || r.includes("critical")) return "red";
  if (r.includes("medium") || r.includes("moderate")) return "amber";
  if (r.includes("low")) return "green";
  return "slate";
}

function riskLabel(tone: Tone) {
  if (tone === "red") return "High";
  if (tone === "amber") return "Med";
  if (tone === "green") return "Low";
  return "Info";
}

function avgFindingAge(findingsForAge: Finding[]) {
  if (!findingsForAge.length) return 0;
  const total = findingsForAge.reduce((sum, finding) => {
    const numeric = Number(ageForFinding(finding, "0d").replace(/\D/g, "") || 0);
    return sum + numeric;
  }, 0);
  return Math.round(total / findingsForAge.length);
}

function findingText(finding: Finding) {
  return `${finding.category || ""} ${finding.description || ""} ${finding.reference || ""}`.trim();
}

function isQueryFinding(finding: Finding) {
  const text = findingText(finding).toLowerCase();
  return text.includes("query") || text.includes("data") || text.includes("missing") || text.includes("discrep");
}

function isSafetyFinding(finding: Finding) {
  const text = findingText(finding).toLowerCase();
  return text.includes("safety") || text.includes("sae") || text.includes("ae ") || text.includes("adverse");
}

function isIpFinding(finding: Finding) {
  const text = findingText(finding).toLowerCase();
  return text.includes("pharmacy") || text.includes("drug") || text.includes(" ip ") || text.includes("kit") || text.includes("shipment");
}

function extractSubjectId(finding: Finding) {
  const explicit = finding.subjectId?.trim();
  if (explicit) return explicit;
  const match = findingText(finding).match(/\b(?:subject|subj|sbj)\s*[-#: ]?\s*([A-Za-z0-9-]+)/i);
  return match?.[1] ?? null;
}

function conciseFindingTitle(finding: Finding, visitId: string) {
  const id = findingIdForDisplay(finding.id, visitId);
  const category = finding.category || "Finding";
  return `${id} - ${category}`;
}

function topByCount(entries: Map<string, number>, limit = 3) {
  return [...entries.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

function StatusPill({ children, tone = "slate" }: { children: ReactNode; tone?: Tone }) {
  const t = toneClasses[tone];
  return (
    <span className={joinClasses("inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold", t.soft)}>
      {children}
    </span>
  );
}

function DotLabel({
  children,
  tone = "slate",
  value,
}: {
  children: ReactNode;
  tone?: Tone;
  value?: ReactNode;
}) {
  const t = toneClasses[tone];
  return (
    <div className="flex items-center justify-between gap-3 text-xs text-slate-600">
      <span className="flex min-w-0 items-center gap-2">
        <span className={joinClasses("h-2 w-2 shrink-0 rounded-full", t.dot)} />
        <span className="truncate">{children}</span>
      </span>
      {value !== undefined && <span className="shrink-0 font-semibold text-slate-700">{value}</span>}
    </div>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  right,
}: {
  icon?: ElementType;
  title: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-slate-500" strokeWidth={1.8} />}
        <h3 className="text-sm font-bold uppercase text-slate-600">{title}</h3>
      </div>
      {right}
    </div>
  );
}

function CommandBadge({
  icon: Icon,
  children,
  tone = "slate",
}: {
  icon?: ElementType;
  children: ReactNode;
  tone?: Tone;
}) {
  const t = toneClasses[tone];
  return (
    <span className={joinClasses("inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold", t.bg, t.border, t.text)}>
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.8} />}
      {children}
    </span>
  );
}

function MetricTile({
  label,
  value,
  tone = "slate",
  sub,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  sub?: string;
}) {
  const t = toneClasses[tone];
  return (
    <div className="min-h-[74px] rounded-md bg-stone-50 px-3 py-3">
      <div className="text-[11px] font-semibold text-slate-500">{label}</div>
      <div className={joinClasses("mt-1 text-2xl font-bold leading-none", t.text)}>{value}</div>
      {sub && <div className="mt-1 text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function KpiCard({
  icon: Icon,
  title,
  badge,
  children,
}: {
  icon: ElementType;
  title: string;
  badge: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-card">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-slate-500" strokeWidth={1.8} />
          <h4 className="text-sm font-bold text-slate-800">{title}</h4>
        </div>
        {badge}
      </div>
      {children}
    </div>
  );
}

function RiskCell({
  title,
  subtitle,
  tone,
}: {
  title: string;
  subtitle: string;
  tone: Tone;
}) {
  const t = toneClasses[tone];
  return (
    <div className={joinClasses("rounded-md border px-3 py-2", t.bg, t.border)}>
      <div className={joinClasses("text-sm font-bold", t.text)}>{title}</div>
      <div className="mt-1 text-[11px] text-slate-600">{subtitle}</div>
    </div>
  );
}

function MiniTable({
  columns,
  children,
}: {
  columns: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            {columns.map((column) => (
              <th key={column} className="whitespace-nowrap border-b border-slate-200 px-3 py-2 font-bold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">{children}</tbody>
      </table>
    </div>
  );
}

function PriorityItem({
  icon: Icon,
  title,
  detail,
  tone,
  badge,
}: {
  icon: ElementType;
  title: string;
  detail: string;
  tone: Tone;
  badge: string;
}) {
  const t = toneClasses[tone];
  return (
    <div className="flex gap-3 border-b border-slate-100 py-3 last:border-b-0">
      <div className={joinClasses("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", t.bg)}>
        <Icon className={joinClasses("h-4 w-4", t.text)} strokeWidth={1.8} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-bold text-slate-800">{title}</div>
          <StatusPill tone={tone}>{badge}</StatusPill>
        </div>
        <p className="mt-1 text-xs text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

export function PreVisitTab({
  visitId,
  showToast,
  onOpenCountChange,
  isVisitClosed = false,
  preVisitReportStatus,
  preVisitReviewedAt,
  onPreVisitReportStatusChange,
  onPreVisitReviewedChange,
  siteIdForPrimaryStatus,
}: {
  visitId: string;
  showToast: (msg: string, type?: string) => void;
  onOpenCountChange?: (count: number) => void;
  isVisitClosed?: boolean;
  preVisitReportStatus?: string;
  preVisitReviewedAt?: string | null;
  onPreVisitReportStatusChange?: (status: string) => void;
  onPreVisitReviewedChange?: (reviewedAt: string | null) => void;
  onPreVisitReportSent?: () => void;
  siteIdForPrimaryStatus?: string | null;
  siteIrbSummary?: string | null;
}) {
  const followUpRef = useRef<HTMLDivElement | null>(null);

  const { preVisit, overview } = useVisitWorkflow();
  const markPreVisitReviewedMutation = useMarkPreVisitReviewed(visitId);
  const previousVisit = preVisit?.previousVisit ?? null;
  const previousOpenFindings = previousVisit?.openFindings ?? [];
  const currentPreVisitStatus = String(preVisitReportStatus || preVisit?.preVisitReportStatus || "DRAFT").trim().toUpperCase();
  const currentPreVisitReviewedAt = preVisitReviewedAt || preVisit?.preVisitReviewedAt || null;
  const isPreVisitReviewed =
    Boolean(currentPreVisitReviewedAt) ||
    currentPreVisitStatus === "ACKNOWLEDGED" ||
    currentPreVisitStatus === "REVIEWED";

  const visitDetails = overview?.visitDetails;
  const siteContact = overview?.siteContact;
  const liveSdv = overview?.sdvProgress;
  const rawVisitDate = visitDetails?.visitDateIso || visitDetails?.visitDate;
  const visitSeq = visitDetails?.siteVisitNumber ?? (Number.isFinite(Number(visitId)) ? Number(visitId) : null);
  const findings = previousOpenFindings;
  const sdv = liveSdv;
  const visitCode = formatVisitCode(visitSeq);
  const previousVisitCode = previousVisit?.label || "";
  const visitDateForDisplay = formatDate(rawVisitDate, visitDetails?.visitDate || "TBD");
  const previousVisitDate = previousVisit?.visitDate || "";
  const previousVisitHeading = previousVisitCode
    ? `Previous Visit Follow-Up - ${previousVisitCode} (${previousVisitDate || "Not recorded"}) - Mandatory Pre-Visit Review`
    : "Previous Visit Follow-Up - Mandatory Pre-Visit Review";

  const enrollment = useMemo(() => {
    const pair = parseCountPair(sdv?.subjectsEnrolled);
    const target = pair?.target ?? sdv?.totalSubjects ?? 0;
    const randomised = pair?.current ?? sdv?.verifiedSubjects ?? 0;
    const screened = pair?.current ?? sdv?.totalSubjects ?? randomised;
    const active = Math.max(Math.min(randomised, sdv?.verifiedSubjects ?? randomised), 0);
    const percent = clampPercent((randomised / Math.max(target, 1)) * 100);
    return { target, randomised, screened, active, percent };
  }, [sdv?.subjectsEnrolled, sdv?.totalSubjects, sdv?.verifiedSubjects]);

  const openFindings = useMemo(() => findings.filter(isFindingOpen), [findings]);
  const criticalOpenFindings = useMemo(
    () => openFindings.filter((finding) => normalizeStatus(finding.severity).includes("critical")),
    [openFindings],
  );
  const overdueFindings = useMemo(() => openFindings.filter(isOverdueFinding), [openFindings]);
  const riskLevel =
    visitDetails?.riskLevel ||
    (criticalOpenFindings.length ? "High" : overdueFindings.length || openFindings.length ? "Medium" : "Low");
  const riskTone = toneForRisk(riskLevel);

  const followUpFindings = useMemo<FollowUpFinding[]>(() => {
    return openFindings.slice(0, 6).map((finding, index) => ({
      id: findingIdForDisplay(finding.id, visitId),
      visitDate: previousVisitDate,
      category: finding.category || "Monitoring",
      severity: finding.severity || "Major",
      description: finding.description || "Open follow-up item",
      status: isOverdueFinding(finding) ? "Overdue" : finding.status || "Open",
      age: ageForFinding(finding, index === 0 ? "Open" : "Not dated"),
    }));
  }, [openFindings, previousVisitDate, visitId]);

  const capaRows = useMemo<CapaRow[]>(() => {
    const rows = openFindings.flatMap((finding, findingIndex) => {
      const actions = finding.actionItems?.length
        ? finding.actionItems
        : finding.resolution
          ? [{
              assignee: finding.assignee,
              dueDate: finding.dueDate,
              resolution: finding.resolution,
            }]
          : [];
      return actions.map((action, actionIndex) => ({
        id: `CAPA-${String(11 + findingIndex + actionIndex).padStart(2, "0")}`,
        finding: findingIdForDisplay(finding.id, visitId),
        description: action.resolution || finding.resolution || `Resolve ${finding.category || "monitoring"} finding`,
        responsible: action.assignee?.name || finding.assignee?.name || "Unassigned",
        dueDate: formatDate(action.dueDate || finding.dueDate, "TBD"),
        status: isOverdueFinding(finding) ? "Overdue" : "In progress",
        age: ageForFinding(finding),
      }));
    });
    return rows.slice(0, 5);
  }, [openFindings, visitId]);

  const queryMetrics = useMemo(() => {
    const dataFindings = openFindings.filter(isQueryFinding);
    const overdueQueryFindings = dataFindings.filter(isOverdueFinding);
    const domainCounts = new Map<string, number>();
    dataFindings.forEach((finding) => {
      const label = finding.category || "Data / query";
      domainCounts.set(label, (domainCounts.get(label) ?? 0) + 1);
    });
    const domains = topByCount(domainCounts).map(([label, value], index) => ({
      label,
      value,
      tone: (index === 0 && overdueQueryFindings.length ? "red" : index === 1 ? "amber" : "blue") as Tone,
    }));
    return {
      total: dataFindings.length,
      open: dataFindings.length,
      overdue: overdueQueryFindings.length,
      avgAge: avgFindingAge(overdueQueryFindings),
      domains,
    };
  }, [openFindings]);

  const capaMetrics = useMemo(() => {
    const openCapas = capaRows.filter((row) => normalizeStatus(row.status) !== "resolved").length;
    const overdueCapas = capaRows.filter((row) => normalizeStatus(row.status).includes("overdue")).length;
    const openFindingCount = openFindings.length;
    const criticalCount = criticalOpenFindings.length;
    const closure = findings.length ? clampPercent(((findings.length - openFindings.length) / Math.max(findings.length, 1)) * 100) : 100;
    return { openCapas, overdueCapas, openFindingCount, criticalCount, closure };
  }, [capaRows, criticalOpenFindings.length, findings.length, openFindings.length]);

  const sdvMetrics = useMemo(() => {
    const percent = clampPercent(sdv?.percent ?? 0);
    const total = sdv?.totalSubjects ?? 0;
    const verified = sdv?.verifiedSubjects ?? 0;
    const pending = Math.max(total - verified, 0);
    const sdrComplete = verified;
    const highPriority = criticalOpenFindings.length;
    return { percent, pending, sdrComplete, highPriority, verified };
  }, [criticalOpenFindings.length, sdv?.percent, sdv?.totalSubjects, sdv?.verifiedSubjects]);

  const subjectRows = useMemo<SubjectRow[]>(() => {
    const bySubject = new Map<string, Finding[]>();
    openFindings.forEach((finding) => {
      const subject = extractSubjectId(finding);
      if (!subject) return;
      const existing = bySubject.get(subject) ?? [];
      existing.push(finding);
      bySubject.set(subject, existing);
    });
    return [...bySubject.entries()]
      .map(([subject, subjectFindings]) => {
        const critical = subjectFindings.some((finding) => normalizeStatus(finding.severity).includes("critical"));
        const major = subjectFindings.some((finding) => normalizeStatus(finding.severity).includes("major"));
        const queries = subjectFindings.filter(isQueryFinding).length;
        const protocolFinding = subjectFindings.find((finding) => normalizeStatus(finding.category).includes("protocol"));
        const safetyFinding = subjectFindings.find(isSafetyFinding);
        const firstFinding = subjectFindings[0];
        const priority: Tone = critical ? "red" : major || queries > 0 ? "amber" : "green";
        return {
          subject,
          currentVisit: firstFinding.reference || "Current visit",
          sdvStatus: critical ? "Critical" : subjectFindings.length ? "Pending" : "Complete",
          queries: `${queries} open`,
          protocolDeviation: protocolFinding?.reference || (protocolFinding ? "Open" : "None"),
          sae: safetyFinding ? "Yes" : "No",
          priority,
        };
      })
      .sort((a, b) => {
        const order: Record<Tone, number> = { red: 0, amber: 1, blue: 2, purple: 3, teal: 4, slate: 5, green: 6 };
        return order[a.priority] - order[b.priority];
      })
      .slice(0, 10);
  }, [openFindings]);

  const prepOpenCount = criticalOpenFindings.length + overdueFindings.length;

  const carryOverItems = useMemo(() => {
    if (followUpFindings.length) {
      return followUpFindings.slice(0, 3).map((finding) => {
        const ageText = finding.age === "Open" || finding.age === "Not dated" ? finding.status : `${finding.age} ${finding.status.toLowerCase()}`;
        return `${finding.description} (${finding.id}, ${ageText})`;
      });
    }
    return ["No unresolved carry-over items in the available pre-visit data."];
  }, [followUpFindings]);

  const carryOverAlertTone: Tone = criticalOpenFindings.length || overdueFindings.length ? "red" : "green";
  const carryOverHeadline =
    criticalOpenFindings.length > 0
      ? `${criticalOpenFindings.length} critical carry-over item${criticalOpenFindings.length === 1 ? "" : "s"} require immediate attention`
      : overdueFindings.length > 0
        ? `${overdueFindings.length} overdue carry-over item${overdueFindings.length === 1 ? "" : "s"} require review`
        : "No critical carry-over items found in available data";

  const sdvAttentionRows = useMemo(
    () => subjectRows.filter((row) => row.priority !== "green").slice(0, 3),
    [subjectRows],
  );

  const repeatFindingCards = useMemo<InsightCard[]>(() => {
    const categoryCounts = new Map<string, number>();
    openFindings.forEach((finding) => {
      const category = finding.category || "Uncategorised finding";
      categoryCounts.set(category, (categoryCounts.get(category) ?? 0) + 1);
    });
    const repeatedCategories = topByCount(categoryCounts)
      .filter(([, count]) => count > 1)
      .map(([category, count]) => ({
        title: `${category} repeated across ${count} open findings`,
        detail: openFindings
          .filter((finding) => (finding.category || "Uncategorised finding") === category)
          .slice(0, 4)
          .map((finding) => findingIdForDisplay(finding.id, visitId))
          .join(", "),
        tone: "amber" as Tone,
      }));
    if (queryMetrics.open > 1) {
      repeatedCategories.push({
        title: `Data/query pattern across ${queryMetrics.open} open findings`,
        detail: queryMetrics.domains.length
          ? queryMetrics.domains.map((domain) => `${domain.label}: ${domain.value}`).join(" | ")
          : "Open findings include data or query language.",
        tone: queryMetrics.overdue ? "red" : "amber",
      });
    }
    return repeatedCategories.slice(0, 3);
  }, [openFindings, queryMetrics.domains, queryMetrics.open, queryMetrics.overdue, visitId]);

  const escalatedIssueCards = useMemo<InsightCard[]>(() => {
    const cards: InsightCard[] = overdueFindings.slice(0, 2).map((finding) => ({
      title: `${conciseFindingTitle(finding, visitId)} is overdue`,
      detail: `${finding.description || "Open finding"}${finding.assignee?.name ? ` | Owner: ${finding.assignee.name}` : ""}`,
      tone: normalizeStatus(finding.severity).includes("critical") ? "red" : "amber",
    }));
    if (enrollment.target > 0 && enrollment.percent < 80) {
      cards.push({
        title: `Enrollment below target (${enrollment.percent}%)`,
        detail: `${enrollment.randomised}/${enrollment.target} randomised. Discuss acceleration plan with PI/site team.`,
        tone: enrollment.percent < 50 ? "red" : "amber",
      });
    }
    return cards.slice(0, 4);
  }, [enrollment.percent, enrollment.randomised, enrollment.target, overdueFindings, visitId]);

  const safetyFindings = useMemo(() => openFindings.filter(isSafetyFinding), [openFindings]);
  const ipFindings = useMemo(() => openFindings.filter(isIpFinding), [openFindings]);

  const riskCells = useMemo<RiskCellModel[]>(() => {
    const enrollmentTone: Tone = enrollment.target === 0 ? "slate" : enrollment.percent < 50 ? "red" : enrollment.percent < 80 ? "amber" : "green";
    const sdvTone: Tone = sdvMetrics.percent < 60 ? "red" : sdvMetrics.percent < 80 ? "amber" : "green";
    const queryTone: Tone = queryMetrics.overdue ? "red" : queryMetrics.open ? "amber" : "green";
    const capaTone: Tone = capaMetrics.overdueCapas ? "red" : capaMetrics.openCapas ? "amber" : "green";
    const safetyTone: Tone = safetyFindings.length ? "amber" : "green";
    return [
      { title: riskLabel(queryTone), subtitle: `Query/data aging (${queryMetrics.overdue} overdue)`, tone: queryTone },
      { title: riskLabel(enrollmentTone), subtitle: enrollment.target ? `Enrollment ${enrollment.percent}%` : "Enrollment not available", tone: enrollmentTone },
      { title: riskLabel(sdvTone), subtitle: `SDV completion ${sdvMetrics.percent}%`, tone: sdvTone },
      { title: riskLabel(capaTone), subtitle: `${capaMetrics.overdueCapas} overdue CAPAs`, tone: capaTone },
      { title: riskLabel(safetyTone), subtitle: `${safetyFindings.length} safety-linked findings`, tone: safetyTone },
    ];
  }, [
    capaMetrics.openCapas,
    capaMetrics.overdueCapas,
    enrollment.percent,
    enrollment.target,
    queryMetrics.open,
    queryMetrics.overdue,
    safetyFindings.length,
    sdvMetrics.percent,
  ]);

  const riskTrendRows = useMemo(() => {
    const openActionRisk = clampPercent(
      criticalOpenFindings.length * 25 +
      overdueFindings.length * 15 +
      Math.max(0, 100 - enrollment.percent) / 2 +
      Math.max(0, 100 - sdvMetrics.percent) / 2,
    );
    return [
      { label: "Enrollment gap", value: enrollment.target ? clampPercent(100 - enrollment.percent) : 0, tone: enrollment.percent < 80 ? "amber" as Tone : "green" as Tone },
      { label: "SDV gap", value: clampPercent(100 - sdvMetrics.percent), tone: sdvMetrics.percent < 80 ? "amber" as Tone : "green" as Tone },
      { label: "Open-action risk", value: openActionRisk, tone: openActionRisk >= 70 ? "red" as Tone : openActionRisk >= 35 ? "amber" as Tone : "green" as Tone },
    ];
  }, [criticalOpenFindings.length, enrollment.percent, enrollment.target, overdueFindings.length, sdvMetrics.percent]);

  const safetyReviewLines = useMemo<ReviewLine[]>(() => {
    const lines: ReviewLine[] = [
      { label: "Open safety-linked findings", value: safetyFindings.length, tone: safetyFindings.length ? "amber" : "green" },
      { label: "Open IP/pharmacy findings", value: ipFindings.length, tone: ipFindings.length ? "amber" : "green" },
    ];
    [...safetyFindings, ...ipFindings].slice(0, 3).forEach((finding) => {
      lines.push({
        label: `${findingIdForDisplay(finding.id, visitId)} - ${finding.description || finding.category}`,
        value: <StatusPill tone={toneForSeverity(finding.severity)}>{finding.status || "Open"}</StatusPill>,
        tone: toneForSeverity(finding.severity),
      });
    });
    return lines;
  }, [ipFindings, safetyFindings, visitId]);

  const criticalPriorities = useMemo<PriorityPlanItem[]>(() => {
    const source = criticalOpenFindings.length ? criticalOpenFindings : overdueFindings;
    return source.slice(0, 4).map((finding) => ({
      title: `Resolve ${conciseFindingTitle(finding, visitId)}`,
      detail: `${finding.description || "Open finding"}${isOverdueFinding(finding) ? ` | Overdue ${ageForFinding(finding)}` : ""}`,
      icon: AlertTriangle,
      tone: normalizeStatus(finding.severity).includes("critical") ? "red" : "amber",
      badge: normalizeStatus(finding.severity).includes("critical") ? "Critical" : "Overdue",
    }));
  }, [criticalOpenFindings, overdueFindings, visitId]);

  const highPriorities = useMemo<PriorityPlanItem[]>(() => {
    const items: PriorityPlanItem[] = openFindings
      .filter((finding) => !criticalOpenFindings.some((critical) => critical.id === finding.id))
      .slice(0, 3)
      .map((finding) => ({
        title: `Review ${conciseFindingTitle(finding, visitId)}`,
        detail: finding.description || "Open monitoring finding requires follow-up.",
        icon: isIpFinding(finding) ? PackageCheck : isSafetyFinding(finding) ? ShieldAlert : FileWarning,
        tone: toneForSeverity(finding.severity) === "red" ? "amber" : toneForSeverity(finding.severity),
        badge: finding.severity || "Open",
      }));
    if (sdvMetrics.pending > 0) {
      const subjects = sdvAttentionRows.map((row) => row.subject).join(", ");
      items.push({
        title: "Complete pending SDV review",
        detail: subjects ? `${sdvMetrics.pending} pending; priority subjects: ${subjects}.` : `${sdvMetrics.pending} subjects pending SDV.`,
        icon: SearchCheck,
        tone: "amber",
        badge: "High",
      });
    }
    if (enrollment.target > 0 && enrollment.percent < 80) {
      items.push({
        title: "Discuss recruitment acceleration with PI",
        detail: `${enrollment.randomised}/${enrollment.target} randomised (${enrollment.percent}%).`,
        icon: Target,
        tone: enrollment.percent < 50 ? "red" : "amber",
        badge: "High",
      });
    }
    return items.slice(0, 6);
  }, [
    criticalOpenFindings,
    enrollment.percent,
    enrollment.randomised,
    enrollment.target,
    openFindings,
    sdvAttentionRows,
    sdvMetrics.pending,
    visitId,
  ]);

  const mediumPriorities = useMemo<PriorityPlanItem[]>(() => {
    if (!queryMetrics.open) return [];
    return [{
      title: `Resolve ${queryMetrics.open} open data/query finding${queryMetrics.open === 1 ? "" : "s"}`,
      detail: queryMetrics.overdue
        ? `${queryMetrics.overdue} overdue; average overdue age ${queryMetrics.avgAge} days.`
        : "Review query/data-related findings with the site team.",
      icon: FileCheck2,
      tone: queryMetrics.overdue ? "amber" : "blue",
      badge: "Medium",
    }];
  }, [queryMetrics.avgAge, queryMetrics.open, queryMetrics.overdue]);

  const handlePreVisitReviewedChange = () => {
    if (isPreVisitReviewed || isVisitClosed || markPreVisitReviewedMutation.isPending) return;
    markPreVisitReviewedMutation.mutate(undefined, {
      onSuccess: (data) => {
        const reviewedAt = data.preVisitReviewedAt ?? new Date().toISOString();
        onPreVisitReviewedChange?.(reviewedAt);
        showToast("Pre-visit review acknowledged.", "success");
      },
      onError: (err) => {
        showToast(extractApiErrorMessage(err, "Failed to acknowledge pre-visit review"), "error");
      },
    });
  };

  useEffect(() => {
    if (!preVisit) return;
    const st = String(preVisit?.preVisitReportStatus || "DRAFT").trim().toUpperCase() || "DRAFT";
    onPreVisitReportStatusChange?.(st);
  }, [onPreVisitReportStatusChange, preVisit]);

  useEffect(() => {
    onOpenCountChange?.(prepOpenCount);
  }, [onOpenCountChange, prepOpenCount, visitId]);

  return (
    <div className="fade-in space-y-6">
      <section className="overflow-hidden rounded-lg border border-brand-100 bg-white shadow-card">
        <div className="border-b border-brand-100 bg-gradient-to-r from-brand-50 via-white to-accent-50 px-5 py-4">
          <div className="flex flex-wrap items-start gap-4">
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-slate-900">CRA Pre-Visit Preparation</h2>
              <p className="mt-1 text-sm font-medium text-slate-600">
                Study: {visitDetails?.protocol || "Study not recorded"} | Protocol: {visitDetails?.indNumber || "Protocol not recorded"} | Sponsor: {visitDetails?.sponsor || "Sponsor not recorded"} | Site {siteIdForPrimaryStatus || "Site ID not recorded"} - {siteContact?.institutionName || "Selected site"} | PI: {siteContact?.principalInvestigator || "N/A"}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <CommandBadge icon={CalendarDays} tone="blue">Visit: {visitDateForDisplay}</CommandBadge>
            <CommandBadge icon={Users} tone="purple">CRA: {visitDetails?.craName || "Assigned CRA"}</CommandBadge>
            <CommandBadge icon={Flag} tone="amber">Visit {visitCode}</CommandBadge>
            <CommandBadge icon={Building2} tone="green">{visitDetails?.visitType || "Visit type not recorded"}</CommandBadge>
            <CommandBadge icon={AlertTriangle} tone={riskTone}>Risk: {riskLevel}</CommandBadge>
          </div>
          <p className="mt-3 text-xs font-semibold text-slate-500">
            {previousVisitCode ? <>Prev visit: {previousVisitCode} ({previousVisitDate || "Not recorded"}) | </> : null}
            Internal use only
          </p>
        </div>

        <div className="px-5 py-4">
          <div className={joinClasses("flex flex-wrap items-center gap-3 rounded-md border px-4 py-3", toneClasses[carryOverAlertTone].border, toneClasses[carryOverAlertTone].bg)}>
            <AlertTriangle className={joinClasses("h-5 w-5 shrink-0", toneClasses[carryOverAlertTone].text)} strokeWidth={1.8} />
            <div className="min-w-0 flex-1">
              <p className={joinClasses("text-sm font-bold", toneClasses[carryOverAlertTone].text)}>
                {carryOverHeadline}
              </p>
              <p className={joinClasses("mt-0.5 text-xs", toneClasses[carryOverAlertTone].text)}>{carryOverItems.join(" | ")}</p>
            </div>
            <button
              type="button"
              onClick={() => followUpRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className={joinClasses("inline-flex items-center gap-2 rounded-md border bg-white px-3 py-1.5 text-xs font-bold hover:bg-white/70", toneClasses[carryOverAlertTone].border, toneClasses[carryOverAlertTone].text)}
            >
              <FileWarning className="h-3.5 w-3.5" strokeWidth={1.8} />
              Jump to Findings
            </button>
          </div>
        </div>
      </section>

      <section>
        <SectionHeading icon={BarChart3} title="Executive KPI Overview" />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
          <KpiCard
            icon={Users}
            title="Enrollment"
            badge={<StatusPill tone="amber">{enrollment.percent}%</StatusPill>}
          >
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="Target" value={enrollment.target} />
              <MetricTile label="Randomised" value={enrollment.randomised} tone="blue" />
              <MetricTile label="Screened" value={enrollment.screened} />
              <MetricTile label="Active" value={enrollment.active} tone="green" />
            </div>
            <div className="mt-4 space-y-2">
              <DotLabel tone="green" value={enrollment.active}>Active / SDV verified</DotLabel>
              <DotLabel tone="amber" value={Math.max(enrollment.screened - enrollment.randomised, 0)}>Screened not randomised</DotLabel>
              <DotLabel tone={enrollment.target > enrollment.randomised ? "amber" : "green"} value={Math.max(enrollment.target - enrollment.randomised, 0)}>Enrollment gap</DotLabel>
            </div>
          </KpiCard>

          <KpiCard
            icon={SearchCheck}
            title="SDV / SDR"
            badge={<StatusPill tone="amber">{sdvMetrics.percent}%</StatusPill>}
          >
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="SDV complete" value={sdvMetrics.verified} tone="green" />
              <MetricTile label="SDV pending" value={sdvMetrics.pending} tone="red" />
              <MetricTile label="SDR complete" value={sdvMetrics.sdrComplete} tone="green" />
              <MetricTile label="High priority" value={sdvMetrics.highPriority} tone="amber" />
            </div>
            <div className="mt-4 space-y-2">
              {sdvAttentionRows.length ? (
                sdvAttentionRows.map((row) => (
                  <DotLabel key={row.subject} tone={row.priority} value={<StatusPill tone={row.priority}>{row.sdvStatus}</StatusPill>}>
                    {row.subject} - {row.currentVisit}
                  </DotLabel>
                ))
              ) : (
                <DotLabel tone="green" value={<StatusPill tone="green">Clear</StatusPill>}>No subject-level SDV blockers in available data</DotLabel>
              )}
            </div>
          </KpiCard>

          <KpiCard
            icon={Clock3}
            title="Queries"
            badge={<StatusPill tone="red">{queryMetrics.overdue} overdue</StatusPill>}
          >
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="Total" value={queryMetrics.total} />
              <MetricTile label="Open" value={queryMetrics.open} tone="red" />
              <MetricTile label="Overdue" value={queryMetrics.overdue} tone="amber" />
              <MetricTile label="Avg age" value={`${queryMetrics.avgAge}d`} tone="amber" />
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-bold uppercase text-slate-500">By domain</p>
              {queryMetrics.domains.length ? (
                queryMetrics.domains.map((domain) => (
                  <DotLabel key={domain.label} tone={domain.tone} value={domain.value}>{domain.label}</DotLabel>
                ))
              ) : (
                <DotLabel tone="green" value={0}>No query/data findings in available data</DotLabel>
              )}
            </div>
          </KpiCard>

          <KpiCard
            icon={ClipboardCheck}
            title="Findings & CAPAs"
            badge={<StatusPill tone="red">{capaMetrics.criticalCount} critical</StatusPill>}
          >
            <div className="grid grid-cols-2 gap-2">
              <MetricTile label="Open findings" value={capaMetrics.openFindingCount} tone="red" />
              <MetricTile label="Open CAPAs" value={capaMetrics.openCapas} tone="amber" />
              <MetricTile label="Overdue CAPAs" value={capaMetrics.overdueCapas} tone="red" />
              <MetricTile label="CAPA closure" value={`${capaMetrics.closure}%`} tone="green" />
            </div>
            <div className="mt-4 space-y-2">
              <p className="text-xs font-bold uppercase text-slate-500">Repeat findings</p>
              {repeatFindingCards.length ? (
                repeatFindingCards.slice(0, 2).map((card) => (
                  <DotLabel key={card.title} tone={card.tone} value={<StatusPill tone={card.tone}>Pattern</StatusPill>}>
                    {card.title}
                  </DotLabel>
                ))
              ) : (
                <DotLabel tone="green" value={<StatusPill tone="green">None</StatusPill>}>No recurring pattern detected in open findings</DotLabel>
              )}
            </div>
          </KpiCard>
        </div>
      </section>

      <section ref={followUpRef} className="rounded-lg border border-red-100 bg-white p-5 shadow-card">
        <div className="-mx-5 -mt-5 mb-5 flex flex-wrap items-center justify-between gap-2 border-b border-red-100 bg-red-50 px-5 py-3">
          <div className="flex items-center gap-2 text-red-800">
            <Clock3 className="h-4 w-4" strokeWidth={1.8} />
            <h3 className="text-sm font-bold">{previousVisitHeading}</h3>
          </div>
          <StatusPill tone="red">{followUpFindings.length} unresolved items | {capaMetrics.overdueCapas} overdue CAPAs</StatusPill>
        </div>

        <div className="space-y-6">
          <div>
            <SectionHeading title="Open Findings From Previous Visits" />
            <MiniTable columns={["Finding ID", "Visit date", "Category", "Severity", "Description", "Status", "Age"]}>
              {followUpFindings.length ? (
                followUpFindings.map((finding) => {
                  const isOverdue = normalizeStatus(finding.status).includes("overdue");
                  return (
                    <tr key={finding.id} className="odd:bg-white even:bg-stone-50">
                      <td className="whitespace-nowrap px-3 py-2 font-bold text-blue-700">{finding.id}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-600">{finding.visitDate}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-600">{finding.category}</td>
                      <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={toneForSeverity(finding.severity)}>{finding.severity}</StatusPill></td>
                      <td className="min-w-[260px] px-3 py-2 font-semibold text-slate-700">{finding.description}</td>
                      <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={isOverdue ? "red" : "amber"}>{finding.status}</StatusPill></td>
                      <td className={joinClasses("whitespace-nowrap px-3 py-2 font-bold", isOverdue ? "text-red-700" : "text-slate-600")}>{finding.age}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-xs font-semibold text-slate-500">
                    No unresolved findings are available for this visit.
                  </td>
                </tr>
              )}
            </MiniTable>
          </div>

          <div>
            <SectionHeading title="Open CAPAs" />
            <MiniTable columns={["CAPA ID", "Finding", "Description", "Responsible", "Due date", "Status", "Age"]}>
              {capaRows.length ? (
                capaRows.map((capa) => {
                  const isOverdue = normalizeStatus(capa.status).includes("overdue");
                  return (
                    <tr key={`${capa.id}-${capa.finding}`} className="odd:bg-white even:bg-stone-50">
                      <td className="whitespace-nowrap px-3 py-2 font-bold text-amber-800">{capa.id}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700">{capa.finding}</td>
                      <td className="min-w-[220px] px-3 py-2 font-semibold text-slate-700">{capa.description}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-600">{capa.responsible}</td>
                      <td className={joinClasses("whitespace-nowrap px-3 py-2 font-bold", isOverdue ? "text-red-600" : "text-slate-700")}>{capa.dueDate}</td>
                      <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={isOverdue ? "red" : "amber"}>{capa.status}</StatusPill></td>
                      <td className={joinClasses("whitespace-nowrap px-3 py-2 font-bold", isOverdue ? "text-red-700" : "text-slate-600")}>{capa.age}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-xs font-semibold text-slate-500">
                    No CAPA action items are linked to the current open findings.
                  </td>
                </tr>
              )}
            </MiniTable>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div>
              <SectionHeading title="Repeat / Recurring Findings" />
              <div className="space-y-3">
                {repeatFindingCards.length ? (
                  repeatFindingCards.map((card) => (
                    <div key={card.title} className={joinClasses("rounded-lg border p-4", toneClasses[card.tone].border, toneClasses[card.tone].bg)}>
                      <p className={joinClasses("text-sm font-bold", toneClasses[card.tone].text)}>{card.title}</p>
                      <p className={joinClasses("mt-1 text-xs", toneClasses[card.tone].text)}>{card.detail}</p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                    <p className="text-sm font-bold text-emerald-800">No recurring pattern detected</p>
                    <p className="mt-1 text-xs text-emerald-700">Open findings do not currently repeat by category or query/data pattern.</p>
                  </div>
                )}
              </div>
            </div>
            <div>
              <SectionHeading title="Previously Escalated Issues" />
              <div className="space-y-3">
                {escalatedIssueCards.length ? (
                  escalatedIssueCards.map((card) => (
                    <div key={card.title} className={joinClasses("rounded-lg border p-4", toneClasses[card.tone].border, toneClasses[card.tone].bg)}>
                      <p className={joinClasses("text-sm font-bold", toneClasses[card.tone].text)}>{card.title}</p>
                      <p className={joinClasses("mt-1 text-xs", toneClasses[card.tone].text)}>{card.detail}</p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm font-bold text-slate-700">No escalation candidates from available data</p>
                    <p className="mt-1 text-xs text-slate-500">Escalations will appear here when overdue findings, low enrollment, or pending checklist items are detected.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[1.05fr_1fr]">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-card">
          <SectionHeading
            icon={Gauge}
            title="RBQM Risk Dashboard"
            right={<StatusPill tone={riskTone}>Overall: {riskLevel}</StatusPill>}
          />
          <div className="grid grid-cols-2 gap-2">
            {riskCells.map((cell) => (
              <RiskCell key={cell.subtitle} title={cell.title} subtitle={cell.subtitle} tone={cell.tone} />
            ))}
          </div>
          <div className="mt-4 space-y-2">
            <p className="text-xs font-bold uppercase text-slate-500">Site risk trend</p>
            {riskTrendRows.map((row) => {
              const t = toneClasses[row.tone];
              return (
                <div key={row.label} className="grid grid-cols-[120px_1fr_38px] items-center gap-2 text-[11px] text-slate-600">
                  <span>{row.label}</span>
                  <div className="h-1.5 rounded-full bg-slate-100">
                    <div className={joinClasses("h-1.5 rounded-full", t.dot)} style={{ width: `${row.value}%` }} />
                  </div>
                  <span className="text-right font-semibold">{row.value}%</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-card">
          <SectionHeading icon={ShieldCheck} title="Safety & IP Review" />
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label="Safety findings" value={safetyFindings.length} tone={safetyFindings.length ? "amber" : "green"} />
            <MetricTile label="IP / pharmacy" value={ipFindings.length} tone={ipFindings.length ? "amber" : "green"} />
            <MetricTile label="Critical safety" value={safetyFindings.filter((finding) => normalizeStatus(finding.severity).includes("critical")).length} tone="red" />
            <MetricTile label="Open follow-up" value={openFindings.length} tone={openFindings.length ? "amber" : "green"} />
          </div>
          <div className="mt-4 space-y-2">
            {safetyReviewLines.map((line) => (
              <DotLabel key={line.label} tone={line.tone} value={line.value}>{line.label}</DotLabel>
            ))}
          </div>
        </div>

      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-card">
        <SectionHeading
          icon={Users}
          title="Subject Review - All Active Subjects"
          right={<StatusPill tone="blue">{subjectRows.filter((row) => row.priority !== "green").length} subjects require action</StatusPill>}
        />
        <MiniTable columns={["Subject", "Current visit", "SDV status", "Queries", "Protocol dev.", "SAE", "Priority"]}>
          {subjectRows.length ? (
            subjectRows.map((row) => (
              <tr key={row.subject} className="odd:bg-white even:bg-stone-50">
                <td className={joinClasses("whitespace-nowrap px-3 py-2 font-bold", row.priority === "red" ? "text-red-700" : "text-slate-700")}>{row.subject}</td>
                <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-600">{row.currentVisit}</td>
                <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={row.sdvStatus === "Complete" ? "green" : row.priority}>{row.sdvStatus}</StatusPill></td>
                <td className={joinClasses("whitespace-nowrap px-3 py-2 font-semibold", row.queries.startsWith("0") ? "text-emerald-700" : "text-amber-700")}>{row.queries}</td>
                <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={row.protocolDeviation === "None" ? "green" : "amber"}>{row.protocolDeviation}</StatusPill></td>
                <td className="whitespace-nowrap px-3 py-2">{row.sae}</td>
                <td className="whitespace-nowrap px-3 py-2"><StatusPill tone={row.priority}>{row.priority === "red" ? "High" : row.priority === "amber" ? "Medium" : "Low"}</StatusPill></td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={7} className="px-3 py-6 text-center text-xs font-semibold text-slate-500">
                No subject-level finding data is available for this visit.
              </td>
            </tr>
          )}
        </MiniTable>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-card">
        <SectionHeading
          icon={Flag}
          title="CRA Visit Priorities - Auto-Generated"
          right={<StatusPill tone={criticalPriorities.length ? "red" : highPriorities.length ? "amber" : "blue"}>{criticalPriorities.length + highPriorities.length + mediumPriorities.length} active priorities</StatusPill>}
        />
        <div>
          <p className="mt-2 text-xs font-bold uppercase text-slate-500">Critical - Must complete during visit</p>
          <div className="mt-1">
            {criticalPriorities.length ? (
              criticalPriorities.map((item) => (
                <PriorityItem
                  key={item.title}
                  icon={item.icon}
                  title={item.title}
                  detail={item.detail}
                  tone={item.tone}
                  badge={item.badge}
                />
              ))
            ) : (
              <div className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-3 text-xs font-semibold text-emerald-700">
                No critical findings in available data.
              </div>
            )}
          </div>
          <p className="mt-5 text-xs font-bold uppercase text-slate-500">High priority</p>
          <div className="mt-1">
            {highPriorities.length ? (
              highPriorities.map((item) => (
                <PriorityItem
                  key={item.title}
                  icon={item.icon}
                  title={item.title}
                  detail={item.detail}
                  tone={item.tone}
                  badge={item.badge}
                />
              ))
            ) : (
              <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-3 text-xs font-semibold text-slate-500">
                No high-priority visit actions generated from current findings, SDV, or enrollment data.
              </div>
            )}
          </div>
          <p className="mt-5 text-xs font-bold uppercase text-slate-500">Medium</p>
          {mediumPriorities.length ? (
            mediumPriorities.map((item) => (
              <PriorityItem
                key={item.title}
                icon={item.icon}
                title={item.title}
                detail={item.detail}
                tone={item.tone}
                badge={item.badge}
              />
            ))
          ) : (
            <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-3 text-xs font-semibold text-slate-500">
              No medium-priority query/data actions generated.
            </div>
          )}
        </div>
      </section>

      <section className={joinClasses(
        "rounded-lg border p-5 shadow-card",
        isPreVisitReviewed ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white",
      )}>
        <label className={joinClasses(
          "flex items-start gap-3",
          isVisitClosed || markPreVisitReviewedMutation.isPending ? "cursor-not-allowed opacity-80" : "cursor-pointer",
        )}>
          <input
            type="checkbox"
            checked={isPreVisitReviewed}
            disabled={isVisitClosed || markPreVisitReviewedMutation.isPending}
            onChange={handlePreVisitReviewedChange}
            className="mt-1 h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          />
          <span className="min-w-0">
            <span className="block text-sm font-bold text-slate-900">
              I acknowledge that I have reviewed the pre-visit preparation and carry-over items for this visit.
            </span>
            <span className={joinClasses(
              "mt-1 block text-xs font-semibold",
              isPreVisitReviewed ? "text-emerald-700" : "text-slate-500",
            )}>
              {isPreVisitReviewed
                ? "Pre-Visit step completed."
                : markPreVisitReviewedMutation.isPending
                  ? "Saving review acknowledgement..."
                  : "This confirmation marks the Pre-Visit step complete."}
            </span>
          </span>
        </label>
      </section>
    </div>
  );
}
