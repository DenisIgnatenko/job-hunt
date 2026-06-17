import { NavLink } from 'react-router-dom'
import { clearCredentials } from '../api/client'

export default function Navbar() {
  const handleLogout = () => {
    clearCredentials()
    window.location.reload()
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">🎯 Job Hunt</div>
      <div className="navbar-links">
        <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
          Dashboard
        </NavLink>
        <NavLink to="/vacancies" className={({ isActive }) => isActive ? 'active' : ''}>
          Vacancies
        </NavLink>
        <NavLink to="/events" className={({ isActive }) => isActive ? 'active' : ''}>
          Events
        </NavLink>
        <NavLink to="/entertainment" className={({ isActive }) => isActive ? 'active' : ''}>
          🎠 Entertainment
        </NavLink>
      </div>
      <button className="logout-btn" onClick={handleLogout}>Logout</button>
    </nav>
  )
}
