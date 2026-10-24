import type { ReactNode } from 'react'

/** A page laid out under Talaria's floating top bar: content starts right below its buttons, and the bottom
 *  clears the home indicator. The background still runs edge to edge. */
export function Screen({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <main
      className={`mx-auto max-w-xl px-4 ${className}`}
      style={{
        paddingTop: 'calc(env(safe-area-inset-top) + 48px)',
        paddingBottom: 'calc(env(safe-area-inset-bottom) + 16px)',
      }}
    >
      {children}
    </main>
  )
}
