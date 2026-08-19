import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  FileStack,
  LayoutTemplate,
  Pencil,
  Plus,
  Radio,
  Trash2,
} from "lucide-react";
import {
  activateMvrTemplate,
  deleteAllMvrTemplates,
  deleteMvrTemplate,
  listMvrTemplates,
} from "../../services/monitorService";
import type { MvrTemplateDto } from "../../types/mvrTemplate";

function formatModified(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function statusLabel(t: MvrTemplateDto): string {
  const ls = t.lifecycleStatus ?? "published";
  if (ls === "draft") return "Draft";
  return "Saved";
}

type Props = {
  showToast: (msg: string, type?: string) => void;
  organizationId?: string;
  /** Open blank builder — no API call until user saves. */
  onOpenBlankBuilder: () => void;
  /** Open builder pre-filled from standard layout — no API until user saves. */
  onOpenLegacyLayoutBuilder: () => void;
  onEdit: (templateId: string) => void;
};

export function MvrTemplateManagerView({
  showToast,
  organizationId = "default",
  onOpenBlankBuilder,
  onOpenLegacyLayoutBuilder,
  onEdit,
}: Props) {
  const [items, setItems] = useState<MvrTemplateDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
  const [activatingId, setActivatingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { items: rows } = await listMvrTemplates(organizationId);
      setItems(rows);
    } catch {
      showToast("Could not load templates", "error");
    } finally {
      setLoading(false);
    }
  }, [organizationId, showToast]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreateNew = () => {
    onOpenBlankBuilder();
  };

  const handleDelete = async (t: MvrTemplateDto) => {
    const title = t.name?.trim() || "Untitled template";
    const liveWarn = t.isActive
      ? "\n\nThis template is marked Live for legacy flows. Confirm it is no longer needed before deleting."
      : "";
    if (
      !window.confirm(
        `Delete "${title}" (v${t.version})? This cannot be undone.${liveWarn}`,
      )
    ) {
      return;
    }
    setDeletingId(t.id);
    try {
      await deleteMvrTemplate(t.id);
      showToast("Template deleted.", "success");
      await load();
    } catch {
      showToast("Could not delete template", "error");
    } finally {
      setDeletingId(null);
    }
  };

  const handleCreateFromLegacyLayout = () => {
    onOpenLegacyLayoutBuilder();
  };

  const handleSetLive = async (t: MvrTemplateDto) => {
    const title = t.name?.trim() || "Untitled template";
    if ((t.lifecycleStatus ?? "published") === "draft") {
      showToast("Save the template first (Edit → Save, not Save draft), then set it as Live.", "error");
      return;
    }
    if (t.isActive) return;
    if (
      !window.confirm(
        `Set "${title}" (v${t.version}) as the Live template?\n\nVisit reports will use this layout. Any other Live template will be replaced.`,
      )
    ) {
      return;
    }
    setActivatingId(t.id);
    try {
      await activateMvrTemplate(t.id);
      showToast(`"${title}" is now Live for visit reports.`, "success");
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      showToast(
        typeof detail === "string" && detail ? detail : "Could not set template as Live",
        "error",
      );
    } finally {
      setActivatingId(null);
    }
  };

  const handleDeleteAll = async () => {
    if (items.length === 0) return;
    const n = items.length;
    const hasLive = items.some((t) => t.isActive);
    const liveNote = hasLive
      ? "\n\nThis includes a template marked Live for legacy flows."
      : "";
    if (
      !window.confirm(
        `Delete ALL ${n} template(s) for this organization? This cannot be undone.${liveNote}`,
      )
    ) {
      return;
    }
    setDeletingAll(true);
    try {
      const res = await deleteAllMvrTemplates(organizationId);
      const c = typeof res.deleted_count === "number" ? res.deleted_count : n;
      showToast(`Deleted ${c} template(s).`, "success");
      await load();
    } catch {
      showToast("Could not delete templates", "error");
    } finally {
      setDeletingAll(false);
    }
  };

  const liveTemplate = items.find((t) => t.isActive);

  return (
    <div className="fade-in max-w-5xl mx-auto py-8 px-1">
      {/* Page header */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-5 mb-8">
        <div className="flex items-start gap-4">
          <div className="hidden sm:flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-600/20">
            <FileStack className="h-5 w-5" strokeWidth={2} />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight m-0">MVR Templates</h1>
            <p className="text-sm text-slate-500 mt-1.5 m-0 max-w-xl leading-relaxed">
              Design the layout of your monitoring visit reports. Save a template, then set it{" "}
              <span className="font-medium text-slate-700">Live</span> — every visit report uses the Live
              template, and only one can be Live at a time.
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-2.5 shrink-0">
          <button
            type="button"
            disabled={deletingAll || loading}
            onClick={() => handleCreateNew()}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 text-white text-sm font-semibold px-4 py-2.5 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 shadow-sm shadow-blue-600/25 transition-colors"
          >
            <Plus className="h-4 w-4" strokeWidth={2.5} />
            New template
          </button>
          <button
            type="button"
            disabled={deletingAll || loading}
            onClick={() => handleCreateFromLegacyLayout()}
            title="Pre-fill all sections to match the built-in monitoring visit report form"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white text-slate-700 text-sm font-semibold px-4 py-2.5 hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 shadow-sm transition-colors"
          >
            <LayoutTemplate className="h-4 w-4 text-slate-500" strokeWidth={2} />
            Standard layout
          </button>
        </div>
      </div>

      {/* Live template callout */}
      {!loading && liveTemplate ? (
        <div className="mb-5 flex items-center gap-3 rounded-xl border border-blue-200/80 bg-gradient-to-r from-blue-50 to-indigo-50/60 px-4 py-3">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-60" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-600" />
          </span>
          <p className="m-0 text-sm text-slate-700">
            <span className="font-semibold text-slate-900">{liveTemplate.name?.trim() || "Untitled template"}</span>{" "}
            <span className="text-slate-500">v{liveTemplate.version}</span> is currently live on all visit reports.
          </p>
        </div>
      ) : null}

      {/* Templates card */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200/80 bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <h2 className="text-sm font-semibold text-slate-800 m-0">Templates</h2>
            {!loading ? (
              <span className="inline-flex items-center rounded-full bg-slate-200/70 px-2 py-0.5 text-xs font-semibold text-slate-600 tabular-nums">
                {items.length}
              </span>
            ) : null}
          </div>
          {items.length > 0 ? (
            <button
              type="button"
              disabled={deletingAll || loading}
              onClick={() => void handleDeleteAll()}
              className="inline-flex items-center gap-1.5 rounded-md text-xs font-semibold text-slate-500 hover:text-red-600 disabled:opacity-50 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" strokeWidth={2} />
              {deletingAll ? "Deleting…" : "Delete all"}
            </button>
          ) : null}
        </div>

        {loading ? (
          <div className="divide-y divide-slate-100">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-4 animate-pulse">
                <div className="h-4 w-48 rounded bg-slate-200/80" />
                <div className="h-4 w-12 rounded bg-slate-100" />
                <div className="ml-auto h-4 w-40 rounded bg-slate-100" />
                <div className="h-6 w-20 rounded-full bg-slate-100" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="px-8 py-16 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
              <LayoutTemplate className="h-6 w-6" strokeWidth={1.75} />
            </div>
            <h3 className="text-base font-semibold text-slate-800 m-0">No templates yet</h3>
            <p className="mx-auto mt-1.5 mb-6 max-w-md text-sm text-slate-500 leading-relaxed">
              Start from a blank canvas, or use the standard layout to begin with the same sections as the
              built-in visit report form.
            </p>
            <div className="flex items-center justify-center gap-2.5">
              <button
                type="button"
                onClick={() => handleCreateNew()}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 text-white text-sm font-semibold px-4 py-2 hover:bg-blue-700 shadow-sm shadow-blue-600/25 transition-colors"
              >
                <Plus className="h-4 w-4" strokeWidth={2.5} />
                New template
              </button>
              <button
                type="button"
                onClick={() => handleCreateFromLegacyLayout()}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white text-slate-700 text-sm font-semibold px-4 py-2 hover:bg-slate-50 transition-colors"
              >
                <LayoutTemplate className="h-4 w-4 text-slate-500" strokeWidth={2} />
                Standard layout
              </button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-200/80">
                  <th className="px-5 py-3">Template</th>
                  <th className="px-4 py-3 w-24">Version</th>
                  <th className="px-4 py-3 min-w-[170px]">Last modified</th>
                  <th className="px-4 py-3 min-w-[150px]">Status</th>
                  <th className="px-5 py-3 min-w-[220px] text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((t) => {
                  const isDraft = (t.lifecycleStatus ?? "published") === "draft";
                  return (
                    <tr
                      key={t.id}
                      className={`group transition-colors ${
                        t.isActive ? "bg-blue-50/40 hover:bg-blue-50/70" : "hover:bg-slate-50/80"
                      }`}
                    >
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          {t.isActive ? (
                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" title="Live template" />
                          ) : null}
                          <span className="font-medium text-slate-900">{t.name?.trim() || "Untitled template"}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-slate-500 tabular-nums text-xs font-medium">v{t.version}</td>
                      <td className="px-4 py-3.5 text-slate-500 whitespace-nowrap text-xs">
                        {formatModified(t.updatedAt)}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="inline-flex items-center gap-1.5 flex-wrap">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                              isDraft
                                ? "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200/70"
                                : "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200/70"
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${isDraft ? "bg-amber-500" : "bg-emerald-500"}`}
                            />
                            {statusLabel(t)}
                          </span>
                          {t.isActive ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide text-blue-700 bg-blue-100/70 ring-1 ring-inset ring-blue-200/70">
                              <Radio className="h-3 w-3" strokeWidth={2.5} />
                              Live
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <span className="inline-flex items-center justify-end gap-1.5 flex-wrap">
                          {!t.isActive && !isDraft ? (
                            <button
                              type="button"
                              disabled={activatingId === t.id || deletingAll}
                              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50/50 px-2.5 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 hover:border-emerald-300 disabled:opacity-50 transition-colors"
                              onClick={() => void handleSetLive(t)}
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2} />
                              {activatingId === t.id ? "Setting…" : "Set live"}
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900 transition-colors"
                            onClick={() => onEdit(t.id)}
                          >
                            <Pencil className="h-3.5 w-3.5" strokeWidth={2} />
                            Edit
                          </button>
                          <button
                            type="button"
                            disabled={deletingId === t.id || deletingAll || activatingId === t.id}
                            title="Delete template"
                            className="inline-flex items-center justify-center rounded-md border border-transparent p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 hover:border-red-100 disabled:opacity-50 transition-colors"
                            onClick={() => void handleDelete(t)}
                          >
                            <Trash2 className="h-4 w-4" strokeWidth={2} />
                            <span className="sr-only">{deletingId === t.id ? "Deleting…" : "Delete"}</span>
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
