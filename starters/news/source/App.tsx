import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion, useScroll, useTransform } from 'motion/react'
import {
  ArrowUpRight, Bookmark, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Clock, Download,
  Inbox, MessageSquare, Newspaper, Search, ShieldCheck, SlidersHorizontal, Sparkles, ThumbsDown, ThumbsUp, Undo2, X,
} from 'lucide-react'
import { Actions } from '@shared/newsroom/Icons'
import { age, editionDay, editionTime, host, topicName, zoneName } from '@shared/newsroom/format'
import { usePicker } from '@shared/newsroom/usePicker'
import { LIMIT, useNewsroom, type Article, type Feed, type Newsroom } from '@shared/newsroom/useNewsroom'
import { ReaderProvider, useReader } from './Reader'
import { AddSource, Collecting, FrequencyPicker, Setup, TopicPicker, nextEditions, type Frequency } from './Setup'
import { action } from 'talaria'

/** A story's link opens the in-app reader; its href stays for long-press and accessibility. */
function useLink() {
  const { open } = useReader()
  return (a: Article) => ({ href: a.url, onClick: (e: React.MouseEvent) => { e.preventDefault(); open(a.id) } })
}

const spring = { type: 'spring', bounce: 0.18, duration: 0.5 } as const

export default function App() {
  const nr = useNewsroom()
  useVoteSync(nr)
  if (nr.phase === 'setup') return <Setup nr={nr} />
  if (nr.phase === 'collecting') return <Collecting nr={nr} />
  return (
    <ReaderProvider nr={nr} Source={Source} Topic={Topic}>
    <div className="mx-auto max-w-[1100px] px-4 min-[700px]:px-7"
      style={{ paddingTop: 'calc(env(safe-area-inset-top) + 48px)', paddingBottom: 'calc(env(safe-area-inset-bottom) + 112px)' }}>
      <Masthead nr={nr} />
      {nr.mode === 'briefing' && <EditionBar nr={nr} />}
      <Notices nr={nr} />
      {nr.mode !== 'preferences' && <SearchField nr={nr} />}
      <SectionHead nr={nr} />
      <AnimatePresence mode="wait" initial={false}>
        <motion.main key={nr.mode + (nr.current?.id ?? '')} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.22 }}>
          {nr.mode === 'preferences' ? <Preferences nr={nr} /> : <Feed nr={nr} />}
        </motion.main>
      </AnimatePresence>
      <Toast nr={nr} />
      <Nav nr={nr} />
    </div>
    </ReaderProvider>
  )
}

/** Send the phone's votes to the editor (reader-feedback.json) a moment after they change. Quietly does nothing
 *  where actions can't run: the votes still rank this device's edition. */
function useVoteSync(nr: Newsroom) {
  const key = JSON.stringify(Object.keys(nr.vote).sort().map((k) => [k, nr.vote[k].value]))
  useEffect(() => {
    if (nr.phase !== 'ready') return
    const t = setTimeout(() => action('feedback', { votes: Object.values(nr.vote) }).catch(() => {}), 2500)
    return () => clearTimeout(t)
  }, [key, nr.phase])
}

/* ——— Masthead ——— */

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
      <defs><linearGradient id="nm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#4c8df6" /><stop offset="1" stopColor="#185abc" /></linearGradient></defs>
      <rect width="32" height="32" rx="9" fill="url(#nm)" />
      <rect x="7" y="8" width="18" height="3" rx="1.5" fill="#fff" />
      <rect x="7" y="14" width="8" height="10" rx="2" fill="#fff" fillOpacity=".55" />
      <rect x="17" y="14" width="8" height="2.4" rx="1.2" fill="#fff" fillOpacity=".85" />
      <rect x="17" y="18" width="8" height="2.4" rx="1.2" fill="#fff" fillOpacity=".85" />
      <rect x="17" y="22" width="5" height="2.4" rx="1.2" fill="#fff" fillOpacity=".85" />
    </svg>
  )
}

function Masthead({ nr }: { nr: Newsroom }) {
  const { scrollY } = useScroll()
  const fade = useTransform(scrollY, [0, 80], [1, 0.35])
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  return (
    <motion.header style={{ opacity: fade }} className="flex items-center gap-3 pt-1">
      <motion.div initial={{ scale: 0.6, rotate: -12, opacity: 0 }} animate={{ scale: 1, rotate: 0, opacity: 1 }} transition={{ type: 'spring', bounce: 0.5, duration: 0.7 }}><Mark /></motion.div>
      <div className="min-w-0">
        <h1 className="display text-[25px] leading-[1.05] font-[650] tracking-[-0.02em]">Newsroom</h1>
        <p className="text-[12.5px] text-[var(--muted)]">{today}</p>
      </div>
    </motion.header>
  )
}

/* ——— Edition bar and the inline calendar ——— */

