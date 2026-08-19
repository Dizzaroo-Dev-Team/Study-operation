import type { ReviewComment } from "@/lib/queries/useMonitoring";

/**
 * Prefix used to embed a stable field id inside `dom_path` at comment-creation time,
 * e.g. `mvrField=fld_abc123|div[1]>label[0]`. This lets the author edit page unlock
 * exactly the commented field instead of relying on fragile cross-DOM fuzzy matching.
 */
const DOM_PATH_FIELD_PREFIX = "mvrField=";

/** Build a dom_path value with an embedded field id. */
export function encodeDomPathWithFieldKey(fieldKey: string | null | undefined, domPath: string): string {
  const key = (fieldKey || "").trim();
  if (!key) return domPath;
  return `${DOM_PATH_FIELD_PREFIX}${key}|${domPath}`;
}

/** Extract the embedded field id from a dom_path, if present. */
export function extractFieldKeyFromDomPath(domPath: string | null | undefined): string | null {
  const raw = (domPath || "").trim();
  if (!raw.startsWith(DOM_PATH_FIELD_PREFIX)) return null;
  const bar = raw.indexOf("|");
  const key = (bar === -1 ? raw.slice(DOM_PATH_FIELD_PREFIX.length) : raw.slice(DOM_PATH_FIELD_PREFIX.length, bar)).trim();
  return key || null;
}

/** Strip an embedded field-id prefix so the remaining string is a pure dom path. */
function stripFieldKeyPrefix(domPath: string): string {
  const raw = (domPath || "").trim();
  if (!raw.startsWith(DOM_PATH_FIELD_PREFIX)) return raw;
  const bar = raw.indexOf("|");
  return bar === -1 ? "" : raw.slice(bar + 1);
}

