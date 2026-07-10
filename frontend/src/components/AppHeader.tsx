import { Link, NavLink } from "react-router-dom";

const LANGUAGES = ["EN", "हिंदी", "ಕನ್ನಡ"];

export default function AppHeader() {
  return (
    <header className="app-header">
      <Link to="/" className="app-header__brand">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2a10 10 0 1 0 10 10h-10V2z" />
          <path d="M12 12 2 12" />
          <path d="M12 12 20 4" />
        </svg>
        AQI Sentinel
      </Link>

      <nav className="app-header__nav">
        <NavLink to="/" end className={({ isActive }) => `app-header__nav-link${isActive ? " app-header__nav-link--active" : ""}`}>
          Map
        </NavLink>
        <NavLink to="/enforcement" className={({ isActive }) => `app-header__nav-link${isActive ? " app-header__nav-link--active" : ""}`}>
          Enforcement
        </NavLink>
        <NavLink to="/copilot" className={({ isActive }) => `app-header__nav-link${isActive ? " app-header__nav-link--active" : ""}`}>
          Copilot
        </NavLink>
        <NavLink to="/neighbourhoods" className={({ isActive }) => `app-header__nav-link${isActive ? " app-header__nav-link--active" : ""}`}>
          Neighbourhoods
        </NavLink>

        <div className="app-header__lang">
          {LANGUAGES.map((lang) => (
            <button key={lang} className="app-header__lang-btn" type="button">
              {lang}
            </button>
          ))}
        </div>
      </nav>
    </header>
  );
}
