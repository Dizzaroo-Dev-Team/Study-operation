// UnifiedAgreementWorkflow.tsx
// The TEMPLATE-DRIVEN, type-agnostic Agreement workflow view (behind WORKFLOW_UNIFIED).
// There are no CDA/CTA tabs here. The flow is one path:
//   1. Pick a template (its type is shown only as a LABEL — it drives nothing).
//   2. Bind a workflow PER TEMPLATE, keyed "tpl:<template_id>":
//        - template has no workflow yet  -> open the builder to DEFINE one (publish).
//        - template already has one       -> "Use previous" or "Define new".
//   3. Run the agreement on the generic self-building runner (stepper + engine
//      buttons + embedded OnlyOffice at review + signing launch at signing).
// Exactly one instance per agreement via the idempotent ensure endpoint.

import React from 'react'
import { workflowApi } from '@/features/workflows/api'
import { WorkflowBuilder } from '@/features/workflows/builder/WorkflowBuilder'
import { WorkflowRunner } from '@/features/workflows/runner/WorkflowRunner'
import { VersionHistory } from '@/features/workflows/definitions/VersionHistory'

type Template = { id: string; template_name?: string; template_type?: string }

interface UnifiedAgreementWorkflowProps {
  /** The agreement loaded for the current (site, study), or null before create. */
  agreement: { id: string; agreement_type?: string } | null
  /** Active templates for the study (id + template_name + template_type). */
  templates: Template[]
  creating: boolean
  /** Creates the agreement for a template id and refreshes the parent's agreement. */
  onCreateAgreement: (templateId: string) => Promise<void>
  /** Called after a dev reset (which also deletes the bound agreement) so the parent
   *  refetches — the now-deleted agreement clears and the view returns to "create". */
  onAfterReset?: () => Promise<void> | void
  /** The current (site, study) scope. An agreement is unique per study + site +
   *  template, and a workflow INSTANCE is per agreement — so changing the site (or
   *  study) is a DIFFERENT scope. Passing these lets the component reset its
   *  per-site binding state on a switch, so one site's selection / "workflow exists"
   *  state / resolved instance can never leak into another site's view. */
  siteId?: string | null
  studyId?: string | null
}

const tplKey = (id: string) => `tpl:${id}`

const card: React.CSSProperties = {
  border: '1px solid #e2e8f0', borderRadius: 12, padding: 20, background: '#fff', marginBottom: 16,
}
const btnPrimary: React.CSSProperties = {
  padding: '9px 16px', background: '#4f46e5', color: '#fff', border: 'none',
  borderRadius: 8, fontWeight: 600, cursor: 'pointer',
}
const btnOutline: React.CSSProperties = {
  padding: '9px 16px', background: '#fff', color: '#3730a3', border: '1px solid #c7d2fe',
  borderRadius: 8, fontWeight: 600, cursor: 'pointer',
}

function TypeLabel({ type }: { type?: string }) {
  if (!type) return null
  return (
    <span
      title="Template type — a label only; it does not branch the workflow."
      style={{
        display: 'inline-block', padding: '2px 10px', borderRadius: 999, fontSize: 12,
        fontWeight: 700, background: '#eef2ff', color: '#3730a3', border: '1px solid #c7d2fe',
      }}
    >
      {type}
    </span>
  )
}

