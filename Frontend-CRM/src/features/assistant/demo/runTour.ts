import { driver, type Driver, type DriveStep } from 'driver.js'
import 'driver.js/dist/driver.css'
import './tourStyles.css'
import { getTour, type TourStep } from './tours'

function waitFor(selector: string, timeoutMs = 4000): Promise<boolean> {
  return new Promise((resolve) => {
    const start = Date.now()
    const tick = () => {
      if (document.querySelector(selector)) return resolve(true)
      if (Date.now() - start > timeoutMs) return resolve(false)
      requestAnimationFrame(tick)
    }
    tick()
  })
}

const settle = (ms: number) => new Promise((r) => setTimeout(r, ms))

// Only one tour at a time — starting a new one tears down the previous overlay.
let active: Driver | null = null

function clearBodyFlags() {
  document.body.classList.remove('orbit-tour-pulsing', 'orbit-tour-tone-action')
}

/**
 * Run a read-only guided tour (driver.js). V2 engine:
 * - Multi-screen: a step may declare `screen` — advancing navigates there and
 *   waits for the step's anchor before highlighting (orientation-first tours
 *   point at the nav entry on the CURRENT screen, then travel).
 * - Click-along: `clickNext` clicks the highlighted element when advancing
 *   (opens a tab/modal — local UI state only, never a submit; tours do ZERO writes).
 * - Tones + pulse: popovers are color-coded (nav/action/info) and click targets
 *   get a pulsing ring, styled in tourStyles.css.
 * - Never dead-ends: a missing anchor renders the narration as a centered
 *   popover (driver.js floating fallback) instead of silently failing.
 */
export async function runTour(id: string, navigate: (screen: string) => void): Promise<boolean> {
  const recipe = getTour(id)
  if (!recipe) return false

  active?.destroy()
  clearBodyFlags()

  const steps: TourStep[] = recipe.steps
  const perStepNav = steps.some((s) => s.screen)

  // Legacy/generated recipes navigate up-front; orientation-first recipes start
  // on the current screen (their first step anchors the navbar) and navigate
  // per-step via `screen`.
  if (!perStepNav && recipe.screen) {
    navigate(recipe.screen)
  }
  const first = steps[0]
  if (first?.screen) navigate(first.screen)
  if (first?.selector) await waitFor(first.selector)

  const driverSteps: DriveStep[] = steps.map((s) => ({
    element: s.selector,
    popover: {
      title: s.title,
      description: s.description,
      popoverClass: `orbit-tour orbit-tour--${s.tone ?? 'info'}`,
    },
    onHighlighted: () => {
      document.body.classList.toggle('orbit-tour-pulsing', !!s.pulse && !!s.selector)
      document.body.classList.toggle('orbit-tour-tone-action', s.tone === 'action')
    },
  }))

  const prepareStep = async (index: number) => {
    const st = steps[index]
    if (!st) return
    if (st.screen) navigate(st.screen)
    if (st.selector) await waitFor(st.selector)
  }

  const d = driver({
    showProgress: true,
    allowClose: true,
    overlayColor: 'rgba(4, 38, 48, 0.6)',
    stagePadding: 6,
    stageRadius: 12,
    disableActiveInteraction: true,
    popoverClass: 'orbit-tour',
    nextBtnText: 'Next',
    prevBtnText: 'Back',
    doneBtnText: 'Finish',
    progressText: '{{current}} of {{total}}',
    steps: driverSteps,
    onNextClick: () => {
      void (async () => {
        if (!d.hasNextStep()) {
          d.destroy()
          return
        }
        const idx = d.getActiveIndex() ?? 0
        const cur = steps[idx]
        if (cur?.clickNext && cur.selector) {
          const el = document.querySelector(cur.selector) as HTMLElement | null
          el?.click()
          await settle(350)
        }
        await prepareStep(idx + 1)
        d.moveNext()
      })()
    },
    onPrevClick: () => {
      void (async () => {
        const idx = d.getActiveIndex() ?? 0
        await prepareStep(idx - 1)
        d.movePrevious()
      })()
    },
    onDestroyed: () => {
      clearBodyFlags()
      if (active === d) active = null
    },
  })

  active = d
  d.drive()
  return true
}
