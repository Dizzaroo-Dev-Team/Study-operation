/**
 * Read-only field mock — shared by the MVR template builder canvas and Preview tab.
 */
import type { MvrFieldDef } from "../../types/mvrTemplate";

/** Normalize label text (e.g. remove stray space before `?`). */
export function formatMvrTemplateFieldLabel(label: string): string {
  return label.replace(/\s+\?/g, "?").trim();
}

export function MvrTemplateFieldPreview({ field }: { field: MvrFieldDef }) {
  const inputBaseClass =
    "w-full bg-white border border-gray-300 rounded-md shadow-sm px-4 py-2 text-sm text-gray-900 placeholder:text-gray-400 disabled:bg-gray-50 disabled:cursor-not-allowed";
  const labelClass = "block text-sm font-medium text-gray-700 mb-1 pointer-events-none";
  const groupLabelClass = "block text-sm font-medium text-gray-700 mb-2 pointer-events-none";

  const displayLabel = formatMvrTemplateFieldLabel(field.label);

  const checkAsterisk =
    field.required && field.type !== "section" ? (
      <span className="text-red-500 ml-1">*</span>
    ) : null;

  const commonLabel = (
    <label className={labelClass}>
      {displayLabel}
      {checkAsterisk}
    </label>
  );

  if (field.type === "section") {
    return (
      <div className="pb-4">
        <h3 className="text-base font-semibold text-gray-900 mb-2 pointer-events-none">{displayLabel}</h3>
        {field.content && (
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap pointer-events-none">
            {field.content}
          </div>
        )}
      </div>
    );
  }

  if (field.type === "text") {
    return (
      <div>
        {commonLabel}
        <input type="text" disabled placeholder={field.placeholder || ""} className={inputBaseClass} />
      </div>
    );
  }

  if (field.type === "textarea") {
    return (
      <div>
        {commonLabel}
        <textarea
          disabled
          placeholder={field.placeholder || ""}
          className={`${inputBaseClass} resize-none min-h-[80px]`}
        />
      </div>
    );
  }

  if (field.type === "number") {
    return (
      <div>
        {commonLabel}
        <input type="number" disabled placeholder={field.placeholder || ""} className={inputBaseClass} />
      </div>
    );
  }

  if (field.type === "date") {
    return (
      <div>
        {commonLabel}
        <input type="date" disabled className={inputBaseClass} />
      </div>
    );
  }

  if (field.type === "checkbox") {
    return (
      <div className="flex items-start gap-3 pt-0.5">
        <input type="checkbox" disabled className="mt-1 h-4 w-4 shrink-0 rounded border-gray-300" />
        <span className="text-sm font-medium text-gray-900 pointer-events-none leading-snug">
          {displayLabel}
          {checkAsterisk}
        </span>
      </div>
    );
  }

  if (field.type === "radio" || field.type === "select" || field.type === "multiselect") {
    const rawOpts = Array.isArray(field.options)
      ? field.options.filter((o) => typeof o === "string" && o.trim() !== "")
      : [];
    const opts = rawOpts.length > 0 ? rawOpts : ["Yes", "No", "N/A"];

    if (field.type === "radio") {
      return (
        <div>
          <span className={groupLabelClass}>
            {displayLabel}
            {checkAsterisk}
          </span>
          <div className="flex flex-wrap gap-4 mt-1 pointer-events-none">
            {opts.map((o) => (
              <label key={o} className="flex items-center gap-2 text-sm text-gray-900 cursor-default opacity-70">
                <input type="radio" disabled className="h-4 w-4 shrink-0 border-gray-300" />
                <span>{o}</span>
              </label>
            ))}
          </div>
        </div>
      );
    }

    if (field.type === "multiselect") {
      return (
        <div>
          <span className={groupLabelClass}>
            {displayLabel}
            {checkAsterisk}
          </span>
          <div className="flex flex-wrap gap-4 mt-1 pointer-events-none">
            {opts.map((o) => (
              <label key={o} className="flex items-center gap-2 text-sm text-gray-900 cursor-default opacity-70">
                <input type="checkbox" disabled className="h-4 w-4 shrink-0 rounded border-gray-300" />
                <span>{o}</span>
              </label>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div>
        {commonLabel}
        <select disabled className={inputBaseClass}>
          <option>{field.placeholder || "Choose…"}</option>
          {opts.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </select>
        {/* A disabled collapsed select hides its options — list them so builders
            can see what CRAs will get without opening Field properties. */}
        <div className="mt-1 text-xs text-gray-500 pointer-events-none">
          Options: {opts.join(" · ")}
        </div>
      </div>
    );
  }

  if (field.type === "table") {
    const cols = field.columns?.length ? field.columns : [{ id: "col_a", label: "Column A" }];
    return (
      <div>
        <span className={groupLabelClass}>
          {displayLabel}
          {checkAsterisk}
        </span>
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white pointer-events-none">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th
                    key={c.id}
                    className="bg-gray-50 px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider border-b border-gray-200"
                  >
                    {formatMvrTemplateFieldLabel(c.label)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-gray-100 last:border-b-0">
                {cols.map((c) => (
                  <td key={c.id} className="px-4 py-2 align-middle">
                    <div className="h-8 w-full bg-gray-50 border border-gray-100 rounded-md" />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return null;
}
