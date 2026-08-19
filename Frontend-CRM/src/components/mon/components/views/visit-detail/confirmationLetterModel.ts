export const DEFAULT_CONTENT = [
  "Date: ${System.CurrentDate}",
  "",
  "To: Principal Investigator: ${Site.PI_Title} ${Site.PI_FirstName} ${Site.PI_LastName}",
  "Site Number: ${Site.SiteId}",
  "Institution/Site Name: ${Site.siteName}",
  "Address: ${Site.Address}",
  "CC: ${Site.CRC_FullName}, ${Site.CRC_Title}",
  "",
  "Protocol Number: ${Study.ProtocolID}",
  "Protocol Title: ${Study.ProtocolTitle}",
  "",
  "Dear Dr. ${Site.PI_LastName} and Study Team,",
  "",
  "The purpose of this letter is to formally confirm the upcoming ${Visit.Type} for the above-referenced protocol. The visit will be conducted ${Visit.Method} by your assigned Clinical Research Associate (CRA), ${CRA.FullName}.",
  "",
  "1) Visit Logistics",
  "• Date(s) of Visit: ${Visit.StartDate} to ${Visit.EndDate}",
  "• Expected Arrival Time: ${Visit.ExpectedArrival}",
  "• Expected Departure Time: ${Visit.ExpectedDeparture}",
  "• Facility Access Required: ${Visit.FacilityAccessRequired}",
  "",
  "2) Personnel Availability",
  "To ensure a productive visit and timely resolution of queries, please ensure the following staff are available:",
  "• Study Coordinator (CRC): Available throughout the visit to assist with data queries and document retrieval.",
  "• Principal Investigator (PI): A brief meeting is requested on ${Visit.PIMeetingDate} at ${Visit.PIMeetingTime} to discuss overall site performance.",
  "{% if Visit.RequiresPharmacyReview == true %}",
  "• Pharmacist / Unblinded Personnel: A brief meeting is requested on ${Visit.PharmacyMeetingDate} at ${Visit.PharmacyMeetingTime} for Investigational Product (IP) accountability.",
  "{% endif %}",
  "",
  "3) Visit Agenda and Objectives",
  "During this visit, the CRA will review the following critical study components in accordance with the Clinical Monitoring Plan (CMP):",
  "• Informed Consent Forms (ICFs): Verification of 100% of newly signed ICFs for subjects enrolled since the last visit.",
  "• Source Data Verification/Review (SDV/SDR): Review of source documents against EDC entries for the following subjects:",
  "• Safety & Pharmacovigilance: Review of all new and ongoing Adverse Events (AEs) and Serious Adverse Events (SAEs).",
  "{% if Visit.RequiresPharmacyReview == true %}",
  "• Investigational Product (IP): Physical inventory check, review of temperature logs, and reconciliation of dispensation/return records.",
  "{% endif %}",
  "• Investigator Site File (ISF): Review of the regulatory binder, including the DOA log and updated CVs/Licenses.",
  "• Action Items: Follow-up on ${ActionItems.OpenCount} outstanding issues and ${EDC.OpenQueriesCount} open EDC queries from previous visits.",
  "",
  "4) Pre-Visit Preparation",
  "To maximize efficiency, please ensure the following are completed prior to the CRA's arrival:",
  "• All subject data up to the cut-off date of ${Visit.DataCutOffDate} is entered into the EDC.",
  "• All outstanding EDC queries are addressed.",
  "• Source documents are organized and accessible.",
  "",
  "Acknowledgment",
  "Please log into the Investigator Portal to acknowledge and confirm the proposed dates, times, and agenda.",
  "",
  "Sincerely,",
  "",
  "${CRA.FullName}",
  "${CRA.Title}",
  "${Sponsor_Name}",
  "${CRA.Email} | ${CRA.Phone}",
].join("\n");

const VISIT_SCHEDULE_PLACEHOLDER_RE =
  /\$\{Visit\.(StartDate|EndDate|ExpectedArrival|ExpectedDeparture|PIMeetingDate|PIMeetingTime|PharmacyMeetingDate|PharmacyMeetingTime|DataCutOffDate)\}/;

const LOCKED_PLACEHOLDER_RE =
  /\$\{(Site\.|Study\.|System\.CurrentDate|Visit\.(StartDate|EndDate|ExpectedArrival|ExpectedDeparture|FacilityAccessRequired|PIMeetingDate|PIMeetingTime|PharmacyMeetingDate|PharmacyMeetingTime|DataCutOffDate))[^}]*\}/;

/** Saved/sent letters often store rendered dates; re-render from the default template when needed. */
export function resolveLetterTemplate(content: string): string {
  return VISIT_SCHEDULE_PLACEHOLDER_RE.test(content) ? content : DEFAULT_CONTENT;
}

