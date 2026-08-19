/**
 * Template builder Preview tab — same vertical canvas layout as edit mode (no drag chrome).
 */
import type { MvrFieldDef } from "../../types/mvrTemplate";
import { MvrTemplateFieldPreview } from "./MvrTemplateFieldPreview";

export function MvrTemplateCanvasPreview({
  templateName,
  fields,
  usesStandardReportUi,
}: {
  templateName: string;
  fields: MvrFieldDef[];
  usesStandardReportUi?: boolean;
}) {
  return (
    <div>
      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
        <strong>Preview</strong> — matches the builder canvas layout. Nothing is saved.
        {usesStandardReportUi && (
          <span className="block mt-1 text-blue-800/90">
            On visit reports, built-in sections use the standard MVR form; fields you add here appear inline in that
            layout.
          </span>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-4 min-h-[320px]">
        <div
          style={{
            background: "#f8fafc",
            borderRadius: 12,
            border: "2px dashed #cbd5e1",
            padding: 12,
          }}
        >
          {fields.length === 0 ? (
            <p style={{ margin: 0, padding: 24, textAlign: "center", color: "#9ca3af", fontSize: 14 }}>
              No fields in this template yet.
            </p>
          ) : (
            fields.map((field) => (
              <div
                key={field.id}
                className="mb-4 p-4 border border-transparent rounded-md bg-white/60"
              >
                <MvrTemplateFieldPreview field={field} />
              </div>
            ))
          )}
        </div>
      </div>

      <p style={{ margin: "12px 0 0", fontSize: 12, color: "#6b7280" }}>
        Template: {templateName.trim() || "Untitled Template"}
      </p>
    </div>
  );
}