function EditionBar({ nr }: { nr: Newsroom }) {
  const p = usePicker(nr)
  const ed = nr.current
  const go = (id?: string) => id && nr.open(id)
  return (
    <section className="mt-4 overflow-hidden rounded-[18px] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow)] min-[700px]:max-w-[480px]">
      <div className="grid grid-cols-[44px_1fr_44px] items-center p-0.5">
        <button className="act disabled:opacity-30" disabled={!nr.older} aria-label="Previous edition" onClick={() => go(nr.older?.id)}><ChevronLeft size={19} /></button>
        <button className="flex h-12 flex-col items-center justify-center rounded-[14px] active:bg-[var(--surface-2)]" aria-expanded={p.open} onClick={p.toggle}>
          <span className="flex items-center gap-1.5 text-[14.5px] font-[620] tabular-nums">
            {ed ? `${editionDay(ed.editedAt)}, ${editionTime(ed.editedAt)}` : <span className="shimmer h-4 w-28 rounded" />}
            <motion.span animate={{ rotate: p.open ? 180 : 0 }}><ChevronDown size={15} className="text-[var(--muted)]" /></motion.span>
          </span>
          <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--muted)]">
            {!nr.archived && (
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--green)] opacity-50 motion-reduce:hidden" />
                <span className="relative h-1.5 w-1.5 rounded-full bg-[var(--green)]" />
              </span>
            )}
            {nr.archived ? 'Past edition' : nr.stale ? 'Latest · may be out of date' : 'Latest'} · {zoneName()} time
          </span>
        </button>
        <button className="act disabled:opacity-30" disabled={!nr.newer} aria-label="Next edition" onClick={() => go(nr.newer?.id)}><ChevronRight size={19} /></button>
      </div>
      <AnimatePresence initial={false}>
        {p.open && p.cal && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={spring} className="overflow-hidden">
            <div className="border-t border-[var(--hair)] px-2 pt-1 pb-3">
              <div className="flex items-center justify-between">
                <button className="act disabled:opacity-25" disabled={!p.cal.prev} aria-label="Previous month" onClick={() => p.cal?.prev && p.setMonth(p.cal.prev)}><ChevronLeft size={17} /></button>
                <span className="text-[14.5px] font-[620]">{p.cal.label}</span>
                <button className="act disabled:opacity-25" disabled={!p.cal.next} aria-label="Next month" onClick={() => p.cal?.next && p.setMonth(p.cal.next)}><ChevronRight size={17} /></button>
              </div>
              <div className="grid grid-cols-7 text-center">
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => <span key={i} className="pb-1 text-[11px] font-semibold text-[var(--faint)]">{d}</span>)}
                {p.cal.cells.map((d, i) => {
                  if (!d) return <span key={i} />
                  const has = p.cal!.days.has(d), on = d === p.day
                  return (
                    <button key={i} disabled={!has} onClick={() => p.setDay(d)} aria-pressed={on} aria-label={`${d}${has ? ', published editions' : ''}`}
                      className="relative mx-auto grid h-11 w-11 place-items-center text-[14px] font-[560] tabular-nums disabled:font-normal disabled:text-[var(--faint)] disabled:opacity-45">
                      {on && <motion.span layoutId="day" transition={spring} className="absolute inset-[3px] rounded-full bg-[var(--blue)]" />}
                      <span className={`relative ${on ? 'text-[var(--surface)]' : ''}`}>{Number(d.slice(8))}</span>
                      {has && !on && <span className="absolute bottom-[6px] h-1 w-1 rounded-full bg-[var(--blue)]" />}
                    </button>
                  )
                })}
              </div>
              <div className="mt-2 space-y-1.5 px-1">
                {p.times.map((e) => {
                  const on = e.id === ed?.id
                  return (
                    <button key={e.id} onClick={() => p.choose(e.id)} aria-pressed={on}
                      className={`flex h-12 w-full items-center justify-between rounded-[12px] px-3.5 text-left transition-colors ${on ? 'bg-[var(--tint)] text-[var(--blue)]' : 'bg-[var(--surface-2)] active:bg-[var(--hair)]'}`}>
                      <span className="flex items-center gap-2.5"><Clock size={15} className="opacity-70" />
                        <span className="text-[14px] font-[620] tabular-nums">{editionTime(e.editedAt)}</span>
                        <span className="text-[12.5px] text-[var(--muted)]">{e.count} stories{e.id === nr.latestId ? ' · Latest' : ''}</span></span>
                      {on ? <Check size={16} /> : <ChevronRight size={16} className="text-[var(--faint)]" />}
                    </button>
                  )
                })}
              </div>
              {nr.archived && (
                <button className="mt-2 flex h-11 w-full items-center justify-center gap-1.5 text-[13.5px] font-[620] text-[var(--blue)]" onClick={() => p.choose(nr.latestId!)}>
                  Return to latest <ArrowUpRight size={14} />
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}

/* ——— Notices, search and the section head ——— */

function Notices({ nr }: { nr: Newsroom }) {
  return (
    <AnimatePresence>
      {!nr.storageOK && (
        <motion.p key="storage" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-3 rounded-[14px] bg-[var(--red-tint)] px-3.5 py-2.5 text-[13.5px] text-[var(--red)]">
          Device storage is unavailable. Votes and saved stories will last only for this visit.
        </motion.p>
      )}
      {nr.error ? (
        <motion.div key="error" role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="mt-3 flex items-center justify-between gap-3 rounded-[14px] bg-[var(--red-tint)] px-3.5 py-1.5 text-[13.5px] text-[var(--red)]">
          <span>{nr.archived ? 'Unable to open this archived edition.' : 'Unable to load a reviewed edition. Saved stories and preferences are still here.'}</span>
          <button className="h-11 shrink-0 font-[650]" onClick={nr.retry}>Try again</button>
        </motion.div>
      ) : nr.newSources && (
        <motion.div key="sources" role="status" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="mt-3 flex items-center gap-2.5 rounded-[14px] bg-[var(--tint)] px-3.5 py-2.5 text-[13px] text-[var(--blue)]">
          <Sparkles size={16} className="shrink-0" />
          <span><strong className="font-[650]">New sources collected.</strong> The next edited edition is on its way; showing the latest reviewed one.</span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function SearchField({ nr }: { nr: Newsroom }) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <label className="group mt-3 flex h-12 items-center gap-2.5 rounded-[14px] border border-[var(--line)] bg-[var(--surface)] px-3.5 transition-shadow focus-within:border-[var(--blue)] focus-within:shadow-[0_0_0_3px_var(--tint)] min-[700px]:max-w-[480px]">
      <Search size={17} className="text-[var(--muted)] group-focus-within:text-[var(--blue)]" />
      <input ref={ref} value={nr.query} onChange={(e) => nr.setQuery(e.target.value)} type="search" enterKeyHint="search"
        placeholder={nr.mode === 'saved' ? 'Search saved stories' : 'Search this edition'}
        className="h-full min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-[var(--faint)] [&::-webkit-search-cancel-button]:hidden" />
      <AnimatePresence>
        {nr.query && (
          <motion.button initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} aria-label="Clear search"
            className="-mr-2 grid h-11 w-11 place-items-center" onClick={() => { nr.setQuery(''); ref.current?.focus() }}>
            <span className="grid h-5 w-5 place-items-center rounded-full bg-[var(--faint)] text-[var(--surface)]"><X size={12} strokeWidth={3} /></span>
          </motion.button>
        )}
      </AnimatePresence>
    </label>
  )
}

function SectionHead({ nr }: { nr: Newsroom }) {
  // The edition speaks for itself: nothing over it, except the match count while searching.
  if (nr.mode === 'briefing') {
    return nr.query ? <p className="mt-4 text-[12.5px] font-[600] text-[var(--muted)]">{nr.total} matching {nr.total === 1 ? 'story' : 'stories'}</p> : null
  }
  if (nr.mode === 'preferences') return <h2 className="display mt-6 text-[23px] leading-tight font-[650] tracking-[-0.015em]">Preferences</h2>
  const title = 'Saved stories'
  const count = `${nr.total} ${nr.total === 1 ? 'story' : 'stories'}`
  const sub = 'Saved on this device'
  return (
    <div className="mt-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="display text-[23px] leading-tight font-[650] tracking-[-0.015em]">{title}</h2>
        <motion.span key={count} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="shrink-0 rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 text-[12px] font-[600] text-[var(--muted)] tabular-nums">{count}</motion.span>
      </div>
      <p className="mt-0.5 text-[12.5px] text-[var(--muted)]">{sub}</p>
    </div>
  )
}

/** The average colour of an image, for an ambient glow behind it. Same-origin images only, which ours are. */
function useAmbient(src?: string) {
  const [color, setColor] = useState<string>()
  useEffect(() => {
    if (!src) return
    const img = new Image()
    img.onload = () => {
      try {
        const c = document.createElement('canvas'); c.width = c.height = 12
        const ctx = c.getContext('2d')!; ctx.drawImage(img, 0, 0, 12, 12)
        const d = ctx.getImageData(0, 0, 12, 12).data
        let r = 0, g = 0, b = 0
        for (let k = 0; k < d.length; k += 4) { r += d[k]; g += d[k + 1]; b += d[k + 2] }
        const n = d.length / 4
        setColor(`rgb(${Math.round(r / n)} ${Math.round(g / n)} ${Math.round(b / n)})`)
      } catch { /* a tainted canvas just means no glow */ }
    }
    img.src = src
  }, [src])
  return color
}

/* ——— The edition ——— */

function Feed({ nr }: { nr: Newsroom }) {
  if (nr.loading && !nr.edition) return <Skeleton />
  const empty = nr.leads.length + nr.rows.length === 0
  if (empty) return <Empty nr={nr} />
  return (
    <LayoutGroup>
      {nr.leads[0] && <Cover a={nr.leads[0]} nr={nr} />}
      {nr.leads.length > 1 && (
        <section aria-label="More key developments" className="mt-7">
          <h3 className="text-[12px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase">More key developments</h3>
          <div className="no-scrollbar -mx-4 mt-2.5 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-4 px-4 pb-2 min-[700px]:mx-0 min-[700px]:px-0">
            {nr.leads.slice(1).map((a, i) => <Feature key={a.id} a={a} nr={nr} i={i} only={nr.leads.length === 2} />)}
          </div>
        </section>
      )}
      {nr.rows.length > 0 && (
        <section aria-label="Supporting coverage" className="mt-7 min-[700px]:max-w-[860px]">
          <h3 className="text-[12px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase">
            {nr.mode === 'saved' ? 'Your reading list' : nr.leads.length ? 'Also worth your attention' : 'Worth your attention'}
          </h3>
          <AnimatePresence initial={false}>
            {nr.rows.map((a, i) => <Row key={a.id} a={a} nr={nr} i={i} rank={nr.mode === 'briefing' ? nr.leads.length + i + 1 : undefined} />)}
          </AnimatePresence>
        </section>
      )}
      <Boundary nr={nr} />
    </LayoutGroup>
  )
}

const MARKS: Record<string, [string, string]> = { 'Hacker News': ['Y', '#ff6600'], TechCrunch: ['TC', '#0a9e01'], 'The Verge': ['V', '#5200ff'],
  'Ars Technica': ['ars', '#ff4e00'], BleepingComputer: ['B', '#1f6fb5'], 'Krebs on Security': ['K', '#3a3a3a'], OpenAI: ['O', '#10a37f'] }
function SourceMark({ publisher }: { publisher: string }) {
  const [label, color] = MARKS[publisher] ?? [publisher.slice(0, 1), `hsl(${[...publisher].reduce((h, c) => h + c.charCodeAt(0), 0) % 360} 45% 45%)`]
  return <span className="grid h-[18px] min-w-[18px] place-items-center rounded-[5px] px-[3px] text-[9px] leading-none font-[800] text-white" style={{ background: color }}>{label}</span>
}

const TOPICS: Record<string, string> = { Cybersecurity: '#d93025', AI: '#7c4dff', Engineering: '#00897b', Fintech: '#188038', Startups: '#e37400', Technology: '#1a73e8' }
const tagOf = (a: Article) => topicName(a.topics.includes('Cybersecurity') ? 'Cybersecurity' : a.topics[0] ?? 'News')

function Topic({ a, keyStory, className = '' }: { a: Article; keyStory?: boolean; className?: string }) {
  const tag = tagOf(a), color = TOPICS[tag] ?? 'var(--muted)'
  return (
    <span className={`flex shrink-0 items-center gap-1 text-[11px] font-[650] ${className}`} style={{ color }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />{keyStory ? 'Key · ' : ''}{tag}
    </span>
  )
}

function Source({ a, keyStory, compact }: { a: Article; keyStory?: boolean; compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-[12px] text-[var(--muted)]">
      <SourceMark publisher={a.publisher} />
      <span className="truncate font-[560] text-[var(--text)] opacity-80">{a.publisher}</span>
      <span className="shrink-0 text-[var(--faint)]">· {age(a.publishedAt)}</span>
      {!compact && <Topic a={a} keyStory={keyStory} className="ml-auto pl-2" />}
    </div>
  )
}

function Cover({ a, nr }: { a: Article; nr: Newsroom }) {
  const link = useLink()
  const [loaded, setLoaded] = useState(false)
  const glow = useAmbient(nr.imageOf(a))
  return (
    <motion.article id={`story-${a.id}`} layout="position" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.1 }}
      className="relative -mx-4 mt-6 scroll-mt-24 min-[700px]:mx-0 min-[700px]:max-w-[860px]">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-x-0 top-[30%] h-[70%] opacity-40 blur-3xl transition-colors duration-700 dark:opacity-30"
          style={{ background: glow ? `radial-gradient(70% 60% at 50% 20%, ${glow}, transparent 70%)` : undefined }} />
      </div>
      <a {...link(a)} aria-label={`Read: ${a.title}`} className="relative block overflow-hidden bg-[var(--surface-2)] min-[700px]:rounded-[22px]">
        {!loaded && <div className="shimmer absolute inset-0" />}
        <motion.img src={nr.imageOf(a)} alt="" decoding="async" onLoad={() => setLoaded(true)} onError={() => nr.imageFailed(a.id)}
          initial={false} animate={{ opacity: loaded ? 1 : 0, scale: loaded ? 1 : 1.05 }} transition={{ duration: 0.7 }} className="aspect-[1.9] w-full object-cover" />
      </a>
      <div className="relative px-4 pt-3.5 min-[700px]:px-1">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[var(--text)] px-2 py-[3px] text-[10.5px] font-[750] tracking-[0.06em] text-[var(--bg)] uppercase">Cover story</span>
          <Topic a={a} />
        </div>
        <a {...link(a)}
          className="display mt-2 block text-[27px] leading-[1.1] font-[720] tracking-[-0.025em] text-[var(--text)] active:text-[var(--blue)]">{a.title}</a>
        <p className="mt-2 text-[15.5px] leading-[1.5] text-[var(--muted)]">{a.why}</p>
        <div className="mt-2.5"><Source a={a} compact /></div>
        <Foot a={a} nr={nr} />
      </div>
    </motion.article>
  )
}

function Feature({ a, nr, i, only }: { a: Article; nr: Newsroom; i: number; only: boolean }) {
  const link = useLink()
  const [loaded, setLoaded] = useState(false)
  return (
    <motion.article id={`story-${a.id}`} layout="position" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }}
      transition={{ ...spring, delay: 0.15 + i * 0.08 }}
      className={`flex shrink-0 snap-start scroll-mt-24 flex-col overflow-hidden rounded-[20px] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow)] ${only ? 'w-full' : 'w-[80%] min-[700px]:w-[calc(50%-6px)]'}`}>
      <a {...link(a)} aria-label={`Read: ${a.title}`} className="relative block overflow-hidden bg-[var(--surface-2)]">
        {!loaded && <div className="shimmer absolute inset-0" />}
        <motion.img src={nr.imageOf(a)} alt="" decoding="async" onLoad={() => setLoaded(true)} onError={() => nr.imageFailed(a.id)}
          initial={false} animate={{ opacity: loaded ? 1 : 0 }} transition={{ duration: 0.6 }} className="aspect-[1.9] w-full object-cover" />
      </a>
      <div className="flex flex-1 flex-col px-3.5 pt-3">
        <Topic a={a} keyStory className="mb-1" />
        <Source a={a} compact />
        <a {...link(a)}
          className="display mt-1.5 text-[17.5px] leading-[1.22] font-[660] tracking-[-0.012em] text-[var(--text)] active:text-[var(--blue)]">{a.title}</a>
        <p className="mt-1 line-clamp-3 text-[13.5px] leading-[1.5] text-[var(--muted)]">{a.why}</p>
        <div className="mt-auto"><Foot a={a} nr={nr} lean /></div>
      </div>
    </motion.article>
  )
}

