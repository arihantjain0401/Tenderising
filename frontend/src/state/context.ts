import type { DiscoveryContext } from '../lib/types'

const KEY = 'tenderising.discoveryContext'

export function getDiscoveryContext(): DiscoveryContext | null {
  const raw = sessionStorage.getItem(KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as DiscoveryContext
  } catch {
    return null
  }
}

export function setDiscoveryContext(context: DiscoveryContext | null): void {
  if (context === null) {
    sessionStorage.removeItem(KEY)
  } else {
    sessionStorage.setItem(KEY, JSON.stringify(context))
  }
}
