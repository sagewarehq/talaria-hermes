// Newsroom's first run: topics, sources, starting the routine, then the wait for the first edition. Everything it
// changes goes through the app's actions (actions/ in its folder), so it needs a Talaria that can run them.
import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowLeft, ArrowRight, Banknote, BookOpen, Bot, CalendarClock, Check, ChevronDown, Code2, Cpu, Link2, Loader2, Plus, Rocket, Rss,
  ShieldCheck, SlidersHorizontal, Sparkles, ThumbsDown, ThumbsUp,
} from 'lucide-react'
import { action, ActionsUnavailable } from 'talaria'
import { topicName } from '@shared/newsroom/format'
import type { Feed, Newsroom } from '@shared/newsroom/useNewsroom'

const spring = { type: 'spring', bounce: 0.18, duration: 0.5 } as const
const DRAFT = 'newsroom-setup-v1'

export const TOPICS: { name: string; icon: typeof Bot; blurb: string }[] = [
  { name: 'Artificial Intelligence', icon: Bot, blurb: 'Models, agents, labs and what they ship' },
  { name: 'Technology', icon: Cpu, blurb: 'Platforms, devices and the industry' },
  { name: 'Cybersecurity', icon: ShieldCheck, blurb: 'Breaches, exploits and fixes' },
  { name: 'Developer & Engineering', icon: Code2, blurb: 'Tools, practice and infrastructure' },
  { name: 'Fintech', icon: Banknote, blurb: 'Payments, banking and money tech' },
  { name: 'Startups', icon: Rocket, blurb: 'Founders, launches and markets' },
]

type Suggestion = Feed & { on?: boolean }
type Discovered = { url: string | null; title?: string; headlines?: string[]; message?: string; alternatives?: (Feed & { headlines?: string[] })[] }

const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, '') } catch { return u } }
const failure = (e: unknown) => e instanceof ActionsUnavailable ? 'Update Talaria on your phone to set up Newsroom.' : e instanceof Error ? e.message : String(e)

function readDraft() {
  try { return JSON.parse(localStorage.getItem(DRAFT) || '{}') } catch { return {} }
}

/* ——— the flow ——— */

export function Setup({ nr }: { nr: Newsroom }) {
  const draft = useMemo(readDraft, [])
  const [step, setStep] = useState<number>(draft.step ?? 0)
  const [topics, setTopics] = useState<string[]>(draft.topics ?? [])
  const [interests, setInterests] = useState<string>(draft.interests ?? '')
  const [feeds, setFeeds] = useState<Suggestion[]>(draft.feeds ?? [])
  useEffect(() => { try { localStorage.setItem(DRAFT, JSON.stringify({ step, topics, interests, feeds })) } catch { /* fine */ } }, [step, topics, interests, feeds])

  const go = (n: number) => { setStep(n); scrollTo({ top: 0 }) }
  const steps = [
    <Welcome key="w" next={() => go(1)} />,
    <Topics key="t" topics={topics} setTopics={setTopics} interests={interests} setInterests={setInterests} next={() => go(2)} back={() => go(0)} />,
    <Sources key="s" topics={topics} feeds={feeds} setFeeds={setFeeds} next={() => go(3)} back={() => go(1)} />,
    <Start key="g" nr={nr} topics={topics} interests={interests} feeds={feeds.filter((f) => f.on)} back={() => go(2)} />,
  ]
  return (
    <div className="mx-auto max-w-[560px] px-5" style={{ paddingTop: 'calc(env(safe-area-inset-top) + 56px)', paddingBottom: 'calc(env(safe-area-inset-bottom) + 120px)' }}>
      {step > 0 && <div className="mb-7" aria-label={`Step ${step} of 3`}>
        <div className="flex items-center justify-between text-[12px] font-[650]">
          <span className="text-[var(--text)]">Set up Newsroom</span>
          <span className="text-[var(--muted)] tabular-nums">Step {step} of 3</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-1 overflow-hidden rounded-full bg-[var(--hair)]">
              <motion.span className="block h-full rounded-full bg-[var(--text)]" initial={false} animate={{ width: i < step ? '100%' : '0%' }} transition={spring} />
            </span>
          ))}
        </div>
      </div>}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={step} initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} transition={{ duration: 0.22 }}>
          {steps[step]}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function Title({ icon: Icon, eyebrow, title, sub }: { icon: typeof Bot; eyebrow: string; title: string; sub: string }) {
  return (
    <header>
      <p className="flex items-center gap-1.5 text-[12px] font-[700] tracking-[0.08em] text-[var(--muted)] uppercase"><Icon size={14} strokeWidth={2.4} />{eyebrow}</p>
      <h1 className="display mt-2 text-[32px] leading-[1.06] font-[740] tracking-[-0.03em]">{title}</h1>
      <p className="mt-2.5 text-[16px] leading-[1.5] text-[var(--muted)]">{sub}</p>
    </header>
  )
}

