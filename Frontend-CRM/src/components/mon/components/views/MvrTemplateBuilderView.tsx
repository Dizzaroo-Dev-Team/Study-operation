import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode, type ElementType } from "react";
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  closestCenter,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AlignLeft,
  ArrowLeft,
  CalendarIcon,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  Copy,
  Eye,
  FileText,
  GripVertical,
  Hash,
  LayoutTemplate,
  ListChecks,
  Radio,
  RotateCcw,
  Table,
  Trash2,
  Type,
} from "lucide-react";
import { Btn } from "../ui";
import {
  activateMvrTemplate,
  duplicateMvrTemplate,
  fetchMvrTemplateById,
  listMvrTemplates,
  patchMvrTemplate,
  saveMvrTemplate,
} from "../../services/monitorService";
import type { MvrFieldDef, MvrFieldType, MvrTableColumn, MvrTemplateDto } from "../../types/mvrTemplate";
import {
  getLegacyStaticMvrTemplateSchema,
  isLegacyStaticMvrTemplateSchema,
  LEGACY_STATIC_MVR_TEMPLATE_LAYOUT,
  LEGACY_STATIC_MVR_TEMPLATE_DEFAULT_NAME,
} from "../../legacyStaticMvrTemplateSchema";
import { MvrTemplateCanvasPreview } from "./MvrTemplateCanvasPreview";
import { MvrTemplateFieldPreview } from "./MvrTemplateFieldPreview";

const CANVAS_ID = "mvr-canvas-drop";

export type MvrTemplateBuilderSession =
  | { kind: "edit"; templateId: string }
  | { kind: "new"; preset: "blank" | "legacy" };

function snapshotState(name: string, fields: MvrFieldDef[]): string {
  return JSON.stringify({ name: name.trim(), fields });
}

function normalizeFieldsFromTemplate(schema: MvrTemplateDto["schema"] | undefined): MvrFieldDef[] {
  const raw = schema?.fields;
  return Array.isArray(raw) ? raw.map((f) => ({ ...f })) : [];
}

const TOOLBOX: { type: MvrFieldType; label: string; icon: ElementType }[] = [
  { type: "section", label: "Section / instructions", icon: FileText },
  { type: "text", label: "Short text", icon: Type },
  { type: "textarea", label: "Long text", icon: AlignLeft },
  { type: "number", label: "Number", icon: Hash },
  { type: "radio", label: "Radio (Y/N/N/A)", icon: CheckCircle2 },
  { type: "select", label: "Dropdown", icon: ChevronDown },
  { type: "multiselect", label: "Multi-select", icon: ListChecks },
  { type: "checkbox", label: "Checkbox", icon: CheckSquare },
  { type: "date", label: "Date", icon: CalendarIcon },
  { type: "table", label: "Dynamic table", icon: Table },
];

function newFieldId(): string {
  // crypto.randomUUID is unavailable in insecure (non-HTTPS) contexts.
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `fld_${uuid.replace(/-/g, "").slice(0, 12)}`;
}

function createField(type: MvrFieldType): MvrFieldDef {
  const id = newFieldId();
  switch (type) {
    case "section":
      return { id, type, label: "Section title", content: "Instruction text for CRAs." };
    case "text":
      return { id, type, label: "Short text", placeholder: "", required: false };
    case "textarea":
      return { id, type, label: "Long text", placeholder: "", required: false };
    case "number":
      return { id, type, label: "Number", placeholder: "", required: false };
    case "checkbox":
      return { id, type, label: "I confirm / acknowledge", required: false };
    case "date":
      return { id, type, label: "Date", required: false };
    case "radio":
      return {
        id,
        type: "radio",
        label: "Choice",
        options: ["Yes", "No", "N/A"],
        required: false,
      };
    case "select":
      return {
        id,
        type: "select",
        label: "Dropdown",
        options: ["Yes", "No", "N/A"],
        placeholder: "",
        required: false,
      };
    case "multiselect":
      return {
        id,
        type: "multiselect",
        label: "Multi-select",
        options: ["Option A", "Option B", "Option C"],
        required: false,
      };
    case "table":
      return {
        id,
        type: "table",
        label: "Table",
        columns: [
          { id: "col_a", label: "Column A" },
          { id: "col_b", label: "Column B" },
        ],
        required: false,
      };
    default:
      return { id, type: "text", label: "Field", required: false };
  }
}

