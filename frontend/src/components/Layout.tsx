import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { runtimeConfig } from '../runtimeConfig';

export default function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const navPanelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 801px)');
    const closeAtDesktop = (event: MediaQueryListEvent) => {
      if (event.matches) setMobileNavOpen(false);
    };
    desktop.addEventListener('change', closeAtDesktop);
    return () => desktop.removeEventListener('change', closeAtDesktop);
  }, []);

  useEffect(() => {
    if (!mobileNavOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMobileNavOpen(false);
        requestAnimationFrame(() => menuButtonRef.current?.focus());
        return;
      }
      if (event.key !== 'Tab' || !navPanelRef.current) return;

      const focusable = [...navPanelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
      )].filter((element) => element.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [mobileNavOpen]);

  function closeMobileNav(restoreFocus = false) {
    setMobileNavOpen(false);
    if (restoreFocus) requestAnimationFrame(() => menuButtonRef.current?.focus());
  }

  async function handleSignOut() {
    await signOut();
    navigate('/login');
  }

  return (
    <div className="app-shell">
      <a className="usa-skipnav" href="#main-content">Skip to main content</a>
      <header className="app-header">
        <div className="grid-container app-header__inner">
          <NavLink to="/search" className="app-brand" aria-label={`${runtimeConfig.appTitle} home`}>
            <span className="app-brand__mark" aria-hidden="true">GV</span>
            <span>{runtimeConfig.appTitle}</span>
          </NavLink>
          <button
            ref={menuButtonRef}
            type="button"
            className="usa-button app-menu-button"
            aria-controls="primary-navigation"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen(true)}
          >
            Menu
          </button>
          <nav
            ref={navPanelRef}
            id="primary-navigation"
            aria-label="Primary navigation"
            className={`app-nav-panel${mobileNavOpen ? ' app-nav-panel--open' : ''}`}
          >
            <div className="app-nav-panel__header">
              <span>Menu</span>
              <button
                ref={closeButtonRef}
                type="button"
                className="app-nav-panel__close"
                aria-label="Close navigation"
                onClick={() => closeMobileNav(true)}
              >
                ×
              </button>
            </div>
            <div className="app-mobile-account">
              <NavLink className="app-account__email" to="/account" onClick={() => closeMobileNav()}>{user?.email}</NavLink>
              <span>Account</span>
            </div>
            <ul className="app-nav">
              <NavMenu
                label="Search"
                active={matches(location.pathname, ['/search', '/opportunities', '/entities'])}
                mobileOpen={mobileNavOpen}
                onNavigate={() => closeMobileNav()}
                items={[
                  { to: '/search', label: 'Opportunities' },
                  { to: '/entities', label: 'Entities' },
                ]}
              />
              <NavMenu
                label="Saved searches"
                active={matches(location.pathname, ['/searches', '/entity-searches'])}
                mobileOpen={mobileNavOpen}
                onNavigate={() => closeMobileNav()}
                items={[
                  { to: '/searches', label: 'Opportunities' },
                  { to: '/entity-searches', label: 'Entities' },
                ]}
              />
              <NavMenu
                label="Daily notifications"
                active={matches(location.pathname, ['/notifications'])}
                mobileOpen={mobileNavOpen}
                onNavigate={() => closeMobileNav()}
                items={[{ to: '/notifications', label: 'Opportunities' }]}
                directOnMobile
              />
              <NavMenu
                label="Saved items"
                active={matches(location.pathname, ['/saved-entities', '/saved'])}
                mobileOpen={mobileNavOpen}
                onNavigate={() => closeMobileNav()}
                items={[
                  { to: '/saved-entities', label: 'Entities' },
                  { to: '/saved', label: 'Opportunities' },
                ]}
              />
              {user?.role === 'admin' && <li><NavLink to="/admin/users" onClick={() => closeMobileNav()}>Admin</NavLink></li>}
            </ul>
            <div className="app-mobile-signout">
              <button type="button" className="usa-button usa-button--unstyled" onClick={handleSignOut}>Sign out</button>
            </div>
          </nav>
          <div className="app-account">
            <NavLink className="app-account__email" to="/account">{user?.email}</NavLink>
            <button type="button" className="usa-button usa-button--unstyled" onClick={handleSignOut}>Sign out</button>
          </div>
        </div>
      </header>
      <button
        type="button"
        className={`app-nav-overlay${mobileNavOpen ? ' app-nav-overlay--visible' : ''}`}
        aria-label="Close navigation"
        tabIndex={mobileNavOpen ? 0 : -1}
        onClick={() => closeMobileNav(true)}
      />
      <main id="main-content" className="grid-container app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        <div className="grid-container">
          Personal opportunity and entity research tool. Data is provided by SAM.gov.
        </div>
      </footer>
    </div>
  );
}

function matches(pathname: string, prefixes: string[]) {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function NavMenu({ label, items, active, mobileOpen, onNavigate, directOnMobile = false }: {
  label: string;
  items: { to: string; label: string }[];
  active: boolean;
  mobileOpen: boolean;
  onNavigate: () => void;
  directOnMobile?: boolean;
}) {
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!ref.current?.contains(event.target as Node)) ref.current?.removeAttribute('open');
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        ref.current?.removeAttribute('open');
        ref.current?.querySelector('summary')?.focus();
      }
    }
    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  useEffect(() => {
    if (mobileOpen && active && !directOnMobile) ref.current?.setAttribute('open', '');
  }, [active, directOnMobile, mobileOpen]);

  return (
    <li className={`app-nav__menu${directOnMobile ? ' app-nav__menu--mobile-direct' : ''}`}>
      <details ref={ref}>
        <summary className={active ? 'active' : ''}>{label}</summary>
        <ul className="app-nav__submenu">
          {items.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} onClick={() => {
                ref.current?.removeAttribute('open');
                onNavigate();
              }}>{item.label}</NavLink>
            </li>
          ))}
        </ul>
      </details>
      {directOnMobile && (
        <NavLink
          className={({ isActive }) => `app-nav__mobile-direct${isActive ? ' active' : ''}`}
          to={items[0].to}
          onClick={onNavigate}
        >
          {label}
        </NavLink>
      )}
    </li>
  );
}
