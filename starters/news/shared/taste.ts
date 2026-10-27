// Explicit, bounded, device-local taste model, ported unchanged from the original Newsroom (personalization.js) so
// votes already on the phone keep their meaning. No remote calls or implicit tracking.
/** Why a story got 👎, when the reader said: for the editor, and for how much the vote weighs here. */
export const REASONS = {
  topic: 'Not my topic',
  seen: 'Already knew this',
  source: 'Don’t trust the source',
  quality: 'Thin or clickbait',
  misleading: 'Misleading',
  other: 'Something else',
} as const
export type Reason = keyof typeof REASONS

/** A value of 0 is a vote taken back: kept, with when, so it wins over the older vote other devices still have. */
export type Vote = {
  id: string; title: string; url: string; publisher: string; topics: string[]; tags: string[]; value: 1 | -1 | 0; at: string
  reason?: Reason; note?: string
}
export type Votes = Record<string, Vote>

type Rated = { id: string; title?: string; url?: string; publisher?: string; topics?: unknown; tags?: unknown; priority?: number }

const strings = (x: unknown): string[] => (Array.isArray(x) ? x.filter((v): v is string => typeof v === 'string').slice(0, 12) : [])

export function vote(a: Rated, value: number, now = Date.now()): Vote {
  return { id: a.id, title: a.title ?? '', url: a.url || '', publisher: a.publisher ?? '', topics: strings(a.topics), tags: strings(a.tags),
           value: value === -1 ? -1 : 1, at: new Date(now).toISOString() }
}

export function sanitizeVotes(input: unknown): Votes {
  const out: Votes = {}
  if (!input || typeof input !== 'object' || Array.isArray(input)) return out
  for (const [id, v] of Object.entries(input as Record<string, any>).slice(-2000)) {
    if (!v || ![-1, 1, 0].includes(v.value) || !Number.isFinite(Date.parse(v.at))) continue
    out[id] = { ...v, id, topics: strings(v.topics), tags: strings(v.tags),
                reason: v.reason in REASONS ? v.reason : undefined, note: typeof v.note === 'string' ? v.note.slice(0, 500) : undefined }
  }
  return out
}

export function affinity(a: Rated, votes: Votes, now = Date.now()): number {
  let delta = 0
  const ts = new Set(strings(a.tags)), topics = new Set(strings(a.topics))
  for (const v of Object.values(sanitizeVotes(votes))) {
    if (v.id === a.id) continue
    const decay = Math.pow(0.5, Math.max(0, now - Date.parse(v.at)) / (90 * 86400000))
    // "Already knew this" says nothing against the subject; "don't trust the source" is about the publisher.
    const subject = v.reason === 'seen' || v.reason === 'source' ? 0 : 1
    const publisher = v.reason === 'source' ? 4 : 0.25
    const sharedTags = v.tags.filter((t) => ts.has(t)).length
    const sharedTopics = v.topics.filter((t) => topics.has(t)).length
    delta += v.value * decay * (subject * (sharedTags * 3 + Math.min(1, sharedTopics) * 0.5) + (v.publisher === a.publisher ? publisher : 0))
  }
  return Math.max(-12, Math.min(12, delta))
}

export function score(a: Rated, votes: Votes, now = Date.now()): number {
  const direct = sanitizeVotes(votes)[a.id]
  return Number(a.priority || 0) + affinity(a, votes, now) + (direct?.value === 1 ? 15 : 0)
}
