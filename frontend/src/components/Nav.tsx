import { NavLink } from 'react-router-dom'
import { useAuth } from '../state/auth'
import { useTheme } from '../lib/theme'

export default function Nav() {
  const { me, authenticated, signOut } = useAuth()
  const { theme, toggle } = useTheme()

  return (
    <nav className="nav">
      <img className="nav-logo" src="/logo.png" alt="Tenderising" />
      <NavLink to="/" end className="nav-link">
        Ask Tenderising
      </NavLink>
      <NavLink to="/discovery" className="nav-link">
        Discovery
      </NavLink>
      <NavLink to="/workspace" className="nav-link">
        Workspace
      </NavLink>

      <span style={{ flex: 1 }} />

      <button
        className="theme-toggle"
        onClick={toggle}
        title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>

      <div className="nav-right">
        {authenticated && me?.user ? (
          <>
            <NavLink to="/workspace?tab=chats" className="nav-link">
              History
            </NavLink>
            {me.user.picture ? (
              <img className="nav-avatar" src={me.user.picture} alt="" />
            ) : null}
            <span className="nav-name">{me.user.name || me.user.email}</span>
            <button
              className="btn ghost"
              onClick={async () => {
                await signOut()
              }}
            >
              Sign out
            </button>
          </>
        ) : (
          <>
            <span className="nav-hint">Unlock chat history & workspace</span>
            <a className="btn primary" href="/api/auth/login">
              Sign in with Google
            </a>
          </>
        )}
      </div>
    </nav>
  )
}
