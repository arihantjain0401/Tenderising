import { Routes, Route, Link } from 'react-router-dom'
import Nav from './components/Nav'
import Ask from './pages/Ask'
import Discovery from './pages/Discovery'
import Workspace from './pages/Workspace'
import BidDetail from './pages/BidDetail'
import PrivacyPolicy from './pages/PrivacyPolicy'
import TermsOfService from './pages/TermsOfService'

export default function App() {
  return (
    <div className="app-shell">
      <Nav />
      <Routes>
        <Route path="/" element={<Ask />} />
        <Route path="/discovery" element={<Discovery />} />
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/bid" element={<BidDetail />} />
        <Route path="/privacy" element={<PrivacyPolicy />} />
        <Route path="/terms" element={<TermsOfService />} />
      </Routes>
      <footer className="footer">
        <Link to="/privacy">Privacy Policy</Link>
        <Link to="/terms">Terms of Service</Link>
      </footer>
    </div>
  )
}