function Row({ a, nr, i, rank }: { a: Article; nr: Newsroom; i: number; rank?: number }) {
  const link = useLink()
  const { read } = useReader()
  return (
    <motion.article id={`story-${a.id}`} layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0, transition: { duration: 0.28 } }}
      transition={{ ...spring, delay: Math.min(i, 8) * 0.025 }}
      className={`grid scroll-mt-24 overflow-hidden border-b border-[var(--hair)] pt-4 pb-0.5 ${rank ? 'grid-cols-[34px_1fr] gap-x-1' : ''}`}>
      {rank && (
        <motion.span key={rank} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
          className="display pt-[1px] text-[25px] leading-none font-[250] tracking-[-0.04em] text-[var(--faint)] tabular-nums">{String(rank).padStart(2, '0')}</motion.span>
      )}
      <div className="min-w-0">
        <Source a={a} />
        <a {...link(a)} className={`display mt-1 block text-[18px] leading-[1.3] font-[620] tracking-[-0.01em] active:text-[var(--blue)] ${read.has(a.id) ? 'text-[var(--muted)]' : ''}`}>
          {read.has(a.id) && <span className="mr-1.5 inline-flex -translate-y-[2px] items-center gap-0.5 rounded-full bg-[var(--surface-2)] px-1.5 py-[1px] align-middle text-[10.5px] font-[650] text-[var(--faint)]"><Check size={11} strokeWidth={3} />Read</span>}
          {a.title}
        </a>
        <p className="mt-1 text-[14px] leading-[1.55] text-[var(--muted)]">{a.why || 'Saved for your reading list.'}</p>
        <Foot a={a} nr={nr} />
      </div>
    </motion.article>
  )
}