/** Safe attribute-selector escaping for field ids (fallback when CSS.escape is unavailable). */
function escapeAttrValue(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(value);
  return value.replace(/["\\]/g, "\\$&");
}

/** Whether a field id exists in the template metadata or the live report DOM. */
function fieldKeyExists(
  key: string,
  root: HTMLElement | null,
  templateFields?: TemplateFieldLike[],
): boolean {
  if (templateFields?.some((f) => f.id === key)) return true;
  if (root && root.querySelector(`[data-mvr-field="${escapeAttrValue(key)}"]`)) return true;
  return false;
}

/** Resolve a dom_path segment chain (from the review page) to a live node. */
function resolveDomPath(root: HTMLElement, path: string): Node | null {
  const trimmed = stripFieldKeyPrefix(path);
  if (!trimmed) return null;
  let cur: Node = root;
  for (const part of trimmed.split(">")) {
    const m = part.match(/^(\w+)\[(\d+)\]$/);
    if (!m) return null;
    const idx = Number.parseInt(m[2], 10);
    const child = cur.childNodes[idx];
    if (!child) return null;
    cur = child;
  }
  return cur;
}

function normalizeForMatch(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

function matchTokens(value: string): string[] {
  return normalizeForMatch(value)
    .replace(/[^a-z0-9]+/g, " ")
    .split(" ")
    .filter((token) => token.length >= 2);
}

function scoreTokenOverlap(haystack: string, needle: string): number {
  const hTokens = matchTokens(haystack);
  const nTokens = matchTokens(needle);
  if (hTokens.length < 3 || nTokens.length < 3) return 0;

  const hSet = new Set(hTokens);
  const matched = nTokens.filter((token) => hSet.has(token)).length;
  const coverage = matched / nTokens.length;
  if (coverage < 0.62) return 0;

  let ordered = 0;
  let hIndex = 0;
  for (const token of nTokens) {
    const foundAt = hTokens.indexOf(token, hIndex);
    if (foundAt === -1) continue;
    ordered += 1;
    hIndex = foundAt + 1;
  }
  const orderCoverage = ordered / nTokens.length;

  return 120 + Math.round(coverage * 240) + Math.round(orderCoverage * 140);
}

function scoreTextMatch(haystack: string, needle: string): number {
  const h = normalizeForMatch(haystack);
  const n = normalizeForMatch(needle);
  if (!n || !h) return 0;
  if (h === n) return 1000;
  if (h.includes(n)) {
    const coverage = n.length / h.length;
    return 400 + Math.round(coverage * 500);
  }
  // "needle contains haystack" is only trustworthy when the haystack (a field/column
  // label) is itself distinctive. Short, generic labels like "Name" or "Date" would
  // otherwise match any longer comment that happens to include that word, unlocking
  // unrelated fields. Require at least two word tokens for this branch.
  if (n.includes(h) && matchTokens(h).length >= 2) {
    const coverage = h.length / n.length;
    return 350 + Math.round(coverage * 400);
  }
  return scoreTokenOverlap(haystack, needle);
}

/** Whether highlighted comment text refers to a field/table label (or part of it). */
export function labelsMatch(haystack: string, needle: string): boolean {
  return scoreTextMatch(haystack, needle) > 0;
}

function fieldWrapper(el: HTMLElement | null): HTMLElement | null {
  if (!el) return null;
  return (
    (el.closest("[data-mvr-field]") as HTMLElement | null) ??
    (el.closest("[data-mvr-comment-anchor]") as HTMLElement | null) ??
    el
  );
}

function scrollContainer(el: HTMLElement): HTMLElement {
  const wrapped = fieldWrapper(el);
  if (wrapped) return wrapped;
  return el;
}

type ScoredAnchor = { el: HTMLElement; score: number };

function consider(candidates: ScoredAnchor[], el: HTMLElement | null, score: number): void {
  if (!el || score <= 0) return;
  const target = scrollContainer(el);
  const existing = candidates.find((c) => c.el === target);
  if (existing) {
    existing.score = Math.max(existing.score, score);
    return;
  }
  candidates.push({ el: target, score });
}

function fieldLabelFromElement(el: HTMLElement): string {
  return (
    el.getAttribute("data-mvr-field-label") ??
    el.getAttribute("data-mvr-comment-anchor") ??
    el.querySelector("label")?.textContent ??
    el.querySelector("[data-mvr-field-label]")?.textContent ??
    el.querySelector("span.font-medium, span.group-label")?.textContent ??
    ""
  ).trim();
}

/** Find the nearest form field id for a label, table header, or other marker. */
export function findAssociatedFieldKey(from: HTMLElement, root: HTMLElement): string | null {
  const direct = from.getAttribute("data-mvr-field");
  if (direct) return direct;

  const wrapped = from.closest("[data-mvr-field]") as HTMLElement | null;
  if (wrapped?.getAttribute("data-mvr-field")) {
    return wrapped.getAttribute("data-mvr-field");
  }

  const parent = from.parentElement;
  if (parent && root.contains(parent)) {
    const parentKey = parent.getAttribute("data-mvr-field");
    if (parentKey) return parentKey;
    const nested = parent.querySelector<HTMLElement>("[data-mvr-field]");
    if (nested?.getAttribute("data-mvr-field")) {
      return nested.getAttribute("data-mvr-field");
    }
  }

  let sib: Element | null = from.nextElementSibling;
  while (sib) {
    if (sib instanceof HTMLElement) {
      if (sib.hasAttribute("data-mvr-field")) {
        return sib.getAttribute("data-mvr-field");
      }
      const inner = sib.querySelector<HTMLElement>("[data-mvr-field]");
      if (inner?.getAttribute("data-mvr-field")) {
        return inner.getAttribute("data-mvr-field");
      }
    }
    sib = sib.nextElementSibling;
  }

  sib = from.previousElementSibling;
  while (sib) {
    if (sib instanceof HTMLElement) {
      if (sib.hasAttribute("data-mvr-field")) {
        return sib.getAttribute("data-mvr-field");
      }
    }
    sib = sib.previousElementSibling;
  }

  return null;
}

type TemplateFieldLike = {
  id: string;
  label?: string;
  type?: string;
  columns?: { id: string; label: string }[];
  unlockFieldIds?: string[];
};

function sectionNumberFromField(field: TemplateFieldLike): string | null {
  const match = field.id.match(/^section(\d+)$/i);
  return match?.[1] ?? null;
}

function sectionHeaderMatches(field: TemplateFieldLike, needle: string): boolean {
  const label = field.label ?? "";
  if (labelsMatch(label, needle)) return true;

  const sectionNumber = sectionNumberFromField(field);
  if (!sectionNumber) return false;

  const normalizedNeedle = normalizeForMatch(needle).replace(/^#\s*/, "");
  if (normalizedNeedle === sectionNumber) return true;
  if (!normalizedNeedle.startsWith(`${sectionNumber} `)) return false;

  const withoutNumber = normalizedNeedle.slice(sectionNumber.length).trim();
  return labelsMatch(label, withoutNumber);
}

function addTemplateFieldKeys(keys: Set<string>, field: TemplateFieldLike): void {
  keys.add(field.id);
  for (const id of field.unlockFieldIds ?? []) {
    keys.add(id);
  }
}

/** Map comments to field ids using template / registry metadata (no DOM required). */
export function resolveCommentedFieldKeysFromTemplate(
  comments: ReviewComment[],
  templateFields: TemplateFieldLike[],
): Set<string> {
  const keys = new Set<string>();
  if (!comments.length || !templateFields.length) return keys;

  for (const comment of comments) {
    const needle = (comment.highlighted_text || "").trim();
    if (!needle) continue;

    for (const field of templateFields) {
      if (sectionHeaderMatches(field, needle)) {
        addTemplateFieldKeys(keys, field);
        continue;
      }

      if (field.type === "table" && field.columns?.length) {
        const label = field.label ?? "";
        const tableLabel = normalizeForMatch(label);
        const n = normalizeForMatch(needle);
        for (const col of field.columns) {
          const colNorm = normalizeForMatch(col.label);
          // Only unlock a table for an unambiguous reference: an exact column-label
          // match, or a comment that names both the table and the column. A loose
          // substring match on a short column label (e.g. "Name") would otherwise
          // unlock the whole table for unrelated comments.
          const exactColumn = colNorm !== "" && n === colNorm;
          const tableAndColumn = tableLabel !== "" && n.includes(tableLabel) && n.includes(colNorm);
          if (exactColumn || tableAndColumn) {
            addTemplateFieldKeys(keys, field);
            break;
          }
        }
      }
    }
  }

  return keys;
}

/**
 * Find the best scroll target in the author report for an inline reviewer comment.
 */
export function resolveCommentAnchor(
  root: HTMLElement | null,
  comment: ReviewComment,
  options?: { allowDomPathFallback?: boolean },
): HTMLElement | null {
  if (!root) return null;
  const allowDomPathFallback = options?.allowDomPathFallback ?? true;

  // Deterministic anchor: if the comment stored the exact field id at creation, use it.
  const embeddedKey = extractFieldKeyFromDomPath(comment.dom_path);
  if (embeddedKey) {
    const el = root.querySelector<HTMLElement>(`[data-mvr-field="${escapeAttrValue(embeddedKey)}"]`);
    if (el) return el;
  }

  const needle = (comment.highlighted_text || "").trim();
  if (!needle) return null;

  const candidates: ScoredAnchor[] = [];

  for (const field of root.querySelectorAll<HTMLElement>("[data-mvr-field]")) {
    const labelText = fieldLabelFromElement(field);
    const labelScore = scoreTextMatch(labelText, needle);
    if (labelScore > 0) {
      consider(candidates, field, labelScore + 120);
      continue;
    }
    const blockScore = scoreTextMatch(field.textContent ?? "", needle);
    if (blockScore > 0) consider(candidates, field, blockScore);
  }

  for (const label of root.querySelectorAll<HTMLElement>("label, th, [data-mvr-field-label]")) {
    const score = scoreTextMatch(label.textContent ?? "", needle);
    if (score > 0) {
      const fk = findAssociatedFieldKey(label, root);
      const target = fk
        ? (root.querySelector(`[data-mvr-field="${fk}"]`) as HTMLElement | null)
        : label.parentElement;
      consider(candidates, target ?? label, score + 100);
    }
  }

  for (const anchor of root.querySelectorAll<HTMLElement>("[data-mvr-comment-anchor]")) {
    const score = scoreTextMatch(anchor.textContent ?? "", needle);
    if (score > 0) consider(candidates, anchor, score + 80);
  }

  for (const el of root.querySelectorAll<HTMLElement>("input, textarea, select")) {
    let value = "";
    if (el instanceof HTMLSelectElement) {
      value = el.options[el.selectedIndex]?.text ?? el.value;
    } else {
      value = (el as HTMLInputElement | HTMLTextAreaElement).value;
    }
    const score = scoreTextMatch(value, needle);
    if (score > 0) consider(candidates, el, score + 60);
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let textNode: Node | null;
  while ((textNode = walker.nextNode())) {
    const text = textNode.textContent ?? "";
    const score = scoreTextMatch(text, needle);
    if (score <= 0) continue;
    const parent = textNode.parentElement;
    if (!parent || !root.contains(parent)) continue;
    consider(candidates, parent, score);
  }

  if (allowDomPathFallback && comment.dom_path) {
    const node = resolveDomPath(root, comment.dom_path);
    if (node) {
      const el = node instanceof HTMLElement ? node : node.parentElement;
      const wrapped = fieldWrapper(el);
      if (wrapped && root.contains(wrapped)) {
        const pathScore = scoreTextMatch(wrapped.textContent ?? "", needle);
        consider(candidates, wrapped, pathScore > 0 ? pathScore - 50 : 40);
      }
    }
  }

  candidates.sort((a, b) => b.score - a.score);
  return candidates[0]?.el ?? null;
}

const FLASH_CLASS = "mvr-comment-target-flash";

/** Collect form field ids that have at least one inline reviewer comment. */
export function resolveCommentedFieldKeys(
  root: HTMLElement | null,
  comments: ReviewComment[],
  templateFields?: TemplateFieldLike[],
): Set<string> {
  const keys = new Set<string>();
  if (!comments.length) return keys;

  // Comments created after the deterministic-anchor change carry their exact field id in
  // dom_path. Trust those directly; only fall back to fuzzy matching for legacy comments
  // that predate the change (or whose field no longer exists).
  const fuzzyComments: ReviewComment[] = [];
  for (const comment of comments) {
    const embeddedKey = extractFieldKeyFromDomPath(comment.dom_path);
    if (embeddedKey && fieldKeyExists(embeddedKey, root, templateFields)) {
      keys.add(embeddedKey);
    } else {
      fuzzyComments.push(comment);
    }
  }

  if (!fuzzyComments.length) return keys;

  if (templateFields?.length) {
    for (const k of resolveCommentedFieldKeysFromTemplate(fuzzyComments, templateFields)) {
      keys.add(k);
    }
  }

  for (const comment of fuzzyComments) {
    const needle = (comment.highlighted_text || "").trim();
    if (!needle) continue;

    // For unlocking we must NOT use the dom_path fallback: dom_path was captured against
    // the reviewer's DOM and resolves to an unrelated node on the author's form, which
    // would unlock a field the reviewer never commented on.
    const anchor = resolveCommentAnchor(root, comment, { allowDomPathFallback: false });
    if (anchor) {
      const fieldKey =
        anchor.getAttribute("data-mvr-field") ??
        anchor.closest("[data-mvr-field]")?.getAttribute("data-mvr-field");
      if (fieldKey) keys.add(fieldKey);
    }

    if (!root) continue;

    // Broad label/anchor matching below can unlock several fields for a single comment
    // (e.g. when the highlighted text is long or a label appears as a substring of
    // another). When we have template metadata + a resolved anchor, that is precise
    // enough — skip the broad passes to avoid unlocking uncommented fields.
    if (templateFields?.length) continue;

    for (const el of root.querySelectorAll<HTMLElement>("[data-mvr-comment-anchor]")) {
      const anchorLabel = el.getAttribute("data-mvr-comment-anchor") || "";
      if (labelsMatch(anchorLabel, needle)) {
        const fk = el.getAttribute("data-mvr-field") ?? findAssociatedFieldKey(el, root);
        if (fk) keys.add(fk);
      }
    }

    for (const el of root.querySelectorAll<HTMLElement>("[data-mvr-field]")) {
      const labelText = fieldLabelFromElement(el);
      if (labelsMatch(labelText, needle)) {
        const fk = el.getAttribute("data-mvr-field");
        if (fk) keys.add(fk);
      }
    }

    for (const label of root.querySelectorAll<HTMLElement>("label, th")) {
      const text = label.textContent ?? "";
      if (!labelsMatch(text, needle)) continue;
      const fk = findAssociatedFieldKey(label, root);
      if (fk) keys.add(fk);
    }
  }

  return keys;
}

/** Smooth-scroll to the comment location and briefly highlight the target field. */
export function scrollToCommentAnchor(
  root: HTMLElement | null,
  comment: ReviewComment,
): HTMLElement | null {
  const anchor = resolveCommentAnchor(root, comment);
  if (!anchor) return null;

  anchor.scrollIntoView({ behavior: "smooth", block: "center" });
  anchor.classList.remove(FLASH_CLASS);
  void anchor.offsetWidth;
  anchor.classList.add(FLASH_CLASS);
  window.setTimeout(() => anchor.classList.remove(FLASH_CLASS), 2200);
  return anchor;
}

export const MVR_COMMENT_FLASH_STYLES = `
@keyframes mvrCommentFlash {
  0%, 100% { box-shadow: none; }
  15%, 55% { box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.55); }
}
.${FLASH_CLASS} {
  animation: mvrCommentFlash 2s ease;
  border-radius: 8px;
}
`;