/* ——— welcome ——— */

// A miniature of an edition, in greys, assembling itself: what Newsroom makes, before any questions.
const MINI = [
  'A widely used decoder flaw reaches web servers',
  'A new open model matches the leaders on code',
  'Twelve years of running SQLite at scale',
]

function Welcome({ next }: { next: () => void }) {
  const line = 'rounded-full bg-[var(--line)]'
  const reveal = (d: number) => ({ initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay: d } })
  return (
    <>
      <motion.div initial={{ opacity: 0, y: 24, rotate: -2 }} animate={{ opacity: 1, y: 0, rotate: -2 }} transition={{ type: 'spring', bounce: 0.25, duration: 0.9 }}
        className="mx-auto mt-3 w-[78%] max-w-[300px] rounded-[22px] border border-[var(--line)] bg-[var(--surface)] p-4 shadow-[0_24px_60px_-24px_rgba(0,0,0,.35)]" aria-hidden>
        <motion.div animate={{ y: [0, -4, 0] }} transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}>
          <motion.div {...reveal(0.3)} className="flex items-center gap-2">
            <span className="h-5 w-5 rounded-[6px] bg-[var(--text)] opacity-85" />
            <span className="display text-[14px] font-[700]">Newsroom</span>
          </motion.div>
          <motion.div {...reveal(0.45)} className="mt-3 h-[84px] rounded-[12px] bg-[var(--surface-2)]" />
          <motion.p {...reveal(0.6)} className="display mt-2.5 text-[14.5px] leading-[1.22] font-[700]">{MINI[0]}</motion.p>
          <motion.div {...reveal(0.7)} className={`mt-2 h-1.5 w-[86%] ${line}`} />
          <motion.div {...reveal(0.75)} className={`mt-1.5 h-1.5 w-[60%] ${line}`} />
          {MINI.slice(1).map((t, i) => (
            <motion.div key={t} {...reveal(0.95 + i * 0.2)} className="mt-3 flex gap-2.5 border-t border-[var(--hair)] pt-2.5">
              <span className="display text-[17px] leading-none font-[250] text-[var(--faint)] tabular-nums">0{i + 2}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[12px] leading-[1.25] font-[650]">{t}</span>
                <span className={`mt-1.5 block h-1 w-[70%] ${line}`} />
              </span>
            </motion.div>
          ))}
          <motion.p {...reveal(1.5)} className="mt-3 flex items-center gap-1 text-[10.5px] font-[650] text-[var(--blue)]">Why this story? <ChevronDown size={11} /></motion.p>
        </motion.div>
      </motion.div>
      <motion.div {...reveal(0.4)} className="mt-9 text-center">
        <h1 className="text-[38px] leading-[1.02] font-[600] tracking-[-0.02em]" style={{ fontFamily: 'ui-serif, "New York", Georgia, serif' }}>Your own newsroom</h1>
        <p className="mx-auto mt-3 max-w-[320px] text-[16px] leading-[1.5] text-[var(--muted)]">
          Hermes reads your sources and edits an edition just for you, as often as you like, with a reason for every story.
        </p>
      </motion.div>
      <Footer><Primary onClick={next}>Get started</Primary></Footer>
    </>
  )
}

function Primary({ children, onClick, disabled, busy }: { children: React.ReactNode; onClick: () => void; disabled?: boolean; busy?: boolean }) {
  return (
    <motion.button whileTap={{ scale: 0.97 }} onClick={onClick} disabled={disabled || busy}
      className="flex h-[52px] w-full items-center justify-center gap-2 rounded-full bg-[var(--blue)] text-[16px] font-[650] text-[var(--surface)] shadow-[var(--shadow-lift)] transition-opacity disabled:opacity-40 disabled:shadow-none">
      {busy && <Loader2 size={18} className="animate-spin" />}{children}
    </motion.button>
  )
}

