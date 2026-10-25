// Newsroom's data and state, shared by every design: the edition index, the latest or an archived edition, ranking
// by the device-local taste model, votes and saves (same localStorage keys as the original app), and pagination.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { action } from 'talaria'
import { setZone } from './format'
import { affinity, score, sanitizeVotes, vote, type Reason, type Vote, type Votes } from './taste'

export type Evidence = { status: 'source-reviewed' | 'feed-only' | string; url?: string; note?: string }
export type Article = {
  id: string; title: string; url: string; publisher: string; topics: string[]; publishedAt: string
  summary?: string; discussionUrl?: string; image?: string
  priority: number; key: boolean; tags: string[]; why?: string; evidence?: Evidence
  /** A story that ran in a recent edition, back for a new development: what changed. */
  update?: boolean; updateNote?: string
  /** A pick from beyond the reader's topics, to widen their taste: its area ("Science & Research", "Comics"). */
  discovery?: string
}
type Item = { id: string; priority: number; key: boolean; tags: string[]; why?: string; topics?: string[]; evidence?: Evidence; update?: boolean; updateNote?: string }
export type Edition = { editionId?: string; editedAt: string; basisUpdatedAt?: string; summary?: string; coverageNotes?: string[]; items: Item[]; snapshots?: Article[] }
export type EditionEntry = { id: string; editedAt: string; date: string; count: number; summary?: string; path: string }
export type Mode = 'briefing' | 'saved' | 'liked' | 'preferences'
/** A story on the reading list, with when it was saved. */
export type Saved = Article & { savedAt?: string }
type ReadLater = { items?: Record<string, { article: Article; savedAt: string }>; removed?: Record<string, string> }
export type Feed = { url: string; title: string; topic: string; ok?: boolean | null; count?: number | null }
export type Settings = { version: number; timezone: string; topics: string[]; interests: string; feeds: Feed[]; discovery?: boolean; frequency?: '6h' | '12h' | 'daily'; routine?: { id: string; installedAt: string } | null }
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
  // The story just marked 👎, while the reader is asked why.
  const [asking, setAsking] = useState<{ article: Article; previous?: Vote }>()
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [limit, setLimit] = useState(PAGE)
  const [mode, setMode] = useState<Mode>('briefing')
  const [broken, setBroken] = useState<Set<string>>(new Set())
  const [[saved, savedOK], setSavedState] = useState(() => readStore<Record<string, Saved>>(STORE.saved, {}))
  // The reading list is shared by every device through read-later.json (actions/saved.py); null until it's read.
  const [shared, setShared] = useState<boolean | null>(null)
  // Every device's votes, as the editor has them (reader-feedback.json), for Liked.
  const [synced, setSynced] = useState<Vote[]>([])
  const savedRef = useRef(saved)
  savedRef.current = saved
  const [[votes, votesOK], setVotesState] = useState<[Votes, boolean]>(() => { const [v, ok] = readStore(STORE.votes, {}); return [sanitizeVotes(v), ok] })
  const [storageOK, setStorageOK] = useState(savedOK && votesOK)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) { setLoading(true); setError(undefined) }
    try {
      const [s, idx] = await Promise.all([maybeJSON('newsroom.json'), maybeJSON('editions.json')])
      void syncLists()
      setSettings(s ?? null); setZone(s?.timezone)
      if (!idx) { setPhase(s ? 'collecting' : 'setup'); return }
      setPhase('ready')
      setIndex(idx.editions ?? []); setLatestId(idx.latestId)
      const id = requested()
      if (id) {
        const entry = (idx.editions ?? []).find((e: EditionEntry) => e.id === id)
        if (!entry) throw new Error('That edition is no longer in the archive.')
        setEdition(await getJSON(entry.path.replace(/^\.?\//, ''))); setPool([])
      } else {
        const [ed, data] = await Promise.all([getJSON('editorial.json'), getJSON('data.json').catch(() => ({ articles: [] }))])
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

  /** Read later and Liked from the server: adopt the shared reading list, and send it anything this device saved on
   *  its own (before the list was shared, or while it couldn't reach it) that wasn't removed since. */
  const syncLists = useCallback(async () => {
    const [list, feedback] = await Promise.all([
      maybeJSON('read-later.json').catch(() => null) as Promise<ReadLater | undefined | null>,
      maybeJSON('reader-feedback.json').catch(() => null) as Promise<{ votes?: Vote[] } | undefined | null>,
    ])
    if (feedback?.votes) setSynced(Object.values(sanitizeVotes(Object.fromEntries(feedback.votes.map((v) => [v.id, v])))))
    if (list === null) return setShared(false)
    const items = list?.items ?? {}, removed = list?.removed ?? {}
    const mine = Object.values(savedRef.current)
    // Saved here and not on the list: send it, unless another device removed it after it was saved here.
    const only = mine.filter((a) => !items[a.id] && !(removed[a.id] && removed[a.id] >= (a.savedAt ?? '')))
    const next: Record<string, Saved> = {}
    for (const [id, item] of Object.entries(items)) next[id] = { ...item.article, savedAt: item.savedAt }
    for (const a of only) next[a.id] = a
    try {
      for (let i = 0; i < only.length; i += 20) {
        await action('saved', { op: 'merge', items: only.slice(i, i + 20).map((a) => ({ article: a, savedAt: a.savedAt })) })
      }
      setShared(true)
    } catch {
      setShared(list !== undefined)
    }
    persistSaved(next)
  }, [])

  const persistSaved = (next: Record<string, Saved>) => {
    try { localStorage.setItem(STORE.saved, JSON.stringify(next)) } catch { setStorageOK(false) }
    setSavedState([next, true])
  }

  const persist = (nextSaved: Record<string, Saved>, nextVotes: Votes) => {
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

  // Liked: every story given 👍 on any device, the latest vote on each story deciding, newest first.
  const liked = useMemo(() => {
    const latest = new Map<string, Vote>()
    for (const v of [...synced, ...Object.values(votes)]) if (v.at >= (latest.get(v.id)?.at ?? '')) latest.set(v.id, v)
    const known = new Map([...pool, ...curated, ...Object.values(saved)].map((a) => [a.id, a]))
    return [...latest.values()].filter((v) => v.value === 1).sort((a, b) => b.at.localeCompare(a.at)).map((v) => ({
      ...(known.get(v.id) ?? { id: v.id, title: v.title, url: v.url, publisher: v.publisher, topics: v.topics, tags: v.tags,
                               publishedAt: v.at, priority: 0, key: false }),
      likedAt: v.at,
    }) as Article & { likedAt: string })
  }, [synced, votes, pool, curated, saved])

  const ranked = useMemo(() => {
    const q = query.trim().toLowerCase()
    const matches = (a: Article) => `${a.title} ${a.publisher} ${a.why ?? ''} ${(a.tags ?? []).join(' ')}`.toLowerCase().includes(q)
    // The lists are by recency: Read later by when it was saved, Liked by when it was liked.
    if (mode === 'saved') {
      return Object.values(saved).filter(matches)
        .sort((a, b) => (b.savedAt ?? b.publishedAt ?? '').localeCompare(a.savedAt ?? a.publishedAt ?? ''))
    }
    if (mode === 'liked') return liked.filter(matches)
    let rows = curated.filter((a) => (selected || votes[a.id]?.value !== -1) && matches(a))
    rows = [...rows].sort((a, b) => (selected ? b.priority - a.priority : score(b, votes) - score(a, votes))
      || (b.publishedAt ?? '').localeCompare(a.publishedAt ?? ''))
    return rows.slice(0, LIMIT)
  }, [curated, saved, liked, votes, mode, selected, query])
  // Discovery picks close the briefing in a section of their own rather than ranking among the reader's topics;
  // a search finds them like any story.
  const apart = mode === 'briefing' && !query.trim()
  const discover = apart ? ranked.filter((a) => a.discovery) : []
  const main = apart ? ranked.filter((a) => !a.discovery) : ranked

  const imageOf = (a: Article) => (!broken.has(a.id) && IMAGE.test(a.image ?? '') ? a.image! : undefined)
  // At most three photo cards, only for key stories with real imagery, first; everything else is a headline row.
  const features = mode === 'briefing' ? main.filter((a) => a.key && imageOf(a)).slice(0, 3) : []
  const page = [...features, ...main.filter((a) => !features.includes(a))].slice(0, limit)
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
    ordered: [...features, ...main.filter((a) => !features.includes(a)), ...discover.filter((a) => a.discovery !== 'Comics')],
    keys: mode === 'briefing' && !query ? main.filter((a) => a.key).slice(0, 3) : [],
    toast, dismissToast: () => setToast(undefined),
    edition, current, index, latestId, archived: Boolean(selected), total: main.length,
    leads, rows, imageOf,
    // Shown once the reader has reached the end of the edition's own stories.
    discover: limit >= main.length ? discover : [], imageFailed: (id: string) => setBroken((s) => new Set(s).add(id)),
    more: limit < main.length ? () => setLimit((l) => Math.min(l + PAGE, main.length)) : undefined,
    remaining: Math.min(PAGE, main.length - limit),
    older: position >= 0 && position < index.length - 1 ? index[position + 1] : undefined,
    newer: position > 0 ? index[position - 1] : undefined,
    open: (id: string | null) => { location.hash = id && id !== latestId ? `edition/${id}` : '' ; scrollTo({ top: 0 }) },
    vote: votes, saved, shared, likedCount: liked.length,
    rate: (a: Article, value: 1 | -1) => {
      const next = { ...votes }, previous = votes[a.id], removing = previous?.value === value
      if (removing) delete next[a.id]
      else next[a.id] = vote(a, value)
      persist(saved, next)
      if (value === -1 && !removing && !selected) { setToast(undefined); setAsking({ article: a, previous }); return }
      setToast({ undo: { id: a.id, previous }, message: removing ? 'Feedback removed. Its ranking influence is gone.'
        : selected ? 'Saved for your latest briefing. This archive stays unchanged.'
        : value === -1 ? 'Hidden. Similar stories will rank lower.' : 'Got it. Related stories will rank higher.' })
    },
    asking: asking?.article,
    /** The reader's answer to "what's off?": kept with the 👎, for this device's ranking and for the editor. */
    explain: (reason?: Reason, note?: string) => {
      const a = asking?.article
      setAsking(undefined)
      if (!a || !votes[a.id]) return
      const text = note?.trim().slice(0, 500)
      if (reason || text) persist(saved, { ...votes, [a.id]: { ...votes[a.id], reason, note: text || undefined } })
      setToast({ undo: { id: a.id, previous: asking?.previous },
                 message: reason || text ? 'Thanks. Your editor will see why.' : 'Hidden. Similar stories will rank lower.' })
    },
    undoAsking: () => {
      const u = asking
      setAsking(undefined)
      if (!u) return
      const next = { ...votes }; if (u.previous) next[u.article.id] = u.previous; else delete next[u.article.id]; persist(saved, next)
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
    /** Read later: on this device at once, and on every other one through read-later.json. */
    toggleSave: (a: Article) => {
      const next = { ...saved }, at = new Date().toISOString(), removing = Boolean(next[a.id])
      if (removing) delete next[a.id]
      else next[a.id] = { ...a, savedAt: at }
      persistSaved(next)
      const { likedAt: _, savedAt: __, ...story } = a as Saved & { likedAt?: string }
      action('saved', removing ? { op: 'remove', id: a.id, at } : { op: 'add', article: story, at })
        .then(() => setShared(true), () => setShared(false))
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
