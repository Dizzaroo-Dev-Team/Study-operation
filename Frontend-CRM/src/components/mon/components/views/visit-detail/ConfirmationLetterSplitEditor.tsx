import {
  renderLetterTemplate,
  splitLetterTemplate,
  updateEditableSegment,
} from "./confirmationLetterModel";

type ConfirmationLetterSplitEditorProps = {
  template: string;
  values: Record<string, string>;
  requiresPharmacy: boolean;
  readOnly?: boolean;
  onTemplateChange: (next: string) => void;
};

export function ConfirmationLetterSplitEditor({
  template,
  values,
  requiresPharmacy,
  readOnly = false,
  onTemplateChange,
}: ConfirmationLetterSplitEditorProps) {
  const segments = splitLetterTemplate(template);

  return (
    <div className="conf-letter-editor">
      {segments.map((segment, i) => {
        if (segment.kind === "locked") {
          const rendered = renderLetterTemplate(segment.lines.join("\n"), values, requiresPharmacy);
          if (!rendered.trim()) return null;
          return (
            <div key={`locked-${i}`} className="conf-letter-editor-locked">
              <div className="conf-letter-editor-locked-label">Auto-filled from site profile &amp; visit schedule</div>
              <pre className="conf-letter-editor-locked-text">{rendered}</pre>
            </div>
          );
        }

        const text = segment.lines.join("\n");
        return (
          <div key={`editable-${segment.index}`} className="conf-letter-editor-editable">
            <label className="conf-letter-editor-editable-label" htmlFor={`letter-segment-${segment.index}`}>
              Editable content
            </label>
            <textarea
              id={`letter-segment-${segment.index}`}
              value={text}
              readOnly={readOnly}
              onChange={(e) => onTemplateChange(updateEditableSegment(template, segment.index, e.target.value))}
              aria-label={`Confirmation letter section ${segment.index + 1}`}
              className="conf-letter-editor-textarea"
            />
          </div>
        );
      })}
    </div>
  );
}
