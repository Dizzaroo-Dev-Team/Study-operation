import type { CRA, Finding, FindingActionItem } from "../types";

export function getFindingActionItems(finding: Finding): FindingActionItem[] {
  if (finding.actionItems?.length) return finding.actionItems;
  return [
    {
      assignee: finding.assignee,
      dueDate: finding.dueDate,
      closedDate: finding.actionItems?.[0]?.closedDate || "",
      resolution: finding.resolution || "",
    },
  ];
}

export function formatActionItemDueDate(dueInput: string): string {
  if (!dueInput) return "TBD";
  const ymd = dueInput.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const monthDay = dueInput.match(/^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
  const date = ymd
    ? new Date(Number(ymd[1]), Number(ymd[2]) - 1, Number(ymd[3]))
    : monthDay
      ? new Date(`${monthDay[1]} ${monthDay[2]}, ${monthDay[3] || new Date().getFullYear()}`)
    : new Date(dueInput);
  if (Number.isNaN(date.getTime())) return "TBD";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function buildActionItemsPayload(
  rows: Array<{ id?: string; assignee: string; due: string; closedDate?: string; resolution: string; taskMode?: string }>,
  assigneeBadgeFromName: (name: string) => CRA,
) {
  return rows.map((row) => {
    const assigneeObj = assigneeBadgeFromName(row.assignee);
    return {
      // Echo back the row's own id (when it already existed) so the backend
      // can tell an edited item apart from a brand-new one and avoid
      // re-creating its linked Task on every save.
      id: row.id || undefined,
      assigneeInitials: assigneeObj.initials,
      assigneeName: assigneeObj.name,
      assigneeColor: assigneeObj.color,
      dueDate: formatActionItemDueDate(row.due),
      closedDate: row.closedDate ? formatActionItemDueDate(row.closedDate) : "",
      resolution: row.resolution || "",
      taskMode: row.taskMode || "",
    };
  });
}

export type FindingFormPayload = {
  category: string;
  severity: string;
  finding: string;
  subjectId: string;
  reference: string;
  actionItems: Array<{ id?: string; assignee: string; due: string; closedDate?: string; resolution: string; taskMode?: string }>;
};

export function buildFindingMutationPayload(
  form: FindingFormPayload,
  assigneeBadgeFromName: (name: string) => CRA,
) {
  const actionItems = buildActionItemsPayload(form.actionItems, assigneeBadgeFromName);
  const primary = actionItems[0];
  const finding = form.finding.trim();
  return {
    category: form.category,
    finding,
    description: finding,
    severity: form.severity,
    subjectId: (form.subjectId || "").trim(),
    reference: (form.reference || "").trim(),
    actionItems,
    assigneeInitials: primary?.assigneeInitials,
    assigneeName: primary?.assigneeName,
    assigneeColor: primary?.assigneeColor,
    dueDate: primary?.dueDate || "TBD",
    closedDate: primary?.closedDate || "",
    resolution: primary?.resolution || "",
    taskMode: primary?.taskMode || "",
  };
}