export function isLockedLine(line: string): boolean {
  const trimmed = line.trim();
  if (/^\{\%.*\%\}\s*$/.test(trimmed)) return true;
  return LOCKED_PLACEHOLDER_RE.test(line);
}

export type LetterSegment =
  | { kind: "locked"; lines: string[] }
  | { kind: "editable"; lines: string[]; index: number };

export function splitLetterTemplate(template: string): LetterSegment[] {
  const lines = template.split("\n");
  const segments: LetterSegment[] = [];
  let editableIndex = 0;
  let bucket: string[] = [];
  let bucketKind: "locked" | "editable" | null = null;

  const flush = () => {
    if (!bucket.length || !bucketKind) return;
    if (bucketKind === "locked") {
      segments.push({ kind: "locked", lines: [...bucket] });
    } else {
      segments.push({ kind: "editable", lines: [...bucket], index: editableIndex++ });
    }
    bucket = [];
  };

  for (const line of lines) {
    const kind = isLockedLine(line) ? "locked" : "editable";
    if (bucketKind && bucketKind !== kind) flush();
    bucketKind = kind;
    bucket.push(line);
  }
  flush();
  return segments;
}

export function mergeLetterSegments(segments: LetterSegment[]): string {
  return segments.map((seg) => seg.lines.join("\n")).join("\n");
}

export function updateEditableSegment(
  template: string,
  segmentIndex: number,
  newText: string,
): string {
  const segments = splitLetterTemplate(template);
  const target = segments.find(
    (seg): seg is Extract<LetterSegment, { kind: "editable" }> =>
      seg.kind === "editable" && seg.index === segmentIndex,
  );
  if (!target) return template;
  target.lines = newText.split("\n");
  return mergeLetterSegments(segments);
}

export function renderLetterTemplate(
  template: string,
  values: Record<string, string>,
  requiresPharmacy: boolean,
): string {
  let out = template;
  out = out.replace(
    /\{\%\s*if\s+Visit\.RequiresPharmacyReview\s*==\s*true\s*\%\}([\s\S]*?)\{\%\s*endif\s*\%\}/g,
    (_m, block) => (requiresPharmacy ? block : ""),
  );
  const targetedSubjects = String(values["TargetedSubjects.List"] || "").trim();
  if (!targetedSubjects || targetedSubjects.toUpperCase() === "N/A") {
    out = out
      .split("\n")
      .filter((line) => !line.includes("${TargetedSubjects.List}"))
      .join("\n");
  }
  out = out.replace(/\$\{([^}]+)\}/g, (_m, keyRaw) => {
    const key = String(keyRaw || "").trim();
    return values[key] ?? `\${${key}}`;
  });
  return out;
}

export function parseDurationHours(raw: string): number {
  const s = (raw || "").toLowerCase();
  if (!s) return 8;
  const range = s.match(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*hours?/);
  if (range) {
    const lo = Number(range[1]);
    const hi = Number(range[2]);
    if (Number.isFinite(lo) && Number.isFinite(hi)) return (lo + hi) / 2;
  }
  const one = s.match(/(\d+(?:\.\d+)?)\s*hours?/);
  if (one) {
    const h = Number(one[1]);
    if (Number.isFinite(h)) return h;
  }
  if (s.includes("half day")) return 4;
  if (s.includes("full day")) return 8;
  return 8;
}

function parseVisitDateTime(raw: string): Date | null {
  const s = (raw || "").trim();
  if (!s || s.toUpperCase() === "TBD") return null;
  const normalized = s.replace("·", "").trim();
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatTime12(d: Date): string {
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true });
}

function formatVisitDateOnly(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}

function stripTimeFromVisitDisplay(raw: string): string {
  const s = (raw || "").trim();
  if (!s || s.toUpperCase() === "TBD") return s || "TBD";
  const dotIdx = s.indexOf("·");
  return dotIdx >= 0 ? s.slice(0, dotIdx).trim() : s;
}

export type VisitOverviewLike = {
  siteContact?: {
    principalInvestigator?: string;
    studyCoordinator?: string;
    siteAddress?: string;
    institutionName?: string;
  };
  visitDetails?: {
    craName?: string;
    sponsor?: string;
    visitDate?: string;
    visitDateIso?: string;
    endDate?: string;
    endDateIso?: string;
    duration?: string;
    visitType?: string;
    protocol?: string;
    siteId?: string;
  };
  actionRequiredCount?: number;
};

