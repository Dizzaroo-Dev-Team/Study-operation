/** MVR template field definitions (serialized from admin builder). */

export type MvrFieldType =
  | "section"
  | "text"
  | "textarea"
  | "number"
  | "checkbox"
  | "radio"
  | "select"
  | "multiselect"
  | "date"
  | "table";

export interface MvrTableColumn {
  id: string;
  label: string;
}

export interface MvrFieldDef {
  id: string;
  type: MvrFieldType;
  label: string;
  /** Section: instructional copy */
  content?: string;
  placeholder?: string;
  required?: boolean;
  options?: string[];
  columns?: MvrTableColumn[];
}

export interface MvrTemplateSchema {
  fields: MvrFieldDef[];
  /** Optional renderer hint for schemas created from the built-in standard report. */
  layout?: string;
}

export interface MvrTemplateDto {
  id: string;
  organizationId?: string;
  name: string;
  schema: MvrTemplateSchema;
  version: number;
  /** Present when loaded from list/detail APIs (Study Setup manager / builder). */
  lifecycleStatus?: "draft" | "published";
  isActive?: boolean;
  updatedAt?: string | null;
}

export type MvrSubmissionData = Record<string, unknown>;
