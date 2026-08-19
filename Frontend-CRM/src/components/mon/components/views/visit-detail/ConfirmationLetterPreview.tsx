export type LetterHeaderField = { label: string; value: string };
export type LetterListItem = { text: string; indent: number };
export type LetterSection = { title: string; intro?: string; items: LetterListItem[] };
export type ParsedConfirmationLetter = {
  headerFields: LetterHeaderField[];
  salutation: string;
  introParagraphs: string[];
  sections: LetterSection[];
  acknowledgment?: { title: string; body: string };
  signatureLines: string[];
};

const SEPARATOR_RE = /^[-=]{4,}\s*$/;
const SECTION_RE = /^(\d+)\)\s+(.+)$/;
const BULLET_RE = /^(\s*)(?:•|-)\s+(.+)$/;

function isHeaderFieldLine(line: string): boolean {
  const t = line.trim();
  if (!t || SEPARATOR_RE.test(t)) return false;
  if (/^Dear\s/i.test(t)) return false;
  if (SECTION_RE.test(t)) return false;
  if (BULLET_RE.test(line)) return false;
  return /^[^:]+:\s*.+$/.test(t);
}

function parseHeaderField(line: string): LetterHeaderField {
  const idx = line.indexOf(":");
  if (idx < 0) return { label: "", value: line.trim() };
  return {
    label: line.slice(0, idx).trim(),
    value: line.slice(idx + 1).trim(),
  };
}

export function parseConfirmationLetter(text: string): ParsedConfirmationLetter {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const headerFields: LetterHeaderField[] = [];
  const introParagraphs: string[] = [];
  const sections: LetterSection[] = [];
  const signatureLines: string[] = [];

  let salutation = "";
  let acknowledgment: ParsedConfirmationLetter["acknowledgment"];
  let phase: "header" | "body" | "signature" = "header";
  let paragraphBuf: string[] = [];
  let currentSection: LetterSection | null = null;

  const flushParagraph = () => {
    if (!paragraphBuf.length) return;
    const p = paragraphBuf.join(" ").trim();
    paragraphBuf = [];
    if (!p) return;
    if (currentSection && !currentSection.intro && currentSection.items.length === 0) {
      currentSection.intro = p;
    } else if (!salutation && phase === "body" && !currentSection && sections.length === 0) {
      introParagraphs.push(p);
    } else if (currentSection) {
      currentSection.items.push({ text: p, indent: 0 });
    } else {
      introParagraphs.push(p);
    }
  };

  const closeSection = () => {
    flushParagraph();
    if (currentSection) {
      sections.push(currentSection);
      currentSection = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      continue;
    }
    if (SEPARATOR_RE.test(trimmed)) continue;

    if (phase === "signature") {
      signatureLines.push(trimmed);
      continue;
    }

    if (/^Sincerely,?\s*$/i.test(trimmed)) {
      closeSection();
      phase = "signature";
      signatureLines.push("Sincerely,");
      continue;
    }

    if (phase === "header") {
      if (/^Dear\s/i.test(trimmed)) {
        salutation = trimmed;
        phase = "body";
        continue;
      }
      if (isHeaderFieldLine(trimmed)) {
        headerFields.push(parseHeaderField(trimmed));
        continue;
      }
      phase = "body";
    }

    if (/^Dear\s/i.test(trimmed)) {
      closeSection();
      salutation = trimmed;
      continue;
    }

    if (/^Acknowledgment\s*$/i.test(trimmed)) {
      closeSection();
      acknowledgment = { title: "Acknowledgment", body: "" };
      continue;
    }

    const secMatch = trimmed.match(SECTION_RE);
    if (secMatch) {
      closeSection();
      currentSection = { title: secMatch[2].trim(), items: [] };
      continue;
    }

    const bulletMatch = line.match(BULLET_RE);
    if (bulletMatch) {
      flushParagraph();
      const indent = Math.floor(bulletMatch[1].length / 2);
      const item = { text: bulletMatch[2].trim(), indent };
      if (currentSection) currentSection.items.push(item);
      else introParagraphs.push(`• ${item.text}`);
      continue;
    }

    if (acknowledgment && !currentSection) {
      acknowledgment.body = acknowledgment.body
        ? `${acknowledgment.body} ${trimmed}`
        : trimmed;
      continue;
    }

    paragraphBuf.push(trimmed);
  }

  closeSection();
  flushParagraph();

  return {
    headerFields,
    salutation,
    introParagraphs,
    sections,
    acknowledgment,
    signatureLines,
  };
}