function ToolboxChip({
  type,
  label,
  icon: Icon,
  onAdd,
}: {
  type: MvrFieldType;
  label: string;
  icon: ElementType;
  onAdd: (type: MvrFieldType) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `toolbox-${type}`,
    data: { source: "toolbox" as const, fieldType: type },
  });
  return (
    <button
      type="button"
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onKeyDown={(e) => {
        // Keyboard path: only PointerSensor is configured, so drag is
        // mouse/touch-only. Enter/Space appends the field to the canvas.
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAdd(type);
        }
      }}
      className={`flex items-center gap-2.5 w-full px-3 py-2 text-sm font-medium text-slate-700 bg-white border rounded-lg shadow-sm hover:bg-slate-50 hover:border-slate-300 hover:shadow transition-all cursor-grab mb-2 ${
        isDragging ? "border-blue-500 bg-blue-50 ring-2 ring-blue-500/20" : "border-slate-200"
      }`}
    >
      <Icon className="h-4 w-4 text-slate-400" />
      <span>{label}</span>
    </button>
  );
}

function CanvasDropShell({ children, showDragChrome }: { children: ReactNode; showDragChrome: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: CANVAS_ID });
  const pulse = showDragChrome && isOver;
  return (
    <div
      ref={setNodeRef}
      style={{
        minHeight: 320,
        borderRadius: 12,
        border: `2px dashed ${pulse ? "#2563eb" : isOver ? "#93c5fd" : "#cbd5e1"}`,
        background: pulse ? "#eff6ff" : isOver ? "#f8fafc" : "#f8fafc",
        padding: 12,
        transition: "border-color .12s ease, background .12s ease, box-shadow .12s ease",
        boxShadow: pulse ? "inset 0 0 0 1px rgba(37,99,235,0.08)" : "none",
      }}
    >
      {children}
    </div>
  );
}

