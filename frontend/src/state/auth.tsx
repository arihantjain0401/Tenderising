import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getMe, logout } from '../api/client'
import type { MeResponse } from '../lib/types'

interface AuthCtx {
  me: MeResponse | null
  authenticated: boolean
  refresh: () => Promise<void>
  signOut: () => Promise<void>
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null)

  const refresh = useCallback(async () => {
    try {
      setMe(await getMe())
    } catch {
      setMe({ authenticated: false })
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const signOut = useCallback(async () => {
    await logout()
    setMe({ authenticated: false })
  }, [])

  return (
    <Ctx.Provider value={{ me, authenticated: me?.authenticated ?? false, refresh, signOut }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
