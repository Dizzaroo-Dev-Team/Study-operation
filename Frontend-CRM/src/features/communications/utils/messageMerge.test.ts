import { describe, it, expect } from 'vitest'
import { appendRealtimeMessage, mergeServerMessages } from './messageMerge'

const mk = (id: string, body: string, t = '2026-01-01T00:00:00Z') => ({
  id,
  body,
  created_at: t,
})

describe('appendRealtimeMessage (instant realtime path)', () => {
  it('appends a new message exactly once', () => {
    const out = appendRealtimeMessage([mk('a', 'hi')], mk('b', 'yo', '2026-01-01T00:00:01Z'))
    expect(out.map((m) => m.id)).toEqual(['a', 'b'])
  })

  it('dedupes a duplicate new_message event by id — never renders twice', () => {
    const after1 = appendRealtimeMessage([mk('a', 'hi')], mk('b', 'yo', '2026-01-01T00:00:01Z'))
    const after2 = appendRealtimeMessage(after1, mk('b', 'yo', '2026-01-01T00:00:01Z'))
    expect(after2).toHaveLength(2)
    expect(after2.filter((m) => m.id === 'b')).toHaveLength(1)
  })

  it("reconciles the sender's optimistic temp- row with its real echo (no double)", () => {
    const prev = [mk('temp-1', 'hello', '2026-01-01T00:00:00Z')]
    const out = appendRealtimeMessage(prev, mk('real-1', 'hello', '2026-01-01T00:00:02Z'))
    expect(out).toHaveLength(1)
    expect(out[0].id).toBe('real-1')
  })

  it('keeps the list time-sorted on append', () => {
    const out = appendRealtimeMessage(
      [mk('b', 'b', '2026-01-01T00:00:05Z')],
      mk('a', 'a', '2026-01-01T00:00:01Z'),
    )
    expect(out.map((m) => m.id)).toEqual(['a', 'b'])
  })
})

describe('mergeServerMessages (focus / reconnect self-heal)', () => {
  it('dedupes a realtime-appended message against the same server message', () => {
    const prev = [mk('a', 'hi'), mk('b', 'yo', '2026-01-01T00:00:01Z')] // b already via WS
    const server = [mk('a', 'hi'), mk('b', 'yo', '2026-01-01T00:00:01Z')]
    const out = mergeServerMessages(prev, server)
    expect(out).toHaveLength(2)
    expect(out.filter((m) => m.id === 'b')).toHaveLength(1)
  })

  it('drops unconfirmed optimistic temp- rows when the server set arrives', () => {
    const out = mergeServerMessages(
      [mk('temp-1', 'pending')],
      [mk('real-1', 'pending', '2026-01-01T00:00:02Z')],
    )
    expect(out.map((m) => m.id)).toEqual(['real-1'])
  })

  it('catches up a message the panel missed while disconnected', () => {
    // panel had only [a]; server now has [a, b] (b arrived during the gap)
    const out = mergeServerMessages([mk('a', 'hi')], [mk('a', 'hi'), mk('b', 'missed', '2026-01-01T00:00:03Z')])
    expect(out.map((m) => m.id)).toEqual(['a', 'b'])
  })
})
