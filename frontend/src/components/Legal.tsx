import type { ReactNode } from 'react'

export default function Legal({
  title,
  updated,
  children,
}: {
  title: string
  updated: string
  children: ReactNode
}) {
  return (
    <div className="page">
      <div className="legal">
        <h1>{title}</h1>
        <p className="legal-updated">Last updated: {updated}</p>
        {children}
      </div>
    </div>
  )
}
