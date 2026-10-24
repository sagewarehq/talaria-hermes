// Newsroom's data and state, shared by every design: the edition index, the latest or an archived edition, ranking
// by the device-local taste model, votes and saves (same localStorage keys as the original app), and pagination.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { setZone } from './format'
import { affinity, score, sanitizeVotes, vote, type Vote, type Votes } from './taste'

export type Evidence = { status: 'source-reviewed' | 'feed-only' | string; url?: string; note?: string }
export type Article = {
  id: string; title: string; url: string; publisher: string; topics: string[]; publishedAt: string
  summary?: string; discussionUrl?: string; image?: string
  priority: number; key: boolean; tags: string[]; why?: string; evidence?: Evidence
}
type Item = { id: string; priority: number; key: boolean; tags: string[]; why?: string; topics?: string[]; evidence?: Evidence }
export type Edition = { editionId?: string; editedAt: string; basisUpdatedAt?: string; summary?: string; coverageNotes?: string[]; items: Item[]; snapshots?: Article[] }
export type EditionEntry = { id: string; editedAt: string; date: string; count: number; summary?: string; path: string }
export type Mode = 'briefing' | 'saved' | 'preferences'
export type Feed = { url: string; title: string; topic: string; ok?: boolean | null; count?: number | null }
export type Settings = { version: number; timezone: string; topics: string[]; interests: string; feeds: Feed[]; frequency?: '6h' | '12h' | 'daily'; routine?: { id: string; installedAt: string } | null }
/** Where Newsroom is: not set up yet, set up and waiting for its first edition, or publishing. */
export type Phase = 'loading' | 'setup' | 'collecting' | 'ready'

export const PAGE = 10
export const LIMIT = 30
const STORE = { saved: 'newsroom-saved-v1', votes: 'newsroom-votes-v1' }
const IMAGE = /^\.\/images\/[a-f0-9]{16}\.(jpg|png|webp|gif|avif)$/

function readStore<T extends object>(key: string, fallback: T): [T, boolean] {
  try {
    const v = JSON.parse(localStorage.getItem(key) || 'null')
    return [v && typeof v === 'object' && !Array.isArray(v) ? v : fallback, true]
  } catch { return [fallback, false] }
}

