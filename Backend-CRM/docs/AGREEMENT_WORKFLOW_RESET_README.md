# Agreement Workflow Reset and Audit

## Overview

This directory contains scripts for auditing and resetting the Agreement workflow implementation. These scripts are designed to safely reset ONLY agreement-related data without affecting other CRM modules.

## Files

### 1. `audit_agreement_workflow.py`
**Purpose**: Audits the current state of Agreement workflow implementation.

**What it checks**:
- Model existence (tables in database)
- Database schema (JSON fields)
- Data counts in agreement-related tables
- Implementation status summary

**Usage**:
```bash
cd Backend-CRM
python audit_agreement_workflow.py
```

**Output**: Console report showing what exists and what's missing.

---

### 2. `reset_agreement_workflow_data.py`
**Purpose**: Safely resets ONLY agreement-related workflow data.

**What it clears**:
- `agreement_inline_comments`
- `agreement_comments`
- `agreement_documents`
- `agreement_versions`
- `agreements`
- `study_templates`

**What it does NOT touch**:
- Users
- Sites
- Studies
- IAM tables
- Notice board
- Site status
- Any unrelated CRM tables

**Safety Features**:
- Requires explicit `--confirm-reset` flag
- Does NOT drop tables
- Does NOT alter schema
- Only deletes rows
- Shows before/after counts
- Verifies deletion

**Usage**:
```bash
# Preview (will abort without confirmation)
cd Backend-CRM
python reset_agreement_workflow_data.py

# Execute reset (requires confirmation flag)
python reset_agreement_workflow_data.py --confirm-reset
```

**Output**: Detailed summary of deleted rows and final state verification.

---

## Disabled Features

### Backend
- **Endpoint**: `POST /agreements/{agreement_id}/versions`
- **Status**: Temporarily disabled
- **Reason**: Workflow restructuring from file-based to template-based
- **Error**: Returns HTTP 503 with explanation message

### Frontend
- **Component**: `AgreementTab.tsx`
- **Feature**: Manual file upload button
- **Status**: Disabled with warning message
- **Reason**: Workflow restructuring
- **UI**: Shows orange warning banner instead of upload form

---

## Current Implementation Status

### ✅ Implemented
- `StudyTemplate` model with `template_content` (JSON)
- `AgreementDocument` model with `document_content` (JSON)
- `AgreementInlineComment` model
- TipTap editor component (`AgreementEditor.tsx`)
- Template creation endpoints
- Document save endpoint
- Agreement creation requires `template_id`

### ⚠️ Partially Implemented
- Upload endpoint exists but is disabled
- Frontend upload UI exists but is disabled

### ❌ Not Yet Implemented
- Full TipTap integration with collaboration
- Inline comment handling in editor
- Document editing workflow
- Template editing interface

---

## Reset Process

1. **Run Audit**:
   ```bash
   python audit_agreement_workflow.py
   ```
   Review the output to understand current state.

2. **Run Reset** (if needed):
   ```bash
   python reset_agreement_workflow_data.py --confirm-reset
   ```
   This will delete all agreement-related data.

3. **Verify Reset**:
   The script will show:
   - Rows deleted per table
   - Final verification (all tables should be empty)
   - Confirmation message

4. **System State After Reset**:
   - Zero agreements
   - Zero agreement versions
   - Zero agreement documents
   - Zero agreement comments
   - Zero inline comments
   - Zero templates
   - All other CRM modules remain functional

---

## Safety Guarantees

1. **No Schema Changes**: Tables are NOT dropped or altered
2. **No Data Loss Outside Scope**: Only agreement-related tables are affected
3. **Explicit Confirmation Required**: Cannot run accidentally
4. **Reversible**: Data can be restored from backups if needed
5. **Auditable**: Full logging of what was deleted

---

## Post-Reset Actions

After resetting, the system is ready for:
1. Clean implementation of template-based workflow
2. Testing new agreement creation flow
3. Verifying TipTap editor integration
4. Building inline comment system
5. Implementing document collaboration features

---

## Notes

- These scripts are for development/testing purposes
- Always backup database before running reset in production
- The disabled upload endpoint can be re-enabled after restructuring is complete
- Frontend upload UI can be restored by removing the disabled wrapper

---

## Troubleshooting

### Error: "Table does not exist"
- Run database migrations first
- Check that `create_template_tables.py` has been executed
- Verify `migrate_to_jsonfield.py` has been executed

### Error: "Foreign key constraint"
- The script deletes in dependency order to avoid FK violations
- If errors occur, check database constraints

### Error: "Connection refused"
- Ensure database is running
- Check `settings.database_url` in `app/config.py`

---

## Contact

For issues or questions about these scripts, refer to the main project documentation.
