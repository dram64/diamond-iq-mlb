import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { PlayerHeadshot } from './PlayerHeadshot';
import { DIQLogo } from './primitives/DIQLogo';
import { usePlayerSearch } from '@/hooks/usePlayerSearch';

const navLinks = [
  { to: '/', label: 'Today', end: true },
  { to: '/compare-players', label: 'Compare', end: false },
  { to: '/teams', label: 'Teams', end: false },
  { to: '/stats', label: 'Stat Explorer', end: false },
] as const;

export function RootLayout() {
  return (
    <div className="min-h-screen bg-surface-base text-paper-ink">
      {/* Navbar — cream-tinted backdrop, ink text, leather
          on hover, leather underline on active. Slight backdrop-blur
          + a thin hairline-strong divider separates it from the cream
          page surface. */}
      <header className="sticky top-0 z-20 border-b border-hairline-strong bg-surface-elevated/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-page items-center gap-10 px-7 py-3.5">
          <NavLink to="/" aria-label="Diamond IQ home">
            <DIQLogo size={22} />
          </NavLink>
          <nav className="flex flex-1 gap-6 text-[13px] font-medium">
            {navLinks.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  [
                    'border-b-2 pb-0.5 transition-colors duration-200 ease-out',
                    isActive
                      ? 'border-accent-leather text-accent-leather'
                      : 'border-transparent text-paper-ink-muted hover:text-paper-ink',
                  ].join(' ')
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <SearchBox />
        </div>
      </header>

      <main className="mx-auto max-w-page px-6 pb-[72px] pt-7">
        <Outlet />
      </main>

      <SiteFooter />
    </div>
  );
}

/**
 * SearchBox — typeahead over /api/players/search.
 *
 * 250 ms debounce on input; results dropdown shows up to 10 player hits.
 * Selecting a result navigates to /compare-players?ids=<id>,<other> if a
 * second slot is staged, otherwise drops the id into the URL ?ids= for the
 * compare page to use as slot A. Click-outside closes the dropdown.
 */
function SearchBox() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const search = usePlayerSearch(debounced);
  const results = search.data?.data.results ?? [];
  const showDropdown = open && debounced.length >= 2;

  function selectResult(personId: number) {
    setQuery('');
    setDebounced('');
    setOpen(false);
    navigate(`/compare-players?ids=${personId}`);
  }

  return (
    <div ref={containerRef} className="relative">
      <label className="flex w-[260px] items-center gap-2 rounded-m border border-hairline bg-surface-sunken px-2.5 py-1.5 transition-colors duration-200 focus-within:border-accent-leather">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
          className="text-paper-ink-soft"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search players"
          aria-label="Search players"
          className="flex-1 border-0 bg-transparent text-[12px] text-paper-ink outline-none placeholder:text-paper-ink-soft"
        />
      </label>

      {showDropdown && (
        <div
          role="listbox"
          aria-label="Search results"
          className="absolute right-0 top-[calc(100%+4px)] z-30 w-[320px] overflow-hidden rounded-m border border-hairline-strong bg-surface-elevated shadow-lg"
        >
          {search.isLoading && (
            <div className="px-4 py-3 text-[12px] text-paper-ink-soft">Searching…</div>
          )}
          {search.isError && (
            <div className="px-4 py-3 text-[12px] text-bad">Search failed.</div>
          )}
          {search.isSuccess && results.length === 0 && (
            <div className="px-4 py-3 text-[12px] text-paper-ink-soft">No matches.</div>
          )}
          {search.isSuccess && results.length > 0 && (
            <ul className="max-h-[360px] overflow-y-auto py-1">
              {results.map((r) => (
                <li key={r.person_id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected="false"
                    onClick={() => selectResult(r.person_id)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface-elevated-hover"
                  >
                    <PlayerHeadshot
                      playerId={r.person_id}
                      playerName={r.full_name}
                      size="sm"
                    />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[13px] font-semibold text-paper-ink">
                        {r.full_name ?? '—'}
                      </span>
                      <span className="mono text-[10.5px] text-paper-ink-soft">
                        {r.primary_position_abbr ?? '—'}
                        {r.primary_number ? ` · #${r.primary_number}` : ''}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="mt-10 border-t border-hairline-strong bg-surface-sunken px-7 pb-12 pt-9">
      <div className="mx-auto flex max-w-page flex-wrap items-start justify-between gap-10">
        <div className="flex max-w-[360px] flex-col gap-2">
          <DIQLogo size={18} />
          <p className="m-0 text-[13px] leading-relaxed text-paper-ink-muted">
            Baseball analytics, live game data, and plain-English insights — for people who
            actually watch the game.
          </p>
        </div>
        <div className="flex gap-14 text-[11px] text-paper-ink-soft">
          <FooterCol
            title="Product"
            items={['Today', 'Stat Explorer', 'Compare players', 'Compare teams', 'Teams']}
          />
          <FooterCol
            title="Data"
            items={['Methodology', 'Glossary', 'Historical', 'API access']}
          />
          <FooterCol title="About" items={['Team', 'Careers', 'Contact', 'Press']} />
        </div>
      </div>
      <div className="mx-auto mt-8 flex max-w-page justify-between border-t border-hairline pt-5 font-mono text-[10.5px] text-paper-ink-soft">
        <span>© 2026 Diamond IQ · Stadium-warm v6.5</span>
        <span>Live MLB data + Statcast</span>
      </div>
    </footer>
  );
}

function FooterCol({ title, items }: { title: string; items: readonly string[] }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="kicker text-[9.5px] text-paper-ink-soft">{title}</span>
      {items.map((i) => (
        <a key={i} href="#" className="text-[12px] text-paper-ink-soft hover:text-paper-ink">
          {i}
        </a>
      ))}
    </div>
  );
}