const getJSON = (path: string) => fetch(path, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${path}: ${r.status}`))))
/** A JSON file that may not exist yet: undefined when it doesn't. */
const maybeJSON = (path: string) => fetch(path, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : r.status === 404 ? undefined : Promise.reject(new Error(`${path}: ${r.status}`))))
const requested = () => location.hash.match(/^#edition\/([0-9]{8}T[0-9]{12}Z)$/)?.[1] ?? null

export function useNewsroom() {
  const [settings, setSettings] = useState<Settings | null>()
  const [phase, setPhase] = useState<Phase>('loading')
  const [index, setIndex] = useState<EditionEntry[]>([])
  const [latestId, setLatestId] = useState<string>()
  const [selected, setSelected] = useState<string | null>(requested)
  const [edition, setEdition] = useState<Edition>()
  const [pool, setPool] = useState<Article[]>([])
  const [collectedAt, setCollectedAt] = useState<string>()
  const [query, setQueryState] = useState('')
  const [toast, setToast] = useState<{ message: string; undo?: { id: string; previous?: Vote } }>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [limit, setLimit] = useState(PAGE)
  const [mode, setMode] = useState<Mode>('briefing')
  const [broken, setBroken] = useState<Set<string>>(new Set())
  const [[saved, savedOK], setSavedState] = useState(() => readStore<Record<string, Article>>(STORE.saved, {}))
  const [[votes, votesOK], setVotesState] = useState<[Votes, boolean]>(() => { const [v, ok] = readStore(STORE.votes, {}); return [sanitizeVotes(v), ok] })
  const [storageOK, setStorageOK] = useState(savedOK && votesOK)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) { setLoading(true); setError(undefined) }
    try {
      const [s, idx] = await Promise.all([maybeJSON('/newsroom.json'), maybeJSON('/editions.json')])
      setSettings(s ?? null); setZone(s?.timezone)
      if (!idx) { setPhase(s ? 'collecting' : 'setup'); return }
      setPhase('ready')
      setIndex(idx.editions ?? []); setLatestId(idx.latestId)
      const id = requested()
      if (id) {
        const entry = (idx.editions ?? []).find((e: EditionEntry) => e.id === id)
        if (!entry) throw new Error('That edition is no longer in the archive.')
        setEdition(await getJSON('/' + entry.path.replace(/^\.?\//, ''))); setPool([])
      } else {
        const [ed, data] = await Promise.all([getJSON('/editorial.json'), getJSON('/data.json').catch(() => ({ articles: [] }))])
        setEdition(ed); setPool(data.articles ?? []); setCollectedAt(data.updatedAt)
      }
      setSelected(id)
    } catch (e) {
      if (!quiet) setError(e instanceof Error ? e.message : String(e))
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onHash = () => { setLimit(PAGE); load() }
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [load])
  // The latest view adopts a newly published edition; an archive never switches on its own.
  useEffect(() => {
    if (selected) return
    const tick = () => document.visibilityState === 'visible' && load(true)
    const t = setInterval(tick, 60000)
    document.addEventListener('visibilitychange', tick)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', tick) }
  }, [selected, load])

  const persist = (nextSaved: Record<string, Article>, nextVotes: Votes) => {
    try {
      localStorage.setItem(STORE.saved, JSON.stringify(nextSaved))
      localStorage.setItem(STORE.votes, JSON.stringify(nextVotes))
    } catch { setStorageOK(false) }
    setSavedState([nextSaved, true]); setVotesState([nextVotes, true])
  }

  const curated: Article[] = useMemo(() => {
    if (!edition) return []
    const all = new Map([...(edition.snapshots ?? []), ...(selected ? [] : pool)].map((a) => [a.id, a]))
    return edition.items.filter((e) => all.has(e.id)).map((e) => {
      const a = all.get(e.id)!
      return { ...a, ...e, topics: [...new Set([...(e.topics ?? []), ...(a.topics ?? [])])] } as Article
    })
  }, [edition, pool, selected])

  const ranked = useMemo(() => {
    let rows = mode === 'saved' ? Object.values(saved) : curated
    const q = query.trim().toLowerCase()
    rows = rows.filter((a) => (mode === 'saved' || selected || votes[a.id]?.value !== -1)
      && `${a.title} ${a.publisher} ${a.why ?? ''} ${(a.tags ?? []).join(' ')}`.toLowerCase().includes(q))
    rows = [...rows].sort((a, b) => (selected && mode === 'briefing' ? b.priority - a.priority : score(b, votes) - score(a, votes))
      || (b.publishedAt ?? '').localeCompare(a.publishedAt ?? ''))
    return mode === 'saved' ? rows : rows.slice(0, LIMIT)
  }, [curated, saved, votes, mode, selected, query])

  const imageOf = (a: Article) => (!broken.has(a.id) && IMAGE.test(a.image ?? '') ? a.image! : undefined)
  // At most three photo cards, only for key stories with real imagery, first; everything else is a headline row.
  const features = mode === 'briefing' ? ranked.filter((a) => a.key && imageOf(a)).slice(0, 3) : []
  const page = [...features, ...ranked.filter((a) => !features.includes(a))].slice(0, limit)
  const leads = page.filter((a) => features.includes(a))
  const rows = page.filter((a) => !features.includes(a))

  const position = index.findIndex((e) => e.id === (selected ?? latestId))
  const current = index[position]

  return {
    loading, error, retry: () => load(), storageOK, mode, query, phase, settings, reload: () => load(true),
    setQuery: (q: string) => { setQueryState(q); setLimit(PAGE) },
    setMode: (m: Mode) => { setMode(m); setLimit(PAGE); setQueryState(''); scrollTo({ top: 0 }) },
    newSources: mode === 'briefing' && !selected && Boolean(collectedAt && edition?.basisUpdatedAt && collectedAt !== edition.basisUpdatedAt),
    stale: Boolean(edition && Date.now() - new Date(edition.editedAt).getTime() > ({ '6h': 7, '12h': 13, daily: 25 }[settings?.frequency ?? '6h'] ?? 7) * 3600000),
    shown: page.length, affinity: (a: Article) => affinity(a, votes),
    // The edition's key developments (with or without imagery), for a summary of what matters most.
    // Every story in reading order (key photo cards first), for the reader's Next.
    ordered: [...features, ...ranked.filter((a) => !features.includes(a))],
    keys: mode === 'briefing' && !query ? ranked.filter((a) => a.key).slice(0, 3) : [],
    toast, dismissToast: () => setToast(undefined),
    edition, current, index, latestId, archived: Boolean(selected), total: ranked.length,
    leads, rows, imageOf, imageFailed: (id: string) => setBroken((s) => new Set(s).add(id)),
    more: limit < ranked.length ? () => setLimit((l) => Math.min(l + PAGE, ranked.length)) : undefined,
    remaining: Math.min(PAGE, ranked.length - limit),
    older: position >= 0 && position < index.length - 1 ? index[position + 1] : undefined,
    newer: position > 0 ? index[position - 1] : undefined,
    open: (id: string | null) => { location.hash = id && id !== latestId ? `edition/${id}` : '' ; scrollTo({ top: 0 }) },
    vote: votes, saved,
    rate: (a: Article, value: 1 | -1) => {
      const next = { ...votes }, previous = votes[a.id], removing = previous?.value === value
      if (removing) delete next[a.id]
      else next[a.id] = vote(a, value)
      persist(saved, next)
      setToast({ undo: { id: a.id, previous }, message: removing ? 'Feedback removed. Its ranking influence is gone.'
        : selected ? 'Saved for your latest briefing. This archive stays unchanged.'
        : value === -1 ? 'Hidden. Similar stories will rank lower.' : 'Got it. Related stories will rank higher.' })
    },
    undo: () => {
      const u = toast?.undo
      if (u) { const next = { ...votes }; if (u.previous) next[u.id] = u.previous; else delete next[u.id]; persist(saved, next) }
      setToast(undefined)
    },
    forget: (id: string) => {
      const next = { ...votes }; delete next[id]; persist(saved, next)
      setToast({ message: 'Feedback removed. Its ranking influence is gone.' })
    },
    exportVotes: () => {
      const blob = new Blob([JSON.stringify({ version: 1, app: 'newsroom', exportedAt: new Date().toISOString(), votes: Object.values(votes) }, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob), link = Object.assign(document.createElement('a'), { href: url, download: 'newsroom-feedback.json' })
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
      setToast({ message: 'Votes exported.' })
    },
    toggleSave: (a: Article) => {
      const next = { ...saved }
      if (next[a.id]) delete next[a.id]
      else next[a.id] = a
      persist(next, votes)
    },
  }
}

export type Newsroom = ReturnType<typeof useNewsroom>

/** The inline edition calendar's data: the published days of a month and the editions on the chosen day. */
export function calendar(index: EditionEntry[], month: string) {
  const days = new Map<string, EditionEntry[]>()
  for (const e of index) days.set(e.date, [...(days.get(e.date) ?? []), e])
  const [y, m] = month.split('-').map(Number)
  const first = new Date(Date.UTC(y, m - 1, 1)).getUTCDay()
  const count = new Date(Date.UTC(y, m, 0)).getUTCDate()
  const cells: (string | null)[] = [...Array(first).fill(null),
    ...Array.from({ length: count }, (_, i) => `${month}-${String(i + 1).padStart(2, '0')}`)]
  const months = [...new Set(index.map((e) => e.date.slice(0, 7)))].sort()
  return {
    cells, days,
    label: new Date(Date.UTC(y, m - 1, 1)).toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
    prev: months.filter((x) => x < month).at(-1), next: months.find((x) => x > month),
  }
}