export const UnifiedAgreementWorkflow: React.FC<UnifiedAgreementWorkflowProps> = ({
  agreement,
  templates,
  creating,
  onCreateAgreement,
  onAfterReset,
  siteId,
  studyId,
}) => {
  const [selectedTemplateId, setSelectedTemplateId] = React.useState('')
  const [defState, setDefState] = React.useState<'idle' | 'checking' | 'none' | 'exists'>('idle')
  const [wfBuilder, setWfBuilder] = React.useState<null | 'define' | 'new'>(null)
  // Workflow Publishing Library: browse this template's version history, and clone an
  // older version into the builder to republish as a new version (clone & edit).
  const [historyOpen, setHistoryOpen] = React.useState(false)
  const [cloneVer, setCloneVer] = React.useState<number | null>(null)
  const [instanceId, setInstanceId] = React.useState<number | null>(null)
  const [resolving, setResolving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  // After a dev reset, force the bind/define view even though the agreement row
  // persists (reset never deletes the agreement). Re-binding ensures a fresh
  // instance on the SAME agreement (no duplicate create).
  const [rebind, setRebind] = React.useState(false)
  const [resetting, setResetting] = React.useState(false)

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId)
  const typeLabel = agreement?.agreement_type ?? selectedTemplate?.template_type

  // ── Per-site isolation ─────────────────────────────────────────────────────
  // An agreement is unique per study + site + template, and a workflow instance is
  // per agreement. So when the SITE (or STUDY) changes, this is a DIFFERENT scope:
  // clear every piece of binding/instance state so a previous site's template pick,
  // its "this template already has a workflow" determination, its resolved instance,
  // or a stale rebind flag can NEVER leak into the new site's view. Without this, a
  // site switch could keep showing (or let "Use the previous workflow" re-bind to)
  // the prior site's agreement — i.e. wrongly "blocked, workflow exists" instead of
  // creating this site's own new agreement. The resolve effect below then re-resolves
  // THIS site's agreement → its OWN instance. Runs before the resolve effect.
  React.useEffect(() => {
    setSelectedTemplateId('')
    setDefState('idle')
    setInstanceId(null)
    setRebind(false)
    setWfBuilder(null)
    setHistoryOpen(false)
    setCloneVer(null)
    setError(null)
  }, [siteId, studyId])

  // ── Existing agreement → resolve (or ensure) its single workflow instance ──
  // findInstance(agreementId) with NO key returns the newest instance for the
  // agreement; in unified mode that is the tpl:<id> instance. If none exists yet
  // (just-created), ensure one on the selected template's key.
  React.useEffect(() => {
    if (!agreement?.id) { setInstanceId(null); return }
    let alive = true
    setResolving(true)
    setError(null)
    ;(async () => {
      try {
        let inst = await workflowApi.findInstance(agreement.id)
        if (!inst && selectedTemplateId) {
          inst = await workflowApi.ensureInstance(tplKey(selectedTemplateId), agreement.id, {
            agreement_id: agreement.id,
            agreement_type: typeLabel ?? '',
            template_id: selectedTemplateId,
          })
        }
        if (alive) {
          setInstanceId(inst?.id ?? null)
        }
      } catch (e: any) {
        if (alive) setError(e?.response?.data?.detail || 'Failed to resolve the workflow instance.')
      } finally {
        if (alive) setResolving(false)
      }
    })()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agreement?.id])

  // Does this template have a workflow? Match the key against the definitions
  // LIST (colon-safe) rather than GET /definitions/tpl:<uuid> — a colon in a URL
  // path segment can be mishandled by proxies. Both sides use the identical key
  // tpl:<template_id>, so a published workflow is detected reliably.
  const checkDefinition = React.useCallback(async (id: string) => {
    if (!id) { setDefState('idle'); return }
    setDefState('checking')
    try {
      const defs = await workflowApi.listDefinitions()
      setDefState(defs.some((d) => d.key === tplKey(id)) ? 'exists' : 'none')
    } catch {
      setDefState('none')
    }
  }, [])

  // ── Template selection (pre-create) → does this template have a workflow? ──
  const onPickTemplate = async (id: string) => {
    setSelectedTemplateId(id)
    setError(null)
    await checkDefinition(id)
  }

  // Bind the selected template's workflow and run it. If an agreement already
  // exists (e.g. after a reset), ensure a fresh instance on THAT agreement (never
  // create a duplicate); otherwise create a new agreement (parent refreshes →
  // resolve effect ensures + runs).
  const proceedBind = async () => {
    if (!selectedTemplateId) return
    if (agreement?.id) {
      try {
        const inst = await workflowApi.ensureInstance(tplKey(selectedTemplateId), agreement.id, {
          agreement_id: agreement.id,
          agreement_type: typeLabel ?? '',
          template_id: selectedTemplateId,
        })
        setInstanceId(inst.id)
        setRebind(false)
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to start the workflow.')
      }
    } else {
      await onCreateAgreement(selectedTemplateId)
    }
  }

  // DEV reset: wipe THIS template's workflow (definition + versions + instances +
  // audit) so it returns to "no workflow yet". The agreement row is untouched; if
  // one exists we flip to the bind/define view (rebind) so testing repeats.
  // Study + site SPECIFIC reset (the agreement-screen button). Deletes THIS agreement
  // + its workflow instance(s) (documents, comments, signatures included) so this one
  // (study, site, template) slot is freed and can be recreated. The shared template
  // definition, the template, and every OTHER site's agreement are untouched.
  const handleResetAgreement = async () => {
    if (!agreement?.id) return
    const ok = window.confirm(
      'Reset THIS agreement (this study + site): deletes the agreement and its workflow ' +
      'instance — including its documents, comments and signatures — so you can create a ' +
      'fresh one from the same template. The template and OTHER sites are NOT affected. Continue?',
    )
    if (!ok) return
    setResetting(true)
    setError(null)
    try {
      await workflowApi.resetAgreementWorkflow(agreement.id)
      // Agreement deleted server-side; clear local state and ask the parent to refetch
      // so `agreement` goes null → the "create an agreement" view returns for this site.
      setInstanceId(null)
      setSelectedTemplateId('')
      setDefState('idle')
      setRebind(false)
      await onAfterReset?.()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to reset this agreement.')
    } finally {
      setResetting(false)
    }
  }

  // Template-level reset of the SHARED workflow definition (bind-view "redefine"):
  // deletes the definition + all its versions/instances so a new blueprint can be
  // drawn. Affects every site on this template; does NOT delete agreements.
  const handleResetDefinition = async (key: string) => {
    const ok = window.confirm(
      'Delete this template’s workflow definition (and all its versions/instances) so you ' +
      'can define a new one? This affects every site using this template. Agreements are NOT deleted.',
    )
    if (!ok) return
    setResetting(true)
    setError(null)
    try {
      await workflowApi.resetTemplateWorkflow(key)
      const tid = key.startsWith('tpl:') ? key.slice(4) : selectedTemplateId
      setInstanceId(null)
      setSelectedTemplateId(tid)
      setDefState('none')
      setRebind(false)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to reset the workflow.')
    } finally {
      setResetting(false)
    }
  }

  // ── RUN: an agreement exists and its instance is resolved ──────────────────
  if (agreement?.id && !rebind) {
    return (
      <div>
        {/* Slim utility strip (compact, single line): type label + dev reset only.
            The workflow name + status live in the runner's own compact header below. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <TypeLabel type={typeLabel} />
          <span style={{ color: '#94a3b8', fontSize: 12 }}>Template-driven workflow · type is a label only</span>
          {agreement?.id && (
            <button
              style={{
                marginLeft: 'auto', padding: '5px 11px', fontSize: 12, fontWeight: 600,
                background: '#fff', color: '#b91c1c', border: '1px solid #fecaca', borderRadius: 8, cursor: 'pointer',
              }}
              disabled={resetting}
              onClick={handleResetAgreement}
              title="DEV only — delete THIS agreement (this study + site) + its workflow instance, so you can recreate it. Other sites and the template are untouched."
            >
              {resetting ? 'Resetting…' : 'Reset (dev)'}
            </button>
          )}
        </div>
        {error && <div style={{ ...card, color: '#b91c1c', background: '#fef2f2', borderColor: '#fecaca' }}>{error}</div>}
        {resolving && <div style={{ ...card, color: '#64748b' }}>Resolving workflow…</div>}
        {!resolving && instanceId !== null && (
          <div style={{ border: '1px solid #e6eaf0', borderRadius: 12, overflow: 'hidden', background: '#fff' }}>
            <WorkflowRunner instanceId={instanceId} />
          </div>
        )}
        {!resolving && instanceId === null && !error && (
          <div style={{ ...card, color: '#64748b' }}>
            This agreement has no bound workflow yet. (Legacy agreements created before unified mode
            won’t have one — create a new agreement to use the template-driven flow.)
          </div>
        )}
      </div>
    )
  }

  // ── BIND: no agreement yet → pick a template, then define / use-or-new ─────
  return (
    <div>
      <div style={card}>
        <h3 style={{ marginTop: 0 }}>{rebind ? 'Re-bind this template’s workflow' : 'Create an agreement'}</h3>
        <p style={{ color: '#64748b', marginTop: 0 }}>
          {rebind
            ? 'The workflow was reset. Define it again (or pick another template) — it will run on the same agreement.'
            : 'Pick a template. Its type is shown as a label only — one flow handles every type.'}
        </p>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 6 }}>
          Template
        </label>
        <select
          value={selectedTemplateId}
          onChange={(e) => onPickTemplate(e.target.value)}
          style={{ width: '100%', maxWidth: 480, padding: '8px 10px', border: '1px solid #cbd5e1', borderRadius: 8 }}
        >
          <option value="">— Select a template —</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.template_name} ({t.template_type})
            </option>
          ))}
        </select>
        {selectedTemplate && (
          <div style={{ marginTop: 10 }}>
            <TypeLabel type={selectedTemplate.template_type} />
          </div>
        )}
      </div>

      {error && <div style={{ ...card, color: '#b91c1c', background: '#fef2f2', borderColor: '#fecaca' }}>{error}</div>}

      {selectedTemplateId && defState === 'checking' && (
        <div style={{ ...card, color: '#64748b' }}>Checking this template’s workflow…</div>
      )}

      {/* First time for this template → define a workflow */}
      {selectedTemplateId && defState === 'none' && (
        <div style={card}>
          <p style={{ marginTop: 0, color: '#334155' }}>
            <strong>This template has no workflow yet.</strong> Define one (draw it or generate with AI),
            publish it, and it becomes this template’s workflow.
          </p>
          <button style={btnPrimary} disabled={creating} onClick={() => setWfBuilder('define')}>
            Define workflow…
          </button>
        </div>
      )}

      {/* Template already has a workflow → use previous or define new */}
      {selectedTemplateId && defState === 'exists' && (
        <div style={card}>
          <p style={{ marginTop: 0, color: '#334155' }}>
            This template already has a workflow. Use the previous one, or define a new version
            (existing in-flight agreements stay pinned to their version).
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button style={btnPrimary} disabled={creating || resetting} onClick={proceedBind}>
              {creating ? 'Creating…' : 'Use the previous workflow'}
            </button>
            <button style={btnOutline} disabled={creating || resetting} onClick={() => setWfBuilder('new')}>
              Define a new one…
            </button>
            <button style={btnOutline} disabled={creating || resetting} onClick={() => setHistoryOpen(true)}>
              Version history…
            </button>
            <button
              style={{ ...btnOutline, color: '#b91c1c', borderColor: '#fecaca' }}
              disabled={resetting}
              onClick={() => handleResetDefinition(tplKey(selectedTemplateId))}
              title="DEV only — delete this template's shared workflow definition to redefine it (affects all sites; agreements are not deleted)"
            >
              {resetting ? 'Resetting…' : 'Reset template workflow (dev)'}
            </button>
          </div>
        </div>
      )}

      {/* Builder modal — publishes as key tpl:<templateId>, then creates + runs. */}
      {(wfBuilder || cloneVer !== null) && selectedTemplateId && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, padding: 16, background: 'rgba(15,23,42,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: '#fff', borderRadius: 12, width: '94vw', height: '88vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderBottom: '1px solid #e2e8f0' }}>
              <strong>
                {cloneVer !== null
                  ? `Clone from v${cloneVer} — edit & publish a new version`
                  : wfBuilder === 'define' ? 'Define this template’s workflow' : 'Define a new workflow version'}
              </strong>
              <button onClick={() => { setWfBuilder(null); setCloneVer(null) }} style={{ ...btnOutline, color: '#334155', borderColor: '#cbd5e1' }}>Cancel</button>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <WorkflowBuilder
                // 'define' = fresh canvas, key locked to tpl:<id>. 'new' = load the
                // existing tpl:<id> to edit, publish a new version. clone = load a
                // SPECIFIC past version's steps, key still locked to tpl:<id>.
                definitionKey={cloneVer === null && wfBuilder === 'new' ? tplKey(selectedTemplateId) : undefined}
                presetKey={cloneVer !== null || wfBuilder === 'define' ? tplKey(selectedTemplateId) : undefined}
                cloneKey={cloneVer !== null ? tplKey(selectedTemplateId) : undefined}
                cloneVersion={cloneVer ?? undefined}
                onPublished={(publishedKey: string) => {
                  setWfBuilder(null)
                  setCloneVer(null)
                  // We just published this EXACT key (publishedKey === tpl:<selected
                  // template id>). Mark it 'exists' directly — no re-query, so the
                  // lookup can never diverge from the publish key. The page now shows
                  // "Use previous / Define new"; the user picks "Use the previous
                  // workflow" to create/bind + run.
                  void publishedKey
                  setDefState('exists')
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Version-history browser for this template's workflow (tpl:<id>): publish an
          older version as the default, or clone one into the builder to edit. */}
      {historyOpen && selectedTemplateId && (
        <VersionHistory
          defKey={tplKey(selectedTemplateId)}
          title={selectedTemplate?.template_name || 'This template’s workflow'}
          onClose={() => setHistoryOpen(false)}
          onPublished={() => setDefState('exists')}
          onClone={(_key, version) => { setHistoryOpen(false); setCloneVer(version) }}
        />
      )}
    </div>
  )
}

export default UnifiedAgreementWorkflow
