import { describe, it, expect } from 'vitest'
import { parseJsonl } from './liveDataClient.js'

describe('parseJsonl', () => {
  it('parses JSONL lines, skipping blanks', () => {
    const text = '{"tick":1,"event":"A"}\n\n{"tick":2,"event":"B"}\n'
    const { events, errors } = parseJsonl(text)
    expect(events).toHaveLength(2)
    expect(errors).toHaveLength(0)
  })

  it('sorts events by tick ascending', () => {
    const text = '{"tick":5,"event":"late"}\n{"tick":1,"event":"early"}'
    const { events } = parseJsonl(text)
    expect(events.map(e => e.event)).toEqual(['early', 'late'])
  })

  it('applies the default algo to events that omit one', () => {
    const { events } = parseJsonl('{"tick":0,"event":"X"}', 'mlfq')
    expect(events[0].algo).toBe('MLFQ') // normalized to canonical display form
  })

  it('keeps an event\'s own algo over the default', () => {
    const { events } = parseJsonl('{"tick":0,"algo":"srtf"}', 'rr')
    expect(events[0].algo).toBe('SRTF')
  })

  it('collects bad-JSON lines as errors without throwing', () => {
    const text = '{"tick":1}\nnot json\n{"tick":2}'
    const { events, errors } = parseJsonl(text)
    expect(events).toHaveLength(2)
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatch(/Bad JSON/)
  })

  it('normalizes a `time` field to `tick`', () => {
    const { events } = parseJsonl('{"time":3,"event":"T"}')
    expect(events[0].tick).toBe(3)
  })
})
