import { NavLink, Outlet } from 'react-router-dom';
import { runtimeConfig } from '../runtimeConfig';

const links = [
  { to: '/about', label: 'About' },
  { to: '/privacy', label: 'Privacy' },
  { to: '/terms', label: 'Terms' },
];

export default function PublicLayout() {
  return (
    <div className="public-shell">
      <a className="usa-skipnav" href="#main-content">Skip to main content</a>
      <header className="public-header">
        <div className="grid-container public-header__inner">
          <NavLink to="/" className="app-brand" aria-label={`${runtimeConfig.appTitle} public home`}>
            <span className="app-brand__mark" aria-hidden="true">GV</span>
            <span>{runtimeConfig.appTitle}</span>
          </NavLink>
          <nav className="public-nav" aria-label="Public navigation">
            {links.map((link) => <NavLink key={link.to} to={link.to}>{link.label}</NavLink>)}
            <NavLink className="usa-button" to="/login">Sign in</NavLink>
          </nav>
        </div>
      </header>
      <main id="main-content" className="grid-container public-main">
        <Outlet />
      </main>
      <footer className="app-footer public-footer">
        <div className="grid-container public-footer__inner">
          <span>GovVue Light is an independent research tool and is not affiliated with SAM.gov or the U.S. government.</span>
          <nav aria-label="Footer navigation">
            {links.map((link) => <NavLink key={link.to} to={link.to}>{link.label}</NavLink>)}
          </nav>
        </div>
      </footer>
    </div>
  );
}