const SECTION_ACCENTS: Record<string, string> = {
  "visit logistics": "#2563eb",
  "personnel availability": "#7c3aed",
  "visit agenda and objectives": "#0d9488",
  "pre-visit preparation": "#d97706",
};

function sectionAccent(title: string): string {
  const key = title.toLowerCase();
  for (const [k, color] of Object.entries(SECTION_ACCENTS)) {
    if (key.includes(k)) return color;
  }
  return "#475569";
}

function SectionBlock({ section }: { section: LetterSection }) {
  const accent = sectionAccent(section.title);
  return (
    <section className="conf-section" style={{ borderLeftColor: accent }}>
      <h3 className="conf-section-title" style={{ color: accent }}>
        {section.title}
      </h3>
      {section.intro && <p className="conf-paragraph">{section.intro}</p>}
      {section.items.length > 0 && (
        <ul className="conf-list">
          {section.items.map((item, i) => (
            <li
              key={`${i}-${item.text.slice(0, 24)}`}
              className="conf-list-item"
              style={{ marginLeft: item.indent ? item.indent * 16 : 0 }}
            >
              {item.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export type ConfirmationLetterEnvelope = {
  /** CRA / sender line (not repeated in letter body header). */
  fromLine?: string;
  /** Subject line (not repeated in letter body header). */
  reLine?: string;
};

function LetterBanner({ envelope }: { envelope?: ConfirmationLetterEnvelope }) {
  const fromLine = envelope?.fromLine?.trim();
  const reLine = envelope?.reLine?.trim();
  return (
    <header className="conf-letter-banner">
      <div className="conf-letter-banner-icon" aria-hidden="true">
        <i className="ti ti-mail-forward" />
      </div>
      <div>
        <h2 className="conf-letter-title">Confirmation of Monitoring Visit</h2>
        <p className="conf-letter-subtitle">Formal notice to the investigative site</p>
        {(fromLine || reLine) && (
          <div className="conf-envelope-lines">
            {fromLine && (
              <p className="conf-envelope-line">
                <span className="conf-envelope-label">From</span>
                <span>{fromLine}</span>
              </p>
            )}
            {reLine && (
              <p className="conf-envelope-line">
                <span className="conf-envelope-label">Re</span>
                <span>{reLine}</span>
              </p>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

export function ConfirmationLetterPreview({
  content,
  envelope,
}: {
  content: string;
  envelope?: ConfirmationLetterEnvelope;
}) {
  const parsed = parseConfirmationLetter(content);

  return (
    <article className="conf-letter">
      <LetterBanner envelope={envelope} />

      {parsed.headerFields.length > 0 && (
        <div className="conf-header-grid">
          {parsed.headerFields.map((f) => (
            <div key={`${f.label}-${f.value}`} className="conf-header-cell">
              <span className="conf-header-label">{f.label}</span>
              <span className="conf-header-value">{f.value || "—"}</span>
            </div>
          ))}
        </div>
      )}

      {parsed.salutation && <p className="conf-salutation">{parsed.salutation}</p>}

      {parsed.introParagraphs.map((p, i) => (
        <p key={`intro-${i}`} className="conf-paragraph">
          {p}
        </p>
      ))}

      {parsed.sections.map((sec) => (
        <SectionBlock key={sec.title} section={sec} />
      ))}

      {parsed.acknowledgment && (
        <section className="conf-section conf-ack" style={{ borderLeftColor: "#059669" }}>
          <h3 className="conf-section-title" style={{ color: "#059669" }}>
            {parsed.acknowledgment.title}
          </h3>
          <p className="conf-paragraph">{parsed.acknowledgment.body}</p>
        </section>
      )}

      {parsed.signatureLines.length > 0 && (
        <footer className="conf-signature">
          {parsed.signatureLines.map((line, i) => (
            <p
              key={`sig-${i}`}
              className={
                i === 0
                  ? "conf-signature-lead"
                  : i === 1
                    ? "conf-signature-name"
                    : "conf-signature-line"
              }
            >
              {line}
            </p>
          ))}
        </footer>
      )}
    </article>
  );
}

function envelopeLinesHtml(envelope: ConfirmationLetterEnvelope | undefined, esc: (s: string) => string): string {
  const fromLine = envelope?.fromLine?.trim();
  const reLine = envelope?.reLine?.trim();
  if (!fromLine && !reLine) return "";
  const rows = [
    fromLine
      ? `<p style="margin:4px 0 0;font-size:12px;color:#475569;"><span style="font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-right:8px;">From</span>${esc(fromLine)}</p>`
      : "",
    reLine
      ? `<p style="margin:4px 0 0;font-size:12px;color:#475569;"><span style="font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#64748b;margin-right:8px;">Re</span>${esc(reLine)}</p>`
      : "",
  ].join("");
  return rows;
}

/** HTML string for client-side PDF export (html2pdf). */
export function buildConfirmationLetterHtml(
  content: string,
  envelope?: ConfirmationLetterEnvelope,
): string {
  const p = parseConfirmationLetter(content);
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const headerHtml =
    p.headerFields.length > 0
      ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 20px;margin-bottom:24px;padding:16px 18px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
      ${p.headerFields
        .map(
          (f) =>
            `<div><div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;margin-bottom:4px;">${esc(f.label)}</div>
            <div style="font-size:13px;color:#1e293b;font-weight:500;">${esc(f.value)}</div></div>`
        )
        .join("")}
    </div>`
      : "";

  const sectionsHtml = p.sections
    .map((sec) => {
      const accent = sectionAccent(sec.title);
      const items = sec.items
        .map(
          (it) =>
            `<li style="margin:0 0 8px ${it.indent * 12}px;padding-left:4px;color:#334155;font-size:13px;line-height:1.65;">${esc(it.text)}</li>`
        )
        .join("");
      return `<div style="margin-bottom:22px;padding:16px 18px 14px;border-left:4px solid ${accent};background:#fff;border:1px solid #e2e8f0;border-radius:0 10px 10px 0;">
        <h3 style="margin:0 0 10px;font-size:14px;font-weight:700;color:${accent};">${esc(sec.title)}</h3>
        ${sec.intro ? `<p style="margin:0 0 12px;font-size:13px;line-height:1.7;color:#475569;">${esc(sec.intro)}</p>` : ""}
        ${items ? `<ul style="margin:0;padding-left:20px;">${items}</ul>` : ""}
      </div>`;
    })
    .join("");

  const introHtml = p.introParagraphs
    .map((t) => `<p style="margin:0 0 14px;font-size:13px;line-height:1.75;color:#475569;">${esc(t)}</p>`)
    .join("");

  const ackHtml = p.acknowledgment
    ? `<div style="margin-bottom:22px;padding:16px 18px;border-left:4px solid #059669;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:0 10px 10px 0;">
        <h3 style="margin:0 0 8px;font-size:14px;font-weight:700;color:#059669;">${esc(p.acknowledgment.title)}</h3>
        <p style="margin:0;font-size:13px;line-height:1.7;color:#475569;">${esc(p.acknowledgment.body)}</p>
      </div>`
    : "";

  const sigHtml =
    p.signatureLines.length > 0
      ? `<div style="margin-top:32px;padding-top:20px;border-top:1px solid #e2e8f0;">
        ${p.signatureLines
          .map((line, i) => {
            const style =
              i === 0
                ? "margin:0 0 12px;font-size:13px;color:#64748b;"
                : i === 1
                  ? "margin:0 0 4px;font-size:15px;font-weight:700;color:#1e293b;"
                  : "margin:0 0 4px;font-size:13px;color:#475569;";
            return `<p style="${style}">${esc(line)}</p>`;
          })
          .join("")}
      </div>`
      : "";

  return `
    <div style="font-family:'Segoe UI',system-ui,sans-serif;color:#1e293b;">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:28px;padding-bottom:20px;border-bottom:2px solid #e2e8f0;">
        <div style="width:48px;height:48px;border-radius:10px;background:linear-gradient(135deg,#0ea5e9,#6366f1);display:flex;align-items:center;justify-content:center;color:#fff;font-size:22px;">✉</div>
        <div>
          <div style="font-size:20px;font-weight:700;color:#0f172a;">Confirmation of Monitoring Visit</div>
          <div style="font-size:12px;color:#64748b;margin-top:4px;">Formal notice to the investigative site</div>
          ${envelopeLinesHtml(envelope, esc)}
        </div>
      </div>
      ${headerHtml}
      ${p.salutation ? `<p style="margin:0 0 16px;font-size:14px;font-weight:600;color:#1e293b;">${esc(p.salutation)}</p>` : ""}
      ${introHtml}
      ${sectionsHtml}
      ${ackHtml}
      ${sigHtml}
    </div>
  `;
}