/** The step's buttons, pinned to the bottom over a fade, so Continue is always in reach. */
function Footer({ back, children }: { back?: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-[var(--bg)] from-60% to-transparent px-5 pt-8" style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 14px)' }}>
      <div className="mx-auto flex max-w-[520px] items-center gap-2.5">
        {back && (
          <motion.button whileTap={{ scale: 0.92 }} onClick={back} aria-label="Back"
            className="grid h-[52px] w-[52px] shrink-0 place-items-center rounded-full border border-[var(--line)] bg-[var(--surface)] text-[var(--text)] shadow-[var(--shadow)]"><ArrowLeft size={19} /></motion.button>
        )}
        <div className="flex-1">{children}</div>
      </div>
    </div>
  )
}

/* ——— how often ——— */

export const FREQUENCIES = [
  { id: '6h', label: 'Every 6 hours', runs: '4 editions a day', step: 6 },
  { id: '12h', label: 'Every 12 hours', runs: 'Morning and evening', step: 12 },
  { id: 'daily', label: 'Daily', runs: 'Every morning', step: 24 },
] as const
export type Frequency = (typeof FREQUENCIES)[number]['id']

/** The next few edition times for a frequency, anchored at 7 AM (the routine action schedules it the same way). */
export function nextEditions(freq: Frequency, count = 3): string[] {
  const step = FREQUENCIES.find((f) => f.id === freq)!.step, now = new Date(), out: string[] = []
  const t = new Date(now); t.setHours(7, 0, 0, 0)
  while (t > now) t.setHours(t.getHours() - step)
  while (out.length < count) { t.setHours(t.getHours() + step); if (t > now) out.push(t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', ...(step === 24 ? {} : {}) })) }
  return out
}

/** A choice of how often editions come. */
export function FrequencyPicker({ value, onChange }: { value: Frequency; onChange: (f: Frequency) => void }) {
  return (
    <div className="overflow-hidden rounded-[18px] border border-[var(--line)] bg-[var(--surface)]">
      {FREQUENCIES.map((f, i) => {
        const on = f.id === value
        return (
          <button key={f.id} onClick={() => onChange(f.id)} aria-pressed={on}
            className={`flex min-h-[56px] w-full items-center gap-3 px-4 py-2.5 text-left active:bg-[var(--surface-2)] ${i ? 'border-t border-[var(--hair)]' : ''}`}>
            <span className="min-w-0 flex-1">
              <span className="block text-[15.5px] font-[620]">{f.label}</span>
              <span className="block text-[12.5px] text-[var(--muted)]">{f.runs}</span>
            </span>
            <span className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 transition-colors ${on ? 'border-[var(--text)] bg-[var(--text)] text-[var(--surface)]' : 'border-[var(--line)]'}`}>
              {on && <Check size={12} strokeWidth={3.2} />}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ——— step 1: topics ——— */

export function TopicPicker({ topics, setTopics }: { topics: string[]; setTopics: (t: string[]) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {TOPICS.map(({ name, icon: Icon, blurb }, i) => {
        const on = topics.includes(name)
        return (
          <motion.button key={name} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: i * 0.04 }} whileTap={{ scale: 0.97 }}
            aria-pressed={on} onClick={() => setTopics(on ? topics.filter((t) => t !== name) : [...topics, name])}
            className={`relative rounded-[20px] border p-3.5 text-left transition-colors duration-200 ${on ? 'border-[var(--text)] bg-[var(--surface)] shadow-[0_0_0_1px_var(--text)]' : 'border-[var(--line)] bg-[var(--surface)]'}`}>
            <span className={`grid h-10 w-10 place-items-center rounded-[12px] transition-colors ${on ? 'bg-[var(--text)] text-[var(--surface)]' : 'bg-[var(--surface-2)] text-[var(--muted)]'}`}>
              <Icon size={20} />
            </span>
            <span className="mt-2.5 block text-[15.5px] font-[680] tracking-[-0.01em]">{topicName(name)}</span>
            <span className="mt-0.5 block text-[12.5px] leading-[1.35] text-[var(--muted)]">{blurb}</span>
            <AnimatePresence>
              {on && (
                <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} transition={{ type: 'spring', bounce: 0.6 }}
                  className="absolute top-3 right-3 grid h-[22px] w-[22px] place-items-center rounded-full bg-[var(--text)] text-[var(--surface)]"><Check size={13} strokeWidth={3} /></motion.span>
              )}
            </AnimatePresence>
          </motion.button>
        )
      })}
    </div>
  )
}

function Topics({ topics, setTopics, interests, setInterests, next, back }: {
  topics: string[]; setTopics: (t: string[]) => void; interests: string; setInterests: (s: string) => void; next: () => void; back: () => void
}) {
  return (
    <>
      <Title icon={Sparkles} eyebrow="Topics" title="What do you follow?" sub="Pick as many as you like. You can change them any time." />
      <div className="mt-6"><TopicPicker topics={topics} setTopics={setTopics} /></div>
      <label className="mt-6 block">
        <span className="text-[13px] font-[650] text-[var(--muted)]">In your own words <span className="font-normal">(optional)</span></span>
        <textarea value={interests} onChange={(e) => setInterests(e.target.value)} rows={3} maxLength={1000}
          placeholder="e.g. AI agents and developer tools I can use at work; security issues that affect web apps; less gadget news."
          className="mt-1.5 w-full resize-none rounded-[14px] border border-[var(--line)] bg-[var(--surface)] p-3 text-[15px] leading-[1.45] outline-none placeholder:text-[var(--faint)] focus:border-[var(--blue)] focus:shadow-[0_0_0_3px_var(--tint)]" />
        <span className="mt-1 block text-[12px] text-[var(--faint)]">Your editor reads this before every edition.</span>
      </label>
      <Footer back={back}><Primary onClick={next} disabled={!topics.length}>{topics.length ? <>Continue with {topics.length} {topics.length === 1 ? 'topic' : 'topics'} <ArrowRight size={17} /></> : 'Pick at least one topic'}</Primary></Footer>
    </>
  )
}

/* ——— step 2: sources ——— */

export function AddSource({ topics, onAdd }: { topics: string[]; onAdd: (f: Feed) => void }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [found, setFound] = useState<Discovered>()
  const [error, setError] = useState<string>()
  const topic = topics[0] ?? 'Technology'
  const find = async () => {
    if (!url.trim()) return
    setBusy(true); setError(undefined); setFound(undefined)
    try { setFound(await action<Discovered>('sources', { op: 'discover', url })) } catch (e) { setError(failure(e)) } finally { setBusy(false) }
  }
  const add = (f: Feed) => { onAdd({ ...f, topic: f.topic || topic }); setUrl(''); setFound(undefined) }
  const options = found ? (found.url ? [{ url: found.url, title: found.title ?? host(found.url), topic, headlines: found.headlines }] : found.alternatives ?? []) : []
  return (
    <div>
      <div className="flex gap-2">
        <label className="flex h-12 min-w-0 flex-1 items-center gap-2 rounded-[14px] border border-[var(--line)] bg-[var(--surface)] pl-3.5 shadow-[var(--shadow)] focus-within:border-[var(--blue)] focus-within:shadow-[0_0_0_3px_var(--tint)]">
        <Link2 size={17} className="shrink-0 text-[var(--faint)]" />
        <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && find()} inputMode="url" autoCapitalize="none" autoCorrect="off"
          placeholder="Add a site or feed, e.g. github.blog" className="h-full min-w-0 flex-1 bg-transparent pr-3 text-[15px] outline-none placeholder:text-[var(--faint)]" />
        </label>
        <button onClick={find} disabled={busy || !url.trim()} aria-label="Find feed"
          className="grid h-12 w-12 shrink-0 place-items-center rounded-[14px] bg-[var(--blue)] text-[var(--surface)] disabled:opacity-40">{busy ? <Loader2 size={18} className="animate-spin" /> : <Plus size={20} />}</button>
      </div>
      <AnimatePresence>
        {error && <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2 text-[13.5px] text-[var(--red)]">{error}</motion.p>}
        {found && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="mt-2.5 space-y-2">
            {found.message && <p className="text-[13.5px] text-[var(--muted)]">{found.message}{options.length ? ' Use one of these RSS feeds instead:' : ''}</p>}
            {options.map((f) => (
              <div key={f.url} className="rounded-[16px] border border-[var(--line)] bg-[var(--surface)] p-3.5">
                <div className="flex items-center gap-2">
                  <Rss size={15} className="shrink-0 text-[#e8710a]" />
                  <span className="min-w-0 flex-1 truncate text-[15px] font-[650]">{f.title}</span>
                  <button onClick={() => add(f)} className="h-9 shrink-0 rounded-full bg-[var(--tint)] px-3.5 text-[13.5px] font-[650] text-[var(--blue)]">Add</button>
                </div>
                <ul className="mt-1.5 space-y-0.5 pl-6 text-[12.5px] leading-[1.4] text-[var(--muted)]">{(f.headlines ?? []).map((h, i) => <li key={i} className="line-clamp-1">· {h}</li>)}</ul>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Sources({ topics, feeds, setFeeds, next, back }: { topics: string[]; feeds: Suggestion[]; setFeeds: (f: Suggestion[]) => void; next: () => void; back: () => void }) {
  const [error, setError] = useState<string>()
  useEffect(() => {
    // The built-in feeds for the chosen topics, switched on; any added by hand stay.
    action<{ suggestions: Feed[] }>('sources', { op: 'suggest', topics })
      .then(({ suggestions }) => {
        const custom = feeds.filter((f) => !suggestions.some((s) => s.url === f.url) && f.on)
        setFeeds([...custom, ...suggestions.map((s) => ({ ...s, on: feeds.find((f) => f.url === s.url)?.on ?? true }))])
      })
      .catch((e) => setError(failure(e)))
  }, [topics.join()])
  const on = feeds.filter((f) => f.on).length
  const groups = [...new Set(feeds.map((f) => f.topic))]
  const setGroup = (g: string, value: boolean) => setFeeds(feeds.map((x) => (x.topic === g ? { ...x, on: value } : x)))
  return (
    <>
      <Title icon={Rss} eyebrow="Sources" title="Where the news comes from" sub="Feeds picked for your topics, ready to go. Switch any off, or add a site you read." />
      <div className="mt-5"><AddSource topics={topics} onAdd={(f) => setFeeds([{ ...f, on: true }, ...feeds.filter((x) => x.url !== f.url)])} /></div>
      {error && <p className="mt-3 text-[13.5px] text-[var(--red)]">{error}</p>}
      {!feeds.length && !error && <div className="mt-6 space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="shimmer h-14 rounded-[14px]" />)}</div>}
      {groups.map((g, gi) => {
        const rows = feeds.filter((f) => f.topic === g), allOn = rows.every((f) => f.on)
        return (
          <motion.section key={g} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: gi * 0.05 }} className="mt-6">
            <div className="flex items-center justify-between px-1">
              <h3 className="flex items-center gap-1.5 text-[12px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase">
{topicName(g)}
                <span className="font-[600] tracking-normal normal-case text-[var(--faint)]">· {rows.filter((f) => f.on).length} of {rows.length}</span>
              </h3>
              <button onClick={() => setGroup(g, !allOn)} className="h-8 text-[12.5px] font-[650] text-[var(--blue)]">{allOn ? 'None' : 'All'}</button>
            </div>
            <div className="mt-1.5 overflow-hidden rounded-[18px] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow)]">
              {rows.map((f, i) => (
                <button key={f.url} onClick={() => setFeeds(feeds.map((x) => (x.url === f.url ? { ...x, on: !x.on } : x)))} aria-pressed={f.on}
                  className={`flex min-h-[56px] w-full items-center gap-3 px-3.5 py-2 text-left active:bg-[var(--surface-2)] ${i ? 'border-t border-[var(--hair)]' : ''}`}>
                  <Mark url={f.url} />
                  <span className={`min-w-0 flex-1 transition-opacity ${f.on ? '' : 'opacity-45'}`}>
                    <span className="block truncate text-[15px] font-[620]">{f.title}</span>
                    <span className="block truncate text-[12px] text-[var(--faint)]">{host(f.url)}</span>
                  </span>
                  <Toggle on={Boolean(f.on)} />
                </button>
              ))}
            </div>
          </motion.section>
        )
      })}
      <Footer back={back}><Primary onClick={next} disabled={!on}>{on ? <>Continue with {on} {on === 1 ? 'source' : 'sources'} <ArrowRight size={17} /></> : 'Turn on at least one source'}</Primary></Footer>
    </>
  )
}

/** A source's mark: its first letter, quietly. */
function Mark({ url }: { url: string }) {
  const name = host(url).replace(/^(blog|news|feeds?|www)\./, '')
  return <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px] bg-[var(--surface-2)] text-[15px] font-[700] text-[var(--muted)] uppercase">{name.slice(0, 1)}</span>
}

function Toggle({ on }: { on: boolean }) {
  return (
    <span className={`relative h-[30px] w-[50px] shrink-0 rounded-full transition-colors ${on ? 'bg-[var(--text)]' : 'bg-[var(--line)]'}`}>
      <motion.span layout transition={{ type: 'spring', bounce: 0.3, duration: 0.3 }} className={`absolute top-[2px] h-[26px] w-[26px] rounded-full bg-white shadow ${on ? 'right-[2px]' : 'left-[2px]'}`} />
    </span>
  )
}

/* ——— step 3: start ——— */

function Start({ nr, topics, interests, feeds, back }: { nr: Newsroom; topics: string[]; interests: string; feeds: Feed[]; back: () => void }) {
  const [stage, setStage] = useState(-1)
  const [error, setError] = useState<string>()
  const tasks = ['Saving your topics', `Adding ${feeds.length} sources`, 'Scheduling your editor']
  const start = async () => {
    setError(undefined)
    try {
      setStage(0)
      await action('settings', { op: 'save', topics, interests, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
      setStage(1)
      for (const f of feeds) await action('sources', { op: 'add', url: f.url, title: f.title, topic: f.topic })
      setStage(2)
      await action('routine', { op: 'install', frequency })
      setStage(3)
      try { localStorage.removeItem(DRAFT) } catch { /* fine */ }
      setTimeout(() => nr.reload(), 700)
    } catch (e) { setError(failure(e)); setStage(-1) }
  }
  const [frequency, setFrequency] = useState<Frequency>('6h')
  const upcoming = nextEditions(frequency)
  const points = [
    [Rss, 'Collects', `The latest from your ${feeds.length} sources, on the schedule you pick.`],
    [Sparkles, 'Edits', 'Up to 30 stories for your topics, each with why it matters to you and how it was checked.'],
    [BookOpen, 'Delivers', 'A fresh edition here, ready to read. Each one is an AI run on your Hermes.'],
  ] as const
  return (
    <>
      <Title icon={Rocket} eyebrow="Ready" title="Meet your editor" sub="Hermes puts each edition together for you, around the clock." />
      <ol className="relative mt-6">
        <span className="absolute top-5 bottom-5 left-[19px] w-px bg-[var(--line)]" />
        {points.map(([Icon, t, d], i) => (
          <motion.li key={t} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: 0.1 + i * 0.1 }} className="relative flex gap-4 pb-5 last:pb-0">
            <span className="relative z-10 grid h-10 w-10 shrink-0 place-items-center rounded-full border border-[var(--line)] bg-[var(--surface)] text-[var(--text)] shadow-[0_0_0_5px_var(--bg)]"><Icon size={18} /></span>
            <span className="pt-1.5"><span className="block text-[16px] font-[680]">{t}</span><span className="mt-0.5 block text-[14.5px] leading-[1.45] text-[var(--muted)]">{d}</span></span>
          </motion.li>
        ))}
      </ol>
      <section className="mt-7">
        <h3 className="text-[12px] font-[700] tracking-[0.07em] text-[var(--muted)] uppercase">How often</h3>
        <div className="mt-2"><FrequencyPicker value={frequency} onChange={setFrequency} /></div>
        <p className="mt-2 px-1 text-[12.5px] text-[var(--muted)]">First edition now, then {upcoming.join(', ')}.</p>
      </section>
      <AnimatePresence>
        {stage >= 0 && (
          <motion.ul initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-5 space-y-2 overflow-hidden">
            {tasks.map((t, i) => (
              <li key={t} className={`flex items-center gap-2.5 text-[14.5px] ${i <= stage ? '' : 'text-[var(--faint)]'}`}>
                {i < stage ? <Check size={17} className="text-[var(--green)]" /> : i === stage ? <Loader2 size={17} className="animate-spin text-[var(--blue)]" /> : <span className="h-[17px] w-[17px]" />}{t}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
      {error && <p className="mt-4 rounded-[14px] bg-[var(--red-tint)] p-3 text-[14px] text-[var(--red)]">{error}</p>}
      <Footer back={stage < 0 ? back : undefined}>
        <Primary onClick={start} busy={stage >= 0 && stage < 3}>{stage === 3 ? <>Started <Check size={18} /></> : stage >= 0 ? 'Setting up…' : <>Start Newsroom <Rocket size={17} /></>}</Primary>
      </Footer>
    </>
  )
}

/* ——— the wait for the first edition ——— */

const TIPS = [
  [ThumbsUp, 'More like this', 'Tap 👍 and related stories rank higher right away. Your editor sees your votes too.'],
  [ThumbsDown, 'Less like this', 'Tap 👎 to hide a story and see less of its kind.'],
  [BookOpen, 'Read in Newsroom', 'Stories open in a clean reader, with the next one a tap away.'],
  [CalendarClock, 'Past editions', 'Every edition is kept; the date bar takes you back through earlier ones.'],
  [SlidersHorizontal, 'Change it any time', 'Topics, sources and how often live in Preferences.'],
] as const

export function Collecting({ nr }: { nr: Newsroom }) {
  const [collected, setCollected] = useState(false)
  const [tip, setTip] = useState(0)
  useEffect(() => {
    const check = () => {
      fetch('/status.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((s) => setCollected(Boolean(s?.ok))).catch(() => {})
      nr.reload()
    }
    check()
    const t = setInterval(check, 20000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => { const t = setInterval(() => setTip((i) => (i + 1) % TIPS.length), 5000); return () => clearInterval(t) }, [])
  const sources = nr.settings?.feeds.length ?? 0
  const steps = [`Collecting from ${sources} ${sources === 1 ? 'source' : 'sources'}`, 'Choosing your stories', 'Getting articles ready to read']
  const at = collected ? 1 : 0
  const [Icon, title, body] = TIPS[tip]
  return (
    <div className="mx-auto flex min-h-dvh max-w-[520px] flex-col px-5" style={{ paddingTop: 'calc(env(safe-area-inset-top) + 64px)', paddingBottom: 'calc(env(safe-area-inset-bottom) + 28px)' }}>
      <div className="relative mx-auto mt-4 grid h-36 w-36 place-items-center" aria-hidden>
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="absolute inset-0 rounded-full border border-[var(--faint)]"
            initial={{ scale: 0.5, opacity: 0.3 }} animate={{ scale: 1.25, opacity: 0 }} transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.8, ease: 'easeOut' }} />
        ))}
        <motion.span animate={{ y: [0, -4, 0] }} transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
          className="grid h-20 w-20 place-items-center rounded-[24px] border border-[var(--line)] bg-[var(--surface)] text-[var(--text)] shadow-[var(--shadow)]"><Rss size={32} /></motion.span>
      </div>
      <h1 className="display mt-8 text-center text-[27px] leading-[1.12] font-[720] tracking-[-0.02em]">Your first edition is on its way</h1>
      <p className="mt-2 text-center text-[15px] leading-[1.5] text-[var(--muted)]">It usually takes 5 to 15 minutes. You can leave; it’ll be here when it’s ready.</p>
      <ul className="mx-auto mt-6 space-y-2.5">
        {steps.map((s, i) => (
          <li key={s} className={`flex items-center gap-2.5 text-[15px] ${i <= at ? 'text-[var(--text)]' : 'text-[var(--faint)]'}`}>
            {i < at ? <Check size={18} className="text-[var(--green)]" /> : i === at ? <Loader2 size={18} className="animate-spin text-[var(--blue)]" /> : <span className="grid h-[18px] w-[18px] place-items-center"><span className="h-1.5 w-1.5 rounded-full bg-[var(--line)]" /></span>}
            {s}
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-10">
        <p className="text-center text-[11.5px] font-[700] tracking-[0.08em] text-[var(--muted)] uppercase">While you wait</p>
        <div className="relative mt-2.5 h-[108px]">
          <AnimatePresence mode="wait">
            <motion.div key={tip} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.3 }}
              className="absolute inset-0 flex gap-3 rounded-[18px] border border-[var(--line)] bg-[var(--surface)] p-4 shadow-[var(--shadow)]">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[12px] bg-[var(--surface-2)] text-[var(--muted)]"><Icon size={19} /></span>
              <span><span className="block text-[15px] font-[650]">{title}</span><span className="mt-0.5 block text-[14px] leading-[1.45] text-[var(--muted)]">{body}</span></span>
            </motion.div>
          </AnimatePresence>
        </div>
        <div className="mt-3 flex justify-center gap-1.5">
          {TIPS.map((_, i) => <button key={i} aria-label={`Tip ${i + 1}`} onClick={() => setTip(i)} className="grid h-6 w-5 place-items-center"><span className={`h-1.5 rounded-full bg-[var(--text)] transition-all ${i === tip ? 'w-4 opacity-80' : 'w-1.5 opacity-25'}`} /></button>)}
        </div>
      </div>
    </div>
  )
}