function SortableFieldRow({
  field,
  selected,
  showDropBefore,
  showDropAfter,
  onSelect,
  onDelete,
}: {
  field: MvrFieldDef;
  selected: boolean;
  showDropBefore: boolean;
  showDropAfter: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: field.id,
    data: { source: "field" as const },
  });
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div ref={setNodeRef} style={style} className="mb-4 relative group cursor-pointer" onClick={onSelect}>
      {showDropBefore && (
        <div
          role="presentation"
          className="absolute -top-2 left-0 right-0 h-1 rounded bg-blue-600 z-10 shadow-[0_0_0_2px_rgba(26,86,219,0.15)]"
        />
      )}
      {showDropAfter && (
        <div
          role="presentation"
          className="absolute -bottom-2 left-0 right-0 h-1 rounded bg-blue-600 z-10 shadow-[0_0_0_2px_rgba(26,86,219,0.15)]"
        />
      )}
      <div
        className={`relative rounded-md transition-all ${
          selected
            ? "ring-2 ring-blue-500 bg-blue-50/20 p-4 border border-transparent"
            : "p-4 border border-transparent hover:border-gray-300 hover:border-dashed"
        } ${isDragging ? "opacity-30" : ""}`}
      >
        <div className={`absolute top-2 right-2 flex items-center gap-1.5 z-10 transition-opacity ${selected ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
          <button
            type="button"
            aria-label="Reorder field"
            title="Reorder field"
            {...attributes}
            {...listeners}
            className="flex items-center justify-center h-8 w-8 rounded text-gray-500 hover:text-gray-800 bg-white shadow-sm border border-gray-200 cursor-grab"
            onClick={(e) => e.stopPropagation()}
          >
            <GripVertical className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="Remove field"
            title="Remove field"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="flex items-center justify-center h-8 w-8 rounded text-gray-500 hover:text-red-600 hover:bg-red-50 bg-white shadow-sm border border-gray-200 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
        
        <div className="pr-20 pointer-events-none">
          <MvrTemplateFieldPreview field={field} />
        </div>
      </div>
    </div>
  );
}

function FieldEditor({
  field,
  onChange,
  isIdTaken,
}: {
  field: MvrFieldDef;
  onChange: (next: MvrFieldDef) => void;
  isIdTaken: (id: string) => boolean;
}) {
  const patch = (partial: Partial<MvrFieldDef>) => onChange({ ...field, ...partial });

  // The field ID doubles as the React key / dnd id / answer-mapping key, so an
  // empty or duplicate value corrupts the canvas. Buffer edits locally and only
  // commit a valid ID on blur; otherwise revert to the current one.
  const [idDraft, setIdDraft] = useState(field.id);
  const [idError, setIdError] = useState<string | null>(null);
  useEffect(() => {
    setIdDraft(field.id);
    setIdError(null);
  }, [field.id]);

  // Options textarea must buffer raw text: re-rendering from the parsed array
  // strips the newline the user just pressed (split + filter drops the empty
  // trailing line), which made it impossible to type a new option. Render the
  // draft, parse into field.options live.
  const [optionsDraft, setOptionsDraft] = useState((field.options ?? []).join("\n"));
  useEffect(() => {
    setOptionsDraft((field.options ?? []).join("\n"));
  }, [field.id]);
  const handleOptionsChange = (raw: string) => {
    setOptionsDraft(raw);
    // Dedupe: duplicate options break React keys and radio/checkbox selection
    // in the rendered report (options double as input values).
    const parsed = Array.from(
      new Set(raw.split("\n").map((s) => s.trim()).filter(Boolean)),
    );
    patch({ options: parsed });
  };
  const commitIdDraft = () => {
    const next = idDraft.trim();
    if (next === field.id) {
      setIdDraft(next);
      setIdError(null);
      return;
    }
    if (!next) {
      setIdDraft(field.id);
      setIdError("Field ID cannot be empty — reverted.");
      return;
    }
    if (isIdTaken(next)) {
      setIdDraft(field.id);
      setIdError(`"${next}" is already used by another field — reverted.`);
      return;
    }
    setIdError(null);
    patch({ id: next });
  };

  const labelStyle: CSSProperties = {
    display: "block",
    fontSize: 11,
    fontWeight: 700,
    color: "#6b7280",
    marginBottom: 4,
    textTransform: "uppercase",
    letterSpacing: ".04em",
  };
  const inputStyle: CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    fontSize: 13,
    borderRadius: 8,
    border: "1px solid #e5e7eb",
    marginBottom: 12,
    boxSizing: "border-box",
  };

  return (
    <div>
      <label style={labelStyle}>Label</label>
      <input
        style={inputStyle}
        value={field.label}
        onChange={(e) => patch({ label: e.target.value })}
      />

      {field.type === "section" && (
        <>
          <label style={labelStyle}>Instruction text</label>
          <textarea
            style={{ ...inputStyle, minHeight: 100, resize: "vertical" }}
            value={field.content ?? ""}
            onChange={(e) => patch({ content: e.target.value })}
          />
        </>
      )}

      {field.type !== "section" && field.type !== "table" && field.type !== "checkbox" && (
        <>
          <label style={labelStyle}>Placeholder</label>
          <input
            style={inputStyle}
            value={field.placeholder ?? ""}
            onChange={(e) => patch({ placeholder: e.target.value })}
          />
        </>
      )}

      {(field.type === "radio" || field.type === "select" || field.type === "multiselect") && (
        <>
          <label style={labelStyle}>Options (one per line)</label>
          <textarea
            style={{ ...inputStyle, minHeight: 72 }}
            value={optionsDraft}
            onChange={(e) => handleOptionsChange(e.target.value)}
          />
        </>
      )}

      {field.type === "table" && (
        <TableColumnsEditor
          columns={field.columns ?? []}
          onChange={(columns) => patch({ columns })}
        />
      )}

      {field.type !== "section" && (
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer", marginBottom: 12 }}>
          <input
            type="checkbox"
            checked={!!field.required}
            onChange={(e) => patch({ required: e.target.checked })}
          />
          Required
        </label>
      )}

      <details style={{ marginTop: 4, borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
        <summary
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "#6b7280",
            cursor: "pointer",
            userSelect: "none",
            listStyle: "none",
          }}
        >
          Advanced — Field ID / key
        </summary>
        <p style={{ fontSize: 11, color: "#9ca3af", margin: "8px 0 6px", lineHeight: 1.45 }}>
          Used to map saved answers across template versions. Change only if you know how integrations use this key.
        </p>
        <label style={labelStyle}>Field ID / key</label>
        <input
          style={{ ...inputStyle, marginBottom: 0 }}
          value={idDraft}
          onChange={(e) => setIdDraft(e.target.value)}
          onBlur={commitIdDraft}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
        {idError ? (
          <p style={{ fontSize: 11, color: "#dc2626", margin: "6px 0 0" }}>{idError}</p>
        ) : null}
      </details>
    </div>
  );
}

/** Column ID input that buffers edits and only commits a non-empty, unique id on blur. */
function TableColumnIdInput({
  value,
  style,
  onCommit,
  isTaken,
}: {
  value: string;
  style: CSSProperties;
  onCommit: (id: string) => void;
  isTaken: (id: string) => boolean;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    const next = draft.trim();
    if (!next || (next !== value && isTaken(next))) {
      setDraft(value);
      return;
    }
    if (next !== value) onCommit(next);
    else setDraft(next);
  };
  return (
    <input
      placeholder="Column id"
      style={style}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
    />
  );
}

function TableColumnsEditor({
  columns,
  onChange,
}: {
  columns: MvrTableColumn[];
  onChange: (cols: MvrTableColumn[]) => void;
}) {
  const updateCol = (i: number, col: MvrTableColumn) => {
    const next = [...columns];
    next[i] = col;
    onChange(next);
  };
  const cellInput: CSSProperties = {
    width: "100%",
    minWidth: 0,
    padding: "8px 10px",
    fontSize: 12,
    borderRadius: 8,
    border: "1px solid #e5e7eb",
    boxSizing: "border-box",
  };
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 8 }}>TABLE COLUMNS</div>
      {columns.map((c, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) 40px",
            gap: 8,
            alignItems: "stretch",
            marginBottom: 8,
          }}
        >
          <TableColumnIdInput
            style={cellInput}
            value={c.id}
            isTaken={(id) => columns.some((col, j) => j !== i && col.id === id)}
            onCommit={(id) => updateCol(i, { ...c, id })}
          />
          <input
            placeholder="Label"
            style={cellInput}
            value={c.label}
            onChange={(e) => updateCol(i, { ...c, label: e.target.value })}
          />
          <button
            type="button"
            title="Remove column"
            aria-label="Remove column"
            style={{
              width: 40,
              minWidth: 40,
              height: "100%",
              minHeight: 38,
              alignSelf: "stretch",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 14,
              color: "#9ca3af",
              background: "#f9fafb",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              cursor: "pointer",
              padding: 0,
            }}
            onClick={() => onChange(columns.filter((_, j) => j !== i))}
          >
            🗑️
          </button>
        </div>
      ))}
      <Btn
        variant="secondary"
        size="sm"
        onClick={() =>
          onChange([...columns, { id: `col_${newFieldId().slice(-6)}`, label: "New column" }])
        }
      >
        + Add column
      </Btn>
    </div>
  );
}

export function MvrTemplateBuilderView({
  session,
  showToast,
  organizationId = "default",
  onBackToManager,
  onTemplateIdChange,
}: {
  session: MvrTemplateBuilderSession;
  showToast: (msg: string, type?: string) => void;
  organizationId?: string;
  onBackToManager: () => void;
  onTemplateIdChange: (id: string) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [templateName, setTemplateName] = useState("Untitled Template");
  const [fields, setFields] = useState<MvrFieldDef[]>([]);
  const [baseline, setBaseline] = useState("");
  const [templateVersion, setTemplateVersion] = useState(1);
  const [lifecycleStatus, setLifecycleStatus] = useState<"draft" | "published">("draft");
  const [isActiveTemplate, setIsActiveTemplate] = useState(false);
  const [usesStandardReportUi, setUsesStandardReportUi] = useState(false);
  const [allTemplates, setAllTemplates] = useState<MvrTemplateDto[]>([]);
  const [switcherQuery, setSwitcherQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saving, setSaving] = useState<"idle" | "draft" | "finalize" | "duplicate">("idle");
  const [dragState, setDragState] = useState<{
    activeId: string | null;
    activeSource: "toolbox" | "field" | null;
    overId: string | null;
  }>({ activeId: null, activeSource: null, overId: null });
  const [workspaceMode, setWorkspaceMode] = useState<"builder" | "preview">("builder");

  const activeTemplateId = session.kind === "edit" ? session.templateId : null;

  const applyTemplateDto = useCallback((template: MvrTemplateDto) => {
    const nm = template.name || "Untitled Template";
    const flds = normalizeFieldsFromTemplate(template.schema);
    setTemplateName(nm);
    setFields(flds);
    setSelectedId(null);
    setBaseline(snapshotState(nm, flds));
    setTemplateVersion(template.version);
    setLifecycleStatus(template.lifecycleStatus === "draft" ? "draft" : "published");
    setIsActiveTemplate(!!template.isActive);
    setUsesStandardReportUi(isLegacyStaticMvrTemplateSchema(template.schema));
  }, []);

  const initFromPreset = useCallback((preset: "blank" | "legacy") => {
    setLoading(true);
    try {
      if (preset === "legacy") {
        const name = LEGACY_STATIC_MVR_TEMPLATE_DEFAULT_NAME;
        const flds = normalizeFieldsFromTemplate(getLegacyStaticMvrTemplateSchema());
        setTemplateName(name);
        setFields(flds);
        setBaseline(snapshotState(name, flds));
        setUsesStandardReportUi(true);
      } else {
        const name = "Untitled Template";
        setTemplateName(name);
        setFields([]);
        setBaseline(snapshotState(name, []));
        setUsesStandardReportUi(false);
      }
      setSelectedId(null);
      setTemplateVersion(1);
      setLifecycleStatus("draft");
      setIsActiveTemplate(false);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadExistingTemplate = useCallback(
    async (templateId: string) => {
      setLoading(true);
      try {
        const { template } = await fetchMvrTemplateById(templateId);
        applyTemplateDto(template);
      } catch {
        showToast("Could not load template", "error");
      } finally {
        setLoading(false);
      }
    },
    [applyTemplateDto, showToast],
  );

  const sessionBootstrapKey =
    session.kind === "edit" ? `edit:${session.templateId}` : `new:${session.preset}`;

  useEffect(() => {
    if (session.kind === "edit") {
      void loadExistingTemplate(session.templateId);
    } else {
      initFromPreset(session.preset);
    }
  }, [sessionBootstrapKey, initFromPreset, loadExistingTemplate]);

  const refreshSwitcher = useCallback(async () => {
    try {
      const { items } = await listMvrTemplates(organizationId);
      setAllTemplates(items);
    } catch {
      /* non-fatal */
    }
  }, [organizationId]);

  useEffect(() => {
    void refreshSwitcher();
  }, [refreshSwitcher]);

  const currentSnap = useMemo(() => snapshotState(templateName, fields), [templateName, fields]);
  const isDirty = currentSnap !== baseline;

  const filteredSwitcher = useMemo(() => {
    const q = switcherQuery.trim().toLowerCase();
    if (!q) return allTemplates;
    return allTemplates.filter((t) => (t.name || "").toLowerCase().includes(q));
  }, [allTemplates, switcherQuery]);

  const switcherOptions = useMemo(() => {
    const ids = new Set(filteredSwitcher.map((t) => t.id));
    const cur = activeTemplateId ? allTemplates.find((t) => t.id === activeTemplateId) : undefined;
    if (cur && !ids.has(cur.id)) return [cur, ...filteredSwitcher];
    return filteredSwitcher;
  }, [filteredSwitcher, allTemplates, activeTemplateId]);

  const buildSchemaPayload = useCallback(
    () => ({
      ...(usesStandardReportUi ? { layout: LEGACY_STATIC_MVR_TEMPLATE_LAYOUT } : {}),
      fields: fields.map((f) => ({ ...f })),
    }),
    [fields, usesStandardReportUi],
  );

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  // Toolbox items are inserted before the hovered row. Reordering with
  // arrayMove lands after the hovered row when moving down, before it when
  // moving up — the indicator must match where the field will actually land.
  const dropIndicatorFor = (fieldId: string): "before" | "after" | null => {
    const { activeId, activeSource, overId } = dragState;
    if (!activeId || !overId || overId !== fieldId) return null;
    if (activeSource === "toolbox") return "before";
    if (activeSource === "field" && activeId !== fieldId) {
      const from = fields.findIndex((f) => f.id === activeId);
      const to = fields.findIndex((f) => f.id === fieldId);
      if (from < 0 || to < 0) return null;
      return from < to ? "after" : "before";
    }
    return null;
  };

  const toolboxDropAtEnd =
    dragState.activeSource === "toolbox" && dragState.overId === CANVAS_ID && fields.length > 0;

  const handleDragStart = (e: DragStartEvent) => {
    const src = e.active.data.current?.source;
    setDragState({
      activeId: String(e.active.id),
      activeSource: src === "toolbox" ? "toolbox" : "field",
      overId: null,
    });
  };

  const handleDragOver = (e: DragOverEvent) => {
    setDragState((s) => ({ ...s, overId: e.over ? String(e.over.id) : null }));
  };

  const clearDrag = () => setDragState({ activeId: null, activeSource: null, overId: null });

  const trySwitchTemplate = (nextId: string) => {
    if (nextId === activeTemplateId) return;
    if (isDirty && !window.confirm("Discard unsaved changes and open the selected template?")) return;
    onTemplateIdChange(nextId);
  };

  const handleReload = async () => {
    if (session.kind === "new") {
      if (isDirty) {
        if (!window.confirm("Discard unsaved changes and reset this unsaved template?")) return;
      }
      initFromPreset(session.preset);
      await refreshSwitcher();
      showToast("Reset to initial layout.", "success");
      return;
    }
    if (isDirty) {
      if (!window.confirm("Discard unsaved changes and reload this template from the server?")) return;
    }
    await loadExistingTemplate(session.templateId);
    await refreshSwitcher();
    showToast("Reloaded from server.", "success");
  };

  const handleDuplicate = async () => {
    if (!activeTemplateId) return;
    const err = validate();
    if (err) {
      showToast(err, "error");
      return;
    }
    setSaving("duplicate");
    try {
      const { template } = await duplicateMvrTemplate(activeTemplateId, {
        name: templateName.trim(),
        schema: buildSchemaPayload(),
      });
      onTemplateIdChange(template.id);
      showToast("Duplicate saved as a new draft.", "success");
      await refreshSwitcher();
    } catch {
      showToast("Duplicate failed", "error");
    } finally {
      setSaving("idle");
    }
  };

  const selectedField = selectedId ? fields.find((f) => f.id === selectedId) : undefined;

  const onDragEndHandler = (event: DragEndEvent) => {
    clearDrag();
    const { active, over } = event;
    if (!over) return;

    const fromToolbox = active.data.current?.source === "toolbox";
    const fieldType = active.data.current?.fieldType as MvrFieldType | undefined;

    if (fromToolbox && fieldType) {
      const nf = createField(fieldType);
      if (over.id === CANVAS_ID) {
        setFields((prev) => [...prev, nf]);
        setSelectedId(nf.id);
        return;
      }
      const targetId = String(over.id);
      const overIndex = fields.findIndex((f) => f.id === targetId);
      if (overIndex < 0) return;
      setFields((prev) => {
        const i = prev.findIndex((f) => f.id === targetId);
        if (i < 0) return prev;
        const next = [...prev];
        next.splice(i, 0, nf);
        return next;
      });
      setSelectedId(nf.id);
      return;
    }

    if (active.id !== over.id) {
      setFields((prev) => {
        const oldI = prev.findIndex((f) => f.id === String(active.id));
        const newI = prev.findIndex((f) => f.id === String(over.id));
        if (oldI < 0 || newI < 0) return prev;
        return arrayMove(prev, oldI, newI);
      });
    }
  };

  const validate = (): string | null => {
    if (!templateName.trim()) return "Template name is required.";
    const ids = new Set<string>();
    for (const f of fields) {
      if (!f.id.trim()) return "Every field needs a non-empty ID.";
      if (ids.has(f.id)) return `Duplicate field ID: ${f.id}`;
      ids.add(f.id);
      if (f.type === "table") {
        const cols = f.columns ?? [];
        if (!cols.length) return `Table "${f.label}" needs at least one column.`;
        const cids = new Set<string>();
        for (const c of cols) {
          if (!c.id.trim()) return "Table columns need an id.";
          if (cids.has(c.id)) return `Duplicate column id in ${f.label}`;
          cids.add(c.id);
        }
      }
      if ((f.type === "radio" || f.type === "select" || f.type === "multiselect") && !(f.options?.length)) {
        return `Field "${f.label}" needs at least one option.`;
      }
    }
    return null;
  };

  const needsFinalizeToSaved = lifecycleStatus === "draft";
  const needsDemoteToDraft = lifecycleStatus === "published";

  const persistNewTemplateToServer = async (publish: boolean) => {
    const err = validate();
    if (err) {
      showToast(err, "error");
      return;
    }
    setSaving(publish ? "finalize" : "draft");
    try {
      const { template } = await saveMvrTemplate({
        name: templateName.trim(),
        schema: buildSchemaPayload() as Record<string, unknown>,
        publish,
        organization_id: organizationId,
      });
      applyTemplateDto(template);
      onTemplateIdChange(template.id);
      showToast(publish ? "Saved." : "Draft saved.", "success");
      await refreshSwitcher();
    } catch {
      showToast(publish ? "Failed to save" : "Failed to save draft", "error");
    } finally {
      setSaving("idle");
    }
  };

  const handleSaveDraft = async () => {
    if (session.kind === "new") {
      await persistNewTemplateToServer(false);
      return;
    }
    if (!activeTemplateId) return;
    const err = validate();
    if (err) {
      showToast(err, "error");
      return;
    }
    if (!isDirty && !needsDemoteToDraft) {
      showToast("No unsaved changes.", "info");
      return;
    }
    if (
      isActiveTemplate &&
      !window.confirm(
        "This template is currently Live on visit reports. Saving it as a draft takes it offline until you Save and Set live again.\n\nContinue?",
      )
    ) {
      return;
    }

    setSaving("draft");
    try {
      const { template } = await patchMvrTemplate(activeTemplateId, {
        name: templateName.trim(),
        schema: buildSchemaPayload(),
        finalize: false,
      });
      applyTemplateDto(template);
      showToast("Draft saved.", "success");
      await refreshSwitcher();
    } catch {
      showToast("Failed to save draft", "error");
    } finally {
      setSaving("idle");
    }
  };

  const handleSetLive = async () => {
    if (!activeTemplateId || isActiveTemplate) return;
    if (lifecycleStatus === "draft") {
      showToast("Use Save (not Save draft) before setting this template as Live.", "error");
      return;
    }
    setSaving("finalize");
    try {
      const { template } = await activateMvrTemplate(activeTemplateId);
      applyTemplateDto(template);
      showToast("Template is now Live for visit reports.", "success");
      await refreshSwitcher();
    } catch {
      showToast("Could not set template as Live", "error");
    } finally {
      setSaving("idle");
    }
  };

  const handleSave = async () => {
    if (session.kind === "new") {
      await persistNewTemplateToServer(true);
      return;
    }
    if (!activeTemplateId) return;
    const err = validate();
    if (err) {
      showToast(err, "error");
      return;
    }
    if (!isDirty && !needsFinalizeToSaved) {
      showToast("No unsaved changes.", "info");
      return;
    }

    setSaving("finalize");
    try {
      const { template } = await patchMvrTemplate(activeTemplateId, {
        name: templateName.trim(),
        schema: buildSchemaPayload(),
        finalize: true,
      });
      applyTemplateDto(template);
      showToast("Saved. Use Set live to put it on visit reports.", "success");
      await refreshSwitcher();
    } catch {
      showToast("Failed to save", "error");
    } finally {
      setSaving("idle");
    }
  };

  if (loading) {
    return (
      <div className="fade-in max-w-[1200px] mx-auto py-8 animate-pulse">
        <div className="h-7 w-64 rounded bg-slate-200/80 mb-3" />
        <div className="h-4 w-96 rounded bg-slate-100 mb-8" />
        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)_300px] gap-4">
          <div className="h-72 rounded-xl bg-slate-100" />
          <div className="h-72 rounded-xl bg-slate-100" />
          <div className="h-40 rounded-xl bg-slate-100" />
        </div>
      </div>
    );
  }

  return (
    <div
      className="fade-in"
      style={{
        maxWidth: 1200,
        margin: "0 auto",
        padding: "8px 0 48px",
      }}
    >
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-6">
        <div className="flex items-start gap-4 min-w-0">
          <div className="hidden sm:flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-600/20">
            <LayoutTemplate className="h-5 w-5" strokeWidth={2} />
          </div>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight m-0">MVR template builder</h1>
            <p className="text-sm text-slate-500 mt-1.5 m-0 max-w-2xl leading-relaxed">
              {workspaceMode === "builder"
                ? "Drag components onto the canvas, reorder, then save. Save draft = work in progress. Save = Saved. Use Set live on a saved template to put it on visit reports."
                : "Preview matches the builder canvas — same layout as while you edit fields."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap shrink-0" title="Current server version and lifecycle">
          <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 tabular-nums ring-1 ring-inset ring-slate-200/80">
            v{templateVersion}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
              lifecycleStatus === "draft"
                ? "bg-amber-50 text-amber-800 ring-amber-200/70"
                : "bg-emerald-50 text-emerald-800 ring-emerald-200/70"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${lifecycleStatus === "draft" ? "bg-amber-500" : "bg-emerald-500"}`} />
            {lifecycleStatus === "draft" ? "Draft" : "Saved"}
          </span>
          {isActiveTemplate ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-100/70 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-blue-700 ring-1 ring-inset ring-blue-200/70">
              <Radio className="h-3 w-3" strokeWidth={2.5} />
              Live
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2.5 flex-wrap mb-6">
        <button
          type="button"
          onClick={onBackToManager}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-400 transition-colors"
        >
          <ArrowLeft className="h-4 w-4 text-slate-500" strokeWidth={2} />
          Manager
        </button>
        <div
          role="tablist"
          aria-label="Builder or preview"
          className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 shadow-sm"
        >
          <button
            type="button"
            role="tab"
            aria-selected={workspaceMode === "builder"}
            onClick={() => setWorkspaceMode("builder")}
            className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-semibold transition-colors ${
              workspaceMode === "builder"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <LayoutTemplate className="h-3.5 w-3.5" strokeWidth={2} />
            Builder
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={workspaceMode === "preview"}
            onClick={() => setWorkspaceMode("preview")}
            className={`inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-semibold transition-colors ${
              workspaceMode === "preview"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Eye className="h-3.5 w-3.5" strokeWidth={2} />
            Preview
          </button>
        </div>

        <div className="flex-1 min-w-[80px]" />

        <button
          type="button"
          onClick={() => void handleReload()}
          disabled={saving !== "idle"}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5 text-slate-500" strokeWidth={2} />
          Reload
        </button>
        <button
          type="button"
          title={session.kind === "new" ? "Save this template first" : "Duplicate as new draft"}
          disabled={saving !== "idle" || session.kind === "new"}
          onClick={() => void handleDuplicate()}
          className="inline-flex items-center justify-center h-[38px] w-[38px] rounded-lg border border-slate-300 bg-white text-slate-500 shadow-sm hover:bg-slate-50 hover:text-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Copy className="h-4 w-4" aria-hidden />
          <span className="sr-only">Duplicate as new draft</span>
        </button>
        <button
          type="button"
          onClick={() => void handleSaveDraft()}
          disabled={saving !== "idle"}
          className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 transition-colors"
        >
          {saving === "draft" ? "Saving…" : "Save draft"}
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving !== "idle"}
          className="inline-flex items-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-blue-600/25 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 transition-colors"
        >
          {saving === "finalize" ? "Saving…" : "Save"}
        </button>
        {session.kind === "edit" && lifecycleStatus !== "draft" && !isActiveTemplate ? (
          <button
            type="button"
            onClick={() => void handleSetLive()}
            disabled={saving !== "idle"}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-emerald-600/25 hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            <CheckCircle2 className="h-4 w-4" strokeWidth={2} />
            Set live
          </button>
        ) : null}
      </div>

      {workspaceMode === "builder" && (
        <>
          <div className="mb-6 rounded-xl border border-slate-200 bg-white shadow-sm px-5 py-4">
            <div className="flex flex-wrap items-start gap-5">
              <div className="flex-1 min-w-[220px]">
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Template name
                </label>
                <input
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="Untitled Template"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>
              <div className="flex-1 min-w-[260px]">
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Quick switch
                </label>
                <input
                  type="search"
                  placeholder="Search templates…"
                  value={switcherQuery}
                  onChange={(e) => setSwitcherQuery(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 mb-2"
                />
                {session.kind === "new" ? (
                  <div className="w-full rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-500">
                    Save draft or Save once to enable quick switch between templates.
                  </div>
                ) : (
                  <select
                    value={activeTemplateId ?? ""}
                    onChange={(e) => trySwitchTemplate(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  >
                    {switcherOptions.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name || "Untitled"} · v{t.version} ·{" "}
                        {(t.lifecycleStatus ?? "published") === "draft" ? "Draft" : "Saved"}
                        {t.isActive ? " · Live" : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {workspaceMode === "preview" ? (
        <MvrTemplateCanvasPreview
          templateName={templateName}
          fields={fields}
          usesStandardReportUi={usesStandardReportUi}
        />
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={onDragEndHandler}
          onDragCancel={clearDrag}
        >
        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)_300px] gap-4 items-start">
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/80 bg-slate-50/70">
              <h2 className="text-sm font-semibold text-slate-800 m-0">Toolbox</h2>
            </div>
            <div className="p-3">
            {TOOLBOX.map((t) => (
              <ToolboxChip
                key={t.type}
                type={t.type}
                label={t.label}
                icon={t.icon}
                onAdd={(type) => {
                  const nf = createField(type);
                  setFields((prev) => [...prev, nf]);
                  setSelectedId(nf.id);
                }}
              />
            ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/80 bg-slate-50/70">
              <h2 className="text-sm font-semibold text-slate-800 m-0">Canvas</h2>
            </div>
            <div className="p-4">
            <CanvasDropShell showDragChrome={!!dragState.activeId}>
              {fields.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
                    <LayoutTemplate className="h-5 w-5" strokeWidth={1.75} />
                  </div>
                  <p className="m-0 text-sm font-medium text-slate-600">Drag items here to build your form</p>
                  <p className="m-0 mt-1 text-xs text-slate-400">
                    or press Enter on a toolbox item to add it to the end
                  </p>
                </div>
              )}
              <SortableContext items={fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
                {fields.map((f) => (
                  <SortableFieldRow
                    key={f.id}
                    field={f}
                    selected={selectedId === f.id}
                    showDropBefore={dropIndicatorFor(f.id) === "before"}
                    showDropAfter={dropIndicatorFor(f.id) === "after"}
                    onSelect={() => setSelectedId(f.id)}
                    onDelete={() => {
                      setFields((prev) => prev.filter((x) => x.id !== f.id));
                      setSelectedId((cur) => (cur === f.id ? null : cur));
                    }}
                  />
                ))}
              </SortableContext>
              {toolboxDropAtEnd && (
                <div
                  role="presentation"
                  className="mt-2 h-1 rounded bg-blue-600 shadow-[0_0_0_2px_rgba(26,86,219,0.15)]"
                />
              )}
            </CanvasDropShell>
            </div>
          </div>

          <div className="sticky top-4 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200/80 bg-slate-50/70">
              <h2 className="text-sm font-semibold text-slate-800 m-0">Field properties</h2>
            </div>
            <div className="p-4">
              {selectedField ? (
                <FieldEditor
                  field={selectedField}
                  isIdTaken={(id) => fields.some((x) => x.id === id)}
                  onChange={(next) => {
                    setFields((prev) => prev.map((x) => (x.id === selectedField.id ? next : x)));
                    if (next.id !== selectedField.id) {
                      setSelectedId(next.id);
                    }
                  }}
                />
              ) : (
                <p style={{ fontSize: 13, color: "#9ca3af", margin: 0 }}>Select a field on the canvas to edit its properties.</p>
              )}
            </div>
          </div>
        </div>
      </DndContext>
      )}
    </div>
  );
}