function Foot({ a, nr, compact, lean }: { a: Article; nr: Newsroom; compact?: boolean; lean?: boolean }) {
  const [open, setOpen] = useState(false)
  const reviewed = a.evidence?.status === 'source-reviewed'
  const learned = !nr.archived && Math.abs(nr.affinity(a)) > 0.5
  return (
    <div className="pb-1">
      <div className={`flex items-center ${compact ? '-mx-2 flex-col items-stretch' : '-mr-2.5'}`}>
        <button aria-expanded={open} onClick={() => setOpen(!open)} className={`flex h-11 items-center gap-1 whitespace-nowrap text-[12.5px] font-[620] text-[var(--blue)] ${compact ? 'order-2 -mt-2 px-2' : ''}`}>
          {compact ? 'Why?' : 'Why this story?'} <motion.span animate={{ rotate: open ? 180 : 0 }}><ChevronDown size={14} /></motion.span>
        </button>
        <div className={`flex items-center ${compact ? 'justify-between' : 'ml-auto'}`}>
          {!compact && !lean && a.discussionUrl && <a className="act" href={a.discussionUrl} target="_blank" rel="noopener noreferrer" aria-label="Hacker News discussion"><MessageSquare size={16} /></a>}
          <Actions a={a} nr={nr} button="act" />
        </div>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={spring} className="overflow-hidden">
            <div className="mb-2 rounded-[14px] bg-[var(--surface-2)] p-3 text-[13.5px] leading-[1.55]">
              {compact && <p className="text-[var(--text)]">{a.why}</p>}
              {learned && <p className="mt-1 flex gap-1.5 text-[var(--blue)]"><SlidersHorizontal size={14} className="mt-[3px] shrink-0" />Your feedback on related stories also moved it on this device.</p>}
              <p className={`flex gap-1.5 font-[620] ${compact || learned ? 'mt-2' : ''} ${reviewed ? 'text-[var(--green)]' : 'text-[var(--muted)]'}`}>
                {reviewed ? <ShieldCheck size={15} className="mt-[2px] shrink-0" /> : <Newspaper size={15} className="mt-[2px] shrink-0" />}
                {reviewed ? 'Canonical source reviewed' : 'Feed metadata only'}
              </p>
              <p className="mt-0.5 text-[var(--muted)]">{a.evidence?.note || 'Not independently verified.'}</p>
              {(a.evidence?.url || a.discussionUrl) && (
                <div className="mt-1.5 flex flex-wrap gap-x-4">
                  {a.evidence?.url && <a className="inline-flex h-9 items-center gap-1 font-[620] text-[var(--blue)]" href={a.evidence.url} target="_blank" rel="noopener noreferrer">Source evidence · {host(a.evidence.url)}<ArrowUpRight size={13} /></a>}
                  {(compact || lean) && a.discussionUrl && <a className="inline-flex h-9 items-center gap-1 font-[620] text-[var(--blue)]" href={a.discussionUrl} target="_blank" rel="noopener noreferrer">HN discussion<ArrowUpRight size={13} /></a>}
                </div>
              )}
              {a.tags?.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{a.tags.map((t) => <span key={t} className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-[11.5px] text-[var(--muted)]">{t.replaceAll('-', ' ')}</span>)}</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Boundary({ nr }: { nr: Newsroom }) {
  const pct = nr.total ? nr.shown / nr.total : 0
  return (
    <section aria-label="Edition progress" className="mt-6 min-[700px]:max-w-[860px]">
      <div className="flex items-center gap-3 text-[12px] text-[var(--muted)] tabular-nums">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-[var(--hair)]">
          <motion.div className="h-full rounded-full bg-[var(--blue)]" initial={false} animate={{ width: `${pct * 100}%` }} transition={spring} />
        </div>
        <span>{nr.shown} of {nr.total}{nr.mode === 'briefing' ? ` · max ${LIMIT}` : ''}</span>
      </div>
      {nr.more ? (
        <motion.button whileTap={{ scale: 0.97 }} onClick={() => { const y = scrollY; nr.more!(); requestAnimationFrame(() => scrollTo({ top: y })) }}
          className="mt-4 flex h-12 w-full items-center justify-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] text-[14.5px] font-[620] text-[var(--blue)] shadow-[var(--shadow)] active:bg-[var(--tint)]">
          Show {nr.remaining} more {nr.remaining === 1 ? 'story' : 'stories'} <ChevronDown size={16} />
        </motion.button>
      ) : (
        <motion.div initial={{ opacity: 0, scale: 0.96 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} className="mt-6 flex flex-col items-center text-center">
          <motion.span initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ type: 'spring', bounce: 0.55, delay: 0.1 }}
            className="grid h-12 w-12 place-items-center rounded-full bg-[var(--tint)] text-[var(--blue)]"><CircleCheck size={24} /></motion.span>
          <h3 className="display mt-2.5 text-[18px] font-[650]">{nr.mode === 'saved' ? 'End of your reading list' : nr.query ? 'End of matching stories' : 'End of this edition'}</h3>
          <p className="mt-0.5 max-w-[300px] text-[13.5px] text-[var(--muted)]">
            {nr.mode === 'saved' ? 'Saved stories stay on this device.' : nr.archived ? 'This edition is preserved as published.'
              : nr.query ? 'Clear your search to see the rest of the edition.' : `You’re caught up. The next edition arrives ${({ '6h': 'within six hours', '12h': 'within twelve hours', daily: 'tomorrow morning' } as const)[nr.settings?.frequency ?? '6h']}.`}
          </p>
          {nr.mode === 'briefing' && (
            <button className="mt-2 flex h-11 items-center gap-1.5 text-[13.5px] font-[620] text-[var(--blue)]" onClick={() => { scrollTo({ top: 0, behavior: 'smooth' }); document.querySelector<HTMLButtonElement>('[aria-expanded]')?.click() }}>
              <CalendarDays size={15} /> Browse past editions
            </button>
          )}
        </motion.div>
      )}
    </section>
  )
}

function Empty({ nr }: { nr: Newsroom }) {
  const [title, body] = nr.query ? ['No matching stories', 'Try a different search.'] : nr.mode === 'saved'
    ? ['Your reading list starts here', 'Save a story with its bookmark and it waits for you here.']
    : ['Nothing picked here right now', 'No filler. Review hidden stories in Preferences or browse a past edition.']
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-10 flex flex-col items-center text-center">
      <span className="grid h-14 w-14 place-items-center rounded-[18px] bg-[var(--surface-2)] text-[var(--muted)]">{nr.mode === 'saved' ? <Bookmark /> : <Inbox />}</span>
      <h3 className="display mt-3 text-[18px] font-[650]">{title}</h3>
      <p className="mt-1 max-w-[280px] text-[14px] text-[var(--muted)]">{body}</p>
    </motion.div>
  )
}

function Skeleton() {
  return (
    <div className="mt-5" aria-label="Loading">
      <div className="shimmer aspect-[1.9] rounded-[18px]" />
      <div className="mt-3 grid grid-cols-2 gap-3"><div className="shimmer aspect-[1.2] rounded-[18px]" /><div className="shimmer aspect-[1.2] rounded-[18px]" /></div>
      {[0, 1, 2].map((i) => <div key={i} className="mt-5 space-y-2"><div className="shimmer h-3 w-32 rounded" /><div className="shimmer h-5 w-full rounded" /><div className="shimmer h-4 w-4/5 rounded" /></div>)}
    </div>
  )
}

/* ——— Preferences ——— */

function Preferences({ nr }: { nr: Newsroom }) {
  const entries = Object.values(nr.vote).sort((a, b) => b.at.localeCompare(a.at))
  const lean: Record<string, number> = {}
  for (const v of entries) for (const t of v.tags ?? []) lean[t] = (lean[t] ?? 0) + v.value
  const toward = Object.entries(lean).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).slice(0, 6)
  const away = Object.entries(lean).filter(([, n]) => n < 0).sort((a, b) => a[1] - b[1]).slice(0, 6)
  const head = 'text-[12px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase'
  return (
    <div className="mt-3 min-[700px]:max-w-[720px]">
      <Interests nr={nr} head={head} />
      <Schedule nr={nr} head={head} />
      <SourcesList nr={nr} head={head} />

      <section className="mt-7">
        <h3 className={head}>Learned from your votes</h3>
        {toward.length + away.length === 0 ? (
          <p className="mt-1.5 text-[14.5px] text-[var(--muted)]">Tap 👍 or 👎 on stories and Newsroom ranks the next ones accordingly.</p>
        ) : (
          <div className="mt-2 space-y-2.5">
            {toward.length > 0 && <Chips label="More of" tags={toward.map(([t]) => t)} tone="blue" />}
            {away.length > 0 && <Chips label="Less of" tags={away.map(([t]) => t)} tone="red" />}
          </div>
        )}
      </section>

      <section className="mt-7">
        <h3 className={head}>Your votes{entries.length ? ` · ${entries.length}` : ''}</h3>
        {entries.length === 0 ? <p className="mt-1.5 text-[14.5px] text-[var(--muted)]">None yet.</p> : (
          <LayoutGroup>
            <AnimatePresence initial={false}>
              {entries.map((v) => (
                <motion.div layout key={v.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-3 overflow-hidden border-b border-[var(--hair)] py-2.5">
                  <span className={v.value === 1 ? 'text-[var(--blue)]' : 'text-[var(--red)]'}>
                    {v.value === 1 ? <ThumbsUp size={17} fill="currentColor" fillOpacity={0.28} /> : <ThumbsDown size={17} fill="currentColor" fillOpacity={0.28} />}
                  </span>
                  <span className="min-w-0 flex-1 line-clamp-2 text-[14.5px] leading-[1.35]">{v.title}</span>
                  <button className="h-11 shrink-0 px-1 text-[13px] font-[620] text-[var(--blue)]" onClick={() => nr.forget(v.id)}>Undo</button>
                </motion.div>
              ))}
            </AnimatePresence>
          </LayoutGroup>
        )}
      </section>

      <p className="mt-6 text-[12.5px] leading-[1.5] text-[var(--faint)]">
        Votes rank this device’s edition, fade over time, and are shared with your editor on Hermes.{' '}
        {entries.length > 0 && <button className="font-[620] text-[var(--blue)] underline-offset-2 active:underline" onClick={nr.exportVotes}>Export votes</button>}
      </p>
    </div>
  )
}

function Interests({ nr, head }: { nr: Newsroom; head: string }) {
  const s = nr.settings
  const [editing, setEditing] = useState(false)
  const [topics, setTopics] = useState<string[]>(s?.topics ?? [])
  const [words, setWords] = useState(s?.interests ?? '')
  const [state, setState] = useState<string>()
  const save = async () => {
    setState('saving')
    try { await action('settings', { op: 'save', topics, interests: words }); await nr.reload(); setEditing(false); setState(undefined) } catch (e) { setState(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <section>
      <div className="flex items-center justify-between">
        <h3 className={head}>Your interests</h3>
        {!editing && <button className="h-9 text-[13.5px] font-[620] text-[var(--blue)]" onClick={() => { setTopics(s?.topics ?? []); setWords(s?.interests ?? ''); setEditing(true) }}>Edit</button>}
      </div>
      {editing ? (
        <div className="mt-2">
          <TopicPicker topics={topics} setTopics={setTopics} />
          <textarea value={words} onChange={(e) => setWords(e.target.value)} rows={3} maxLength={1000} placeholder="In your own words (optional)"
            className="mt-3 w-full resize-none rounded-[14px] border border-[var(--line)] bg-[var(--surface)] p-3 text-[15px] outline-none focus:border-[var(--blue)]" />
          {state && state !== 'saving' && <p className="mt-1 text-[13px] text-[var(--red)]">{state}</p>}
          <div className="mt-2 flex gap-2">
            <button disabled={!topics.length || state === 'saving'} onClick={save} className="h-11 flex-1 rounded-full bg-[var(--blue)] text-[14.5px] font-[650] text-[var(--surface)] disabled:opacity-40">{state === 'saving' ? 'Saving…' : 'Save'}</button>
            <button onClick={() => setEditing(false)} className="h-11 flex-1 rounded-full bg-[var(--surface-2)] text-[14.5px] font-[620]">Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5">{(s?.topics ?? []).map((t) => <span key={t} className="rounded-full bg-[var(--surface-2)] px-2.5 py-1 text-[12.5px] font-[600]">{topicName(t)}</span>)}</div>
          {s?.interests && <p className="mt-2 text-[15px] leading-[1.5]">{s.interests}</p>}
        </>
      )}
    </section>
  )
}

function Schedule({ nr, head }: { nr: Newsroom; head: string }) {
  const [freq, setFreq] = useState<Frequency>(nr.settings?.frequency ?? '6h')
  const [state, setState] = useState<string>()
  const change = async (f: Frequency) => {
    const before = freq
    setFreq(f); setState('saving')
    try { await action('routine', { op: 'schedule', frequency: f }); await nr.reload(); setState(undefined) }
    catch (e) { setFreq(before); setState(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <section className="mt-7">
      <h3 className={head}>How often</h3>
      <div className="mt-2"><FrequencyPicker value={freq} onChange={change} /></div>
      <p className={`mt-1.5 px-1 text-[12.5px] ${state && state !== 'saving' ? 'text-[var(--red)]' : 'text-[var(--muted)]'}`}>
        {state === 'saving' ? 'Rescheduling…' : state ?? `Next editions: ${nextEditions(freq).join(', ')}.`}
      </p>
    </section>
  )
}

function SourcesList({ nr, head }: { nr: Newsroom; head: string }) {
  const [feeds, setFeeds] = useState<Feed[]>(nr.settings?.feeds ?? [])
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string>()
  useEffect(() => { action<{ feeds: Feed[] }>('sources', { op: 'list' }).then((r) => setFeeds(r.feeds)).catch(() => {}) }, [])
  const change = async (op: 'add' | 'remove', f: Feed) => {
    setError(undefined)
    try { const r = await action<{ feeds: Feed[] }>('sources', { op, url: f.url, title: f.title, topic: f.topic }); setFeeds(r.feeds); setAdding(false); nr.reload() }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  return (
    <section className="mt-7">
      <div className="flex items-center justify-between">
        <h3 className={head}>Sources · {feeds.length}</h3>
        <button className="h-9 text-[13.5px] font-[620] text-[var(--blue)]" onClick={() => setAdding(!adding)}>{adding ? 'Done' : 'Add'}</button>
      </div>
      <AnimatePresence initial={false}>
        {adding && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden pt-2 pb-1">
            <AddSource topics={nr.settings?.topics ?? []} onAdd={(f) => change('add', f)} />
          </motion.div>
        )}
      </AnimatePresence>
      {error && <p className="mt-1 text-[13px] text-[var(--red)]">{error}</p>}
      <LayoutGroup>
        <AnimatePresence initial={false}>
          {feeds.map((f) => (
            <motion.div layout key={f.url} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-3 overflow-hidden border-b border-[var(--hair)] py-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${f.ok === false ? 'bg-[var(--red)]' : f.ok ? 'bg-[var(--green)]' : 'bg-[var(--line)]'}`} title={f.ok === false ? 'Last collection failed' : undefined} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-[600]">{f.title}</span>
                <span className="block truncate text-[12px] text-[var(--faint)]">{topicName(f.topic)} · {host(f.url)}{f.ok === false ? ' · last collection failed' : f.count ? ` · ${f.count} stories` : ''}</span>
              </span>
              <button aria-label={`Remove ${f.title}`} onClick={() => change('remove', f)} className="grid h-11 w-11 shrink-0 place-items-center text-[var(--faint)] active:text-[var(--red)]"><X size={17} /></button>
            </motion.div>
          ))}
        </AnimatePresence>
      </LayoutGroup>
    </section>
  )
}

function Chips({ label, tags, tone }: { label: string; tags: string[]; tone: 'blue' | 'red' }) {
  return (
    <div className="flex items-baseline gap-2.5">
      <p className="w-12 shrink-0 text-[12.5px] font-[650] text-[var(--muted)]">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => <span key={t} className={`rounded-full px-2.5 py-1 text-[12.5px] font-[560] ${tone === 'blue' ? 'bg-[var(--tint)] text-[var(--blue)]' : 'bg-[var(--red-tint)] text-[var(--red)]'}`}>{t.replaceAll('-', ' ')}</span>)}
      </div>
    </div>
  )
}

/* ——— Toast and navigation ——— */

function Toast({ nr }: { nr: Newsroom }) {
  useEffect(() => {
    if (!nr.toast) return
    const t = setTimeout(nr.dismissToast, 5000)
    return () => clearTimeout(t)
  }, [nr.toast])
  return (
    <div className="pointer-events-none fixed inset-x-0 z-20 flex justify-center px-4" style={{ bottom: 'calc(env(safe-area-inset-bottom) + 84px)' }} role="status" aria-live="polite">
      <AnimatePresence>
        {nr.toast && (
          <motion.div key={nr.toast.message} initial={{ opacity: 0, y: 16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.98 }} transition={spring}
            className="pointer-events-auto flex w-full max-w-[440px] items-center gap-2 rounded-[16px] bg-[#202124] py-1 pr-1 pl-4 text-[13.5px] text-white shadow-[0_12px_40px_-8px_rgba(0,0,0,.45)] dark:bg-[#e3e5e9] dark:text-[#202124]">
            <span className="flex-1 py-2">{nr.toast.message}</span>
            {nr.toast.undo && <button className="h-11 px-2 font-[650] text-[#a8c7fa] dark:text-[#185abc]" onClick={nr.undo}>Undo</button>}
            <button className="grid h-11 w-11 place-items-center opacity-70" aria-label="Dismiss" onClick={nr.dismissToast}><X size={16} /></button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Nav({ nr }: { nr: Newsroom }) {
  const tabs = [['briefing', 'For you', Newspaper], ['saved', 'Saved', Bookmark], ['preferences', 'Preferences', SlidersHorizontal]] as const
  const savedCount = Object.keys(nr.saved).length
  return (
    <nav className="fixed inset-x-0 z-10 flex justify-center px-4" style={{ bottom: 'calc(env(safe-area-inset-bottom) + 10px)' }}>
      <div className="flex w-full max-w-[400px] rounded-full border border-[var(--line)] bg-[var(--surface)]/80 p-1 shadow-[0_10px_36px_-10px_rgba(32,33,36,.35)] backdrop-blur-xl backdrop-saturate-150">
        {tabs.map(([m, label, Icon]) => {
          const on = nr.mode === m
          return (
            <button key={m} aria-pressed={on} onClick={() => (m === 'briefing' && on ? nr.open(null) : nr.setMode(m))}
              className="relative flex h-12 flex-1 flex-col items-center justify-center rounded-full">
              {on && <motion.span layoutId="tab" transition={spring} className="absolute inset-0 rounded-full bg-[var(--tint)]" />}
              <span className={`relative flex flex-col items-center gap-[1px] ${on ? 'text-[var(--blue)]' : 'text-[var(--muted)]'}`}>
                <span className="relative">
                  <Icon size={19} strokeWidth={on ? 2.3 : 1.8} />
                  {m === 'saved' && savedCount > 0 && (
                    <motion.span key={savedCount} initial={{ scale: 0.4 }} animate={{ scale: 1 }} transition={{ type: 'spring', bounce: 0.6 }}
                      className="absolute -top-1.5 -right-2.5 grid h-4 min-w-4 place-items-center rounded-full bg-[var(--blue)] px-1 text-[9.5px] font-[750] text-[var(--surface)]">{savedCount}</motion.span>
                  )}
                </span>
                <span className="text-[10.5px] font-[650]">{label}</span>
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
