export function age(date: string): string {
  const h = Math.max(0, (Date.now() - new Date(date).getTime()) / 3600000)
  return h < 1 ? 'Just now' : h < 24 ? `${Math.floor(h)}h ago` : `${Math.floor(h / 24)}d ago`
}

// Editions are dated in the reader's timezone (newsroom.json), whatever the phone's is.
let zone = 'UTC'
export function setZone(tz?: string) {
  try { if (tz) { new Intl.DateTimeFormat('en-US', { timeZone: tz }); zone = tz } } catch { /* unknown: keep UTC */ }
}
/** "Tokyo" for Asia/Tokyo, "UTC" for UTC. */
export const zoneName = () => zone.split('/').pop()!.replaceAll('_', ' ')

const inZone = (opts: Intl.DateTimeFormatOptions) => (s: string) => new Date(s).toLocaleString('en-US', { timeZone: zone, ...opts })
export const editionTime = inZone({ hour: 'numeric', minute: '2-digit' })
export const editionDay = inZone({ month: 'short', day: 'numeric' })
export const editionLong = inZone({ weekday: 'long', month: 'long', day: 'numeric' })

export function topicName(t: string): string {
  return t === 'Artificial Intelligence' ? 'AI' : t === 'Developer & Engineering' ? 'Engineering' : t
}

export function host(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return '' }
}
