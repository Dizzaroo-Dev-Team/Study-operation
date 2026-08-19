import { AvatarStack } from "../ui";
import type { Finding } from "../../types";
import { getFindingActionItems } from "../../utils/findingActionItems";

function primaryActionItem(finding: Finding) {
  const items = getFindingActionItems(finding);
  return { items, primary: items[0] };
}

function extraItemsTooltip(items: ReturnType<typeof getFindingActionItems>): string {
  return items
    .slice(1)
    .map(
      (item, index) =>
        `${index + 2}. ${item.assignee.name} · ${item.dueDate || "TBD"} · ${(item.resolution || "").trim() || "Pending"}`,
    )
    .join("\n");
}

function MoreActionsBadge({ count, title }: { count: number; title: string }) {
  if (count <= 0) return null;
  return (
    <span className="finding-action-more" title={title}>
      +{count} more
    </span>
  );
}

export function FindingAssigneesCell({ finding }: { finding: Finding }) {
  const { items, primary } = primaryActionItem(finding);
  if (!primary) return <span style={{ color: "var(--text-muted)" }}>—</span>;

  return (
    <div className="finding-action-primary">
      <AvatarStack
        initials={primary.assignee.initials}
        color={primary.assignee.color}
        name={primary.assignee.name}
      />
      <MoreActionsBadge count={items.length - 1} title={extraItemsTooltip(items)} />
    </div>
  );
}

export function FindingDueDatesCell({ finding }: { finding: Finding }) {
  const { primary } = primaryActionItem(finding);
  if (!primary) return <span style={{ color: "var(--text-muted)" }}>—</span>;

  return (
    <span
      className="finding-action-due"
      style={{
        fontSize: 13,
        color:
          finding.dueColor === "red"
            ? "var(--red)"
            : finding.dueColor === "orange"
              ? "var(--orange)"
              : "var(--text-muted)",
        fontWeight: finding.dueColor !== "muted" ? 500 : 400,
      }}
    >
      {primary.dueDate || "TBD"}
    </span>
  );
}

export function FindingCorrectiveActionsCell({ finding }: { finding: Finding }) {
  const { items, primary } = primaryActionItem(finding);
  if (!primary) return <span style={{ color: "var(--text-muted)" }}>—</span>;

  const text = (primary.resolution || "").trim() || "Pending";
  const title =
    items.length > 1
      ? `${text}\n\nOther actions:\n${extraItemsTooltip(items)}`
      : text;

  return (
    <span className="finding-action-resolution" title={title}>
      {text}
    </span>
  );
}

/** Compact summary for dashboard-style tables. */
export function FindingActionItemsSummaryCell({ finding }: { finding: Finding }) {
  const { items, primary } = primaryActionItem(finding);
  if (!primary) return <span style={{ color: "var(--text-muted)" }}>—</span>;

  const label = `${primary.assignee.name} · ${primary.dueDate || "TBD"}`;
  if (items.length === 1) {
    return (
      <span className="finding-action-summary" title={label}>
        {label}
      </span>
    );
  }

  return (
    <span className="finding-action-summary" title={`${label}\n${extraItemsTooltip(items)}`}>
      {label}
      <span className="finding-action-more finding-action-more--inline"> +{items.length - 1}</span>
    </span>
  );
}