export function buildLetterValues(
  visitOverview: VisitOverviewLike | null | undefined,
  docDate: string,
  formatTodayLong: () => string,
): { values: Record<string, string>; requiresPharmacy: boolean } {
  const sc = visitOverview?.siteContact;
  const vd = visitOverview?.visitDetails;
  const [piFirstName, ...piRest] = String(sc?.principalInvestigator || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  const piLastName = piRest.length > 0 ? piRest[piRest.length - 1] : piFirstName || "";
  const crcFullName = String(sc?.studyCoordinator || "").trim();
  const craFullName = String(vd?.craName || "").trim();
  const sponsor = String(vd?.sponsor || "").trim();
  const visitDate = String(vd?.visitDate || "").trim();
  const visitDateIso = String(vd?.visitDateIso || "").trim();
  const visitDuration = String(vd?.duration || "").trim();
  const visitType = String(vd?.visitType || "").trim();
  const protocol = String(vd?.protocol || "").trim();
  const siteAddress = String(sc?.siteAddress || "").trim();
  const institutionName = String(sc?.institutionName || "").trim();
  const siteIdRaw = String(vd?.siteId || "").trim();
  const requiresPharmacy = /on-site|onsite/i.test(visitType);

  const startDt = (() => {
    if (visitDateIso) {
      const d = new Date(visitDateIso);
      if (!Number.isNaN(d.getTime())) return d;
    }
    return parseVisitDateTime(visitDate);
  })();
  const durationHours = parseDurationHours(visitDuration);

  const endDateIso = String(vd?.endDateIso || "").trim();
  const endDateDisplay = String(vd?.endDate || "").trim();
  const explicitEndDt: Date | null = (() => {
    if (endDateIso) {
      const d = new Date(endDateIso);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    if (endDateDisplay) return parseVisitDateTime(endDateDisplay);
    return null;
  })();

  const arrivalTime = startDt ? formatTime12(startDt) : "TBD";
  const departureTime = (() => {
    if (explicitEndDt) return formatTime12(explicitEndDt);
    if (!startDt) return "TBD";
    return formatTime12(new Date(startDt.getTime() + durationHours * 60 * 60 * 1000));
  })();
  const startStamp = startDt ? formatVisitDateOnly(startDt) : stripTimeFromVisitDisplay(visitDate);
  const endStamp = (() => {
    if (explicitEndDt) return formatVisitDateOnly(explicitEndDt);
    if (!startDt) return stripTimeFromVisitDisplay(endDateDisplay || visitDate);
    return formatVisitDateOnly(new Date(startDt.getTime() + durationHours * 60 * 60 * 1000));
  })();

  const values: Record<string, string> = {
    "System.CurrentDate": docDate !== "—" ? docDate : formatTodayLong(),

    "Site.PI_Title": "Dr.",
    "Site.PI_FirstName": piFirstName || "N/A",
    "Site.PI_LastName": piLastName || "N/A",
    "Site.SiteNumber": siteIdRaw || "N/A",
    "Site.SiteId": siteIdRaw || "N/A",
    "Site.InstitutionName": institutionName || "N/A",
    "Site.siteName": institutionName || "N/A",
    "Site.Address": siteAddress || "N/A",
    "Site.CRC_FullName": crcFullName || "N/A",
    "Site.CRC_Title": "Study Coordinator",

    "Study.ProtocolID": protocol || "N/A",
    "Study.ProtocolTitle": protocol || "N/A",

    "Visit.Type": visitType || "Monitoring Visit",
    "Visit.Method": /remote/i.test(visitType) ? "remotely" : "on-site",
    "Visit.StartDate": startStamp,
    "Visit.EndDate": endStamp,
    "Visit.ExpectedArrival": arrivalTime,
    "Visit.ExpectedDeparture": departureTime,
    "Visit.FacilityAccessRequired": "Yes",
    "Visit.PIMeetingDate": startDt
      ? startDt.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
      : visitDate || "TBD",
    "Visit.PIMeetingTime": "4:30 PM",
    "Visit.PharmacyMeetingDate": startDt
      ? startDt.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
      : visitDate || "TBD",
    "Visit.PharmacyMeetingTime": "2:30 PM",
    "Visit.DataCutOffDate": startDt
      ? startDt.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
      : visitDate || "TBD",

    "TargetedSubjects.List": "N/A",
    "ActionItems.OpenCount": String(visitOverview?.actionRequiredCount ?? 0),
    "EDC.OpenQueriesCount": "N/A",

    "CRA.SignatureImage": "[Signature]",
    "CRA.FullName": craFullName || "N/A",
    "CRA.Title": "Clinical Research Associate",
    "Sponsor_Name": sponsor || "N/A",
    "CRA.Email": "N/A",
    "CRA.Phone": "N/A",
  };

  return { values, requiresPharmacy };
}
