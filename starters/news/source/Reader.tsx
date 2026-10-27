// The in-app reader: a full-screen sheet with the article's extracted text, its place in the edition, and the story
// actions. It's a history entry, so Talaria's Back (and the edge swipe) closes it; Next replaces it in place.
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useScroll, useSpring } from 'motion/react'
import { ArrowRight, ArrowUpRight, Bookmark, ChevronDown, Compass, MessageSquare, Newspaper, Share, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react'
import { age, host } from '@shared/newsroom/format'
import { Glyph } from '@shared/newsroom/Icons'
import { prefetch, useArticle, type Block } from '@shared/newsroom/useArticle'
import type { Article, Newsroom } from '@shared/newsroom/useNewsroom'

const Ctx = createContext<{ open: (id: string) => void; read: Set<string> }>({ open: () => {}, read: new Set() })
export const useReader = () => useContext(Ctx)

export function ReaderProvider({ nr, children, Source, Topic }: {
  nr: Newsroom; children: React.ReactNode
  Source: (p: { a: Article; compact?: boolean }) => React.ReactNode; Topic: (p: { a: Article; keyStory?: boolean; className?: string }) => React.ReactNode
}) {
  const [id, setId] = useState<string | null>(() => history.state?.read ?? null)
  // Read marks are shared by every device (useNewsroom, actions/read.py).
  const { read, markRead } = nr
  useEffect(() => {
    const pop = () => setId(history.state?.read ?? null)
    addEventListener('popstate', pop)
    return () => removeEventListener('popstate', pop)
  }, [])
  const open = (x: string) => { history.pushState({ ...history.state, read: x }, ''); setId(x); markRead(x) }
  const go = (x: string) => { history.replaceState({ ...history.state, read: x }, ''); setId(x); markRead(x) }
  const close = () => (history.state?.read ? history.back() : setId(null))
  const list = nr.ordered
  const a = list.find((x) => x.id === id) ?? nr.saved[id ?? ''] ?? nr.ordered.find((x) => x.id === id)
  return (
    <Ctx.Provider value={{ open, read }}>
      <div inert={Boolean(a)}>{children}</div>
      <AnimatePresence>
        {a && <Sheet key="reader" a={a} list={list} nr={nr} go={go} close={close} Source={Source} Topic={Topic} />}
      </AnimatePresence>
    </Ctx.Provider>
  )
}

function Sheet({ a, list, nr, go, close, Source, Topic }: {
  a: Article; list: Article[]; nr: Newsroom; go: (id: string) => void; close: () => void
  Source: (p: { a: Article; compact?: boolean }) => React.ReactNode; Topic: (p: { a: Article; keyStory?: boolean; className?: string }) => React.ReactNode
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ container: scroller })
  const progress = useSpring(scrollYProgress, { stiffness: 300, damping: 40 })
  const at = list.findIndex((x) => x.id === a.id)
  const next = at >= 0 ? list[at + 1] : undefined
  const [note, setNote] = useState<string>()
  useEffect(() => { scroller.current?.scrollTo({ top: 0 }); prefetch(list.slice(at + 1, at + 3).map((x) => x.id)) }, [a.id])
  useEffect(() => { document.documentElement.style.overflow = 'hidden'; return () => { document.documentElement.style.overflow = '' } }, [])
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(undefined), 2200); return () => clearTimeout(t) }, [note])
  // A keyboard closes the reader with Esc and moves on with the right arrow.
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || (e.target instanceof Element && e.target.closest('input, textarea'))) return
      if (document.getElementById('why-title')) return // the "what's off?" sheet is open over the reader
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowRight' && next) go(next.id)
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [next?.id])
  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ title: a.title, url: a.url })
      else { await navigator.clipboard.writeText(a.url); setNote('Link copied') }
    } catch { /* cancelled */ }
  }
  const v = nr.vote[a.id]?.value, saved = Boolean(nr.saved[a.id])
  const tool = 'grid h-11 w-11 place-items-center rounded-full text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)] active:scale-90'
  return (
    <motion.div role="dialog" aria-modal aria-label={a.title} initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }}
      transition={{ type: 'spring', bounce: 0.08, duration: 0.5 }} className="fixed inset-0 z-30 bg-[var(--bg)]">
      <motion.div className="fixed inset-x-0 z-40 h-[3px] origin-left bg-[var(--blue)]" style={{ top: 'env(safe-area-inset-top)', scaleX: progress }} />
      <div ref={scroller} className="h-full overflow-x-hidden overflow-y-auto overscroll-contain [overflow-wrap:anywhere]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.article key={a.id} initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={{ duration: 0.25 }}
            className="mx-auto max-w-[680px] px-5" style={{ paddingTop: 'calc(env(safe-area-inset-top) + 58px)', paddingBottom: 'calc(env(safe-area-inset-bottom) + 110px)' }}>
            <Body a={a} nr={nr} Source={Source} Topic={Topic} />
            {next && (
              <button onClick={() => go(next.id)} className="mt-8 flex w-full items-center gap-3 rounded-[18px] border border-[var(--line)] bg-[var(--surface)] p-4 text-left shadow-[var(--shadow)] active:scale-[0.99]">
                <span className="min-w-0 flex-1">
                  <span className="text-[11.5px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase">Up next · {at + 2} of {list.length}</span>
                  <Topic a={next} className="mt-1.5" />
                  <span className="display mt-0.5 line-clamp-2 block text-[17px] leading-[1.25] font-[650]">{next.title}</span>
                </span>
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[var(--blue)] text-[var(--surface)]"><ArrowRight size={18} /></span>
              </button>
            )}
            {!next && <p className="mt-8 text-center text-[13.5px] text-[var(--muted)]">That’s the last story in this list.</p>}
          </motion.article>
        </AnimatePresence>
      </div>
      <nav className="fixed inset-x-0 z-40 flex justify-center px-3" style={{ bottom: 'calc(env(safe-area-inset-bottom) + 10px)' }} aria-label="Article actions">
        <div className="flex items-center gap-0.5 rounded-full border border-[var(--line)] bg-[var(--surface)]/85 p-1 shadow-[0_10px_36px_-10px_rgba(32,33,36,.4)] backdrop-blur-xl backdrop-saturate-150">
          <button className={tool} aria-label="Close" onClick={close}><ChevronDown size={21} /></button>
          <span className="mx-0.5 h-6 w-px bg-[var(--line)]" />
          <button className={`${tool} ${v === 1 ? '!text-[var(--blue)]' : ''}`} aria-pressed={v === 1} aria-label="More like this" onClick={() => nr.rate(a, 1)}><Glyph Icon={ThumbsUp} on={v === 1} size={18} /></button>
          <button className={`${tool} ${v === -1 ? '!text-[var(--red)]' : ''}`} aria-pressed={v === -1} aria-label="Less like this" onClick={() => nr.rate(a, -1)}><Glyph Icon={ThumbsDown} on={v === -1} size={18} /></button>
          <button className={`${tool} ${saved ? '!text-[var(--blue)]' : ''}`} aria-pressed={saved} aria-label={saved ? 'Remove from Read later' : 'Read later'} onClick={() => nr.toggleSave(a)}><Glyph Icon={Bookmark} on={saved} size={18} /></button>
          <button className={tool} aria-label="Share" onClick={share}><Share size={18} /></button>
          <a className={tool} aria-label={`Open on ${host(a.url)}`} href={a.url} target="_blank" rel="noopener noreferrer"><Compass size={19} /></a>
          {next && (
            <motion.button whileTap={{ scale: 0.94 }} onClick={() => go(next.id)} className="ml-0.5 flex h-11 items-center gap-1 rounded-full bg-[var(--blue)] pr-3 pl-4 text-[14px] font-[650] text-[var(--surface)]">
              Next <ArrowRight size={16} />
            </motion.button>
          )}
        </div>
      </nav>
      <AnimatePresence>
        {(note || nr.toast) && (
          <motion.p key={note ?? nr.toast?.message} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="fixed inset-x-0 z-40 mx-auto w-fit max-w-[90%] rounded-full bg-[#202124] px-4 py-2 text-center text-[13px] text-white shadow-lg dark:bg-[#e3e5e9] dark:text-[#202124]"
            style={{ bottom: 'calc(env(safe-area-inset-bottom) + 74px)' }}>{note ?? nr.toast?.message}</motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

function Body({ a, nr, Source, Topic }: { a: Article; nr: Newsroom; Source: (p: { a: Article; compact?: boolean }) => React.ReactNode; Topic: (p: { a: Article; keyStory?: boolean; className?: string }) => React.ReactNode }) {
  const { article, loading } = useArticle(a.id)
  const minutes = article?.ok && article.words ? Math.max(1, Math.round(article.words / 230)) : undefined
  const reviewed = a.evidence?.status === 'source-reviewed'
  const image = nr.imageOf(a)
  return (
    <>
      <Topic a={a} keyStory={a.key} />
      <h1 className="display mt-2 text-[28px] leading-[1.12] font-[720] tracking-[-0.022em] lg:text-[36px] lg:leading-[1.08]">{a.title}</h1>
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1">
        <Source a={a} compact />
        {article?.byline && <span className="text-[12px] text-[var(--muted)]">· {article.byline}</span>}
        {minutes && <span className="text-[12px] text-[var(--muted)]">· {minutes} min read</span>}
      </div>
      {image && <img src={image} alt="" className="mt-4 aspect-[1.9] w-full rounded-[16px] object-cover" />}
      <aside className="mt-4 rounded-[16px] bg-[var(--tint)] p-3.5 text-[14px] leading-[1.5]">
        <p className="text-[11px] font-[700] tracking-[0.07em] text-[var(--blue)] uppercase">Why it’s in your edition</p>
        <p className="mt-1 text-[var(--text)]">{a.why || (nr.vote[a.id]?.value === 1 ? 'You liked this story.' : 'You saved it to read later.')}</p>
        <p className={`mt-1.5 flex items-center gap-1.5 text-[12.5px] font-[620] ${reviewed ? 'text-[var(--green)]' : 'text-[var(--muted)]'}`}>
          {reviewed ? <ShieldCheck size={14} /> : <Newspaper size={14} />}{reviewed ? 'Canonical source reviewed' : 'Feed metadata only'}
        </p>
      </aside>
      <div className="reader mt-6">
        {loading ? (
          <div className="space-y-3">{[100, 96, 99, 70, 0, 98, 94, 60].map((w, i) => w ? <div key={i} className="shimmer h-4 rounded" style={{ width: `${w}%` }} /> : <div key={i} className="h-2" />)}</div>
        ) : article?.ok && article.blocks ? (
          <Blocks blocks={article.blocks} hero={Boolean(image)} />
        ) : (
          <div className="rounded-[18px] border border-[var(--line)] bg-[var(--surface)] p-4 text-center font-sans">
            {a.summary && <p className="text-left text-[16px] leading-[1.6] text-[var(--text)]">{a.summary}</p>}
            <p className="mt-3 text-[13px] text-[var(--muted)]">{host(a.url)} couldn’t be brought into the reader.</p>
            <a href={a.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex h-11 items-center gap-1.5 rounded-full bg-[var(--blue)] px-5 text-[14.5px] font-[650] text-[var(--surface)]">
              Read on {host(a.url)} <ArrowUpRight size={16} />
            </a>
          </div>
        )}
      </div>
      {article?.ok && (
        <div className="mt-6 flex flex-wrap gap-x-5 border-t border-[var(--hair)] pt-3 text-[13.5px] font-[620] text-[var(--blue)]">
          <a className="inline-flex h-11 items-center gap-1" href={a.url} target="_blank" rel="noopener noreferrer">Original on {host(a.url)}<ArrowUpRight size={14} /></a>
          {a.discussionUrl && <a className="inline-flex h-11 items-center gap-1" href={a.discussionUrl} target="_blank" rel="noopener noreferrer"><MessageSquare size={14} />HN discussion</a>}
        </div>
      )}
      <p className="mt-1 text-[12px] text-[var(--faint)]">Published {age(a.publishedAt)} by {a.publisher}. Text extracted for reading; the original is the source of record.</p>
    </>
  )
}

// Only addresses extract.py rebuilt from a player's id get a frame.
const PLAYER = /^https:\/\/(www\.youtube-nocookie\.com\/embed\/|player\.vimeo\.com\/video\/|flo\.uri\.sh\/|datawrapper\.dwcdn\.net\/)/

function Blocks({ blocks, hero }: { blocks: Block[]; hero: boolean }) {
  // Publisher metadata sometimes arrives as a standalone body block (not article prose).
  blocks = blocks.filter((b) => !('text' in b && b.t !== 'code' && /^published\s*:?$/i.test(b.text.trim())))
  // The page's own lead photo is the hero already shown above the story.
  const lead = blocks.findIndex((b) => b.t === 'p')
  return (
    <>
      {blocks.map((b, i) =>
        b.t === 'img' ? (hero && i < lead ? null : <Photo key={i} src={b.src} alt={b.alt ?? ''} />)
        : b.t === 'embed' ? (PLAYER.test(b.src) ? <Embed key={i} {...b} /> : null)
        : b.t === 'h' ? <h2 key={i} className="display mt-7 mb-2 text-[20px] leading-[1.25] font-[680] tracking-[-0.01em]"><Text {...b} /></h2>
        : b.t === 'li' ? <p key={i} className="relative mb-2 pl-5 before:absolute before:left-1 before:top-[0.7em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-[var(--blue)]"><Text {...b} /></p>
        : b.t === 'code' ? <pre key={i} className="my-5 overflow-x-auto rounded-[12px] border border-[var(--line)] bg-[var(--surface-2)] px-4 py-3 font-mono text-[13.5px] leading-[1.55] whitespace-pre [tab-size:4] [overflow-wrap:normal]"><code>{b.text}</code></pre>
        : b.t === 'q' ? <blockquote key={i} className="my-5 border-l-[3px] border-[var(--blue)] pl-4 italic text-[var(--muted)]"><Text {...b} /></blockquote>
        : <p key={i} className="mb-4"><Text {...b} /></p>)}
    </>
  )
}

/** A block's text, its inline code (every other part) set in the code face. */
function Text({ text, parts }: { text: string; parts?: string[] }) {
  if (!parts) return <>{text}</>
  return <>{parts.map((s, i) => i % 2 ? <code key={i} className="rounded-[5px] bg-[var(--surface-2)] px-[0.3em] py-[0.08em] font-mono text-[0.84em] not-italic [overflow-wrap:anywhere]">{s}</code> : s)}</>
}

/** A photo or chart from the story, shown from the publisher's site; gone if it doesn't load. */
function Photo({ src, alt }: { src: string; alt: string }) {
  const [broken, setBroken] = useState(false)
  if (broken) return null
  return (
    <img src={src} alt={alt} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setBroken(true)}
      className="my-6 max-h-[80vh] w-full rounded-[14px] bg-[var(--surface-2)] object-contain" />
  )
}

/** A video or interactive chart where the story has it, played in place from its own player. */
function Embed({ kind, src, ratio }: { kind: 'video' | 'chart'; src: string; ratio?: number }) {
  return (
    <iframe src={src} title={kind === 'video' ? 'Video' : 'Chart'} loading="lazy" allowFullScreen
      allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
      sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
      className={`my-6 block w-full rounded-[14px] border-0 ${kind === 'chart' ? 'bg-white' : 'bg-black'}`}
      style={{ aspectRatio: String(kind === 'video' ? 16 / 9 : Math.min(Math.max(ratio ?? 4 / 3, 0.6), 2.4)) }} />
  )
}
