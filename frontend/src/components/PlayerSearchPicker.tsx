import { useEffect, useRef, useState } from 'react';

import { PlayerHeadshot } from '@/components/PlayerHeadshot';
import { usePlayerSearch } from '@/hooks/usePlayerSearch';
import {
  FEATURED_COMPARISONS,
  type FeaturedComparison,
} from '@/lib/featuredComparisons';

interface SelectedPlayer {
  person_id: number;
  full_name?: string | null;
  primary_position_abbr?: string | null;
}

interface PlayerSearchPickerProps {
  selectedIds: readonly number[];
  /** Selected-player display data (name, position) keyed by person_id. May
   *  be sparse — the picker falls back to "Player #<id>" if the parent
   *  doesn't have the full row yet. */
  selectedDisplay: ReadonlyMap<number, SelectedPlayer>;
  minIds: number;
  maxIds: number;
  onAdd: (personId: number) => void;
  onRemove: (personId: number) => void;
  onPreset: (preset: FeaturedComparison) => void;
  /** Slug of the active preset, if any (used to highlight the chip). */
  activePresetId?: string;
}

export function PlayerSearchPicker({
  selectedIds,
  selectedDisplay,
  minIds,
  maxIds,
  onAdd,
  onRemove,
  onPreset,
  activePresetId = '',
}: PlayerSearchPickerProps) {
  const atCapacity = selectedIds.length >= maxIds;
  const canRemove = selectedIds.length > minIds;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" aria-label="Selected players">
        {selectedIds.map((id) => {
          const meta = selectedDisplay.get(id);
          return (
            <SelectedChip
              key={id}
              personId={id}
              fullName={meta?.full_name ?? `Player #${id}`}
              position={meta?.primary_position_abbr ?? null}
              onRemove={canRemove ? () => onRemove(id) : undefined}
            />
          );
        })}
      </div>

      <SearchInput
        disabled={atCapacity}
        excludeIds={new Set(selectedIds)}
        capacityHint={atCapacity ? `Max ${maxIds} players reached.` : null}
        onPick={onAdd}
      />

      <div>
        <div className="kicker mb-2 text-paper-ink-soft">Quick picks</div>
        <div
          className="-mx-1 flex flex-wrap gap-2 px-1"
          role="tablist"
          aria-label="Featured player comparisons"
        >
          {FEATURED_COMPARISONS.map((m) => {
            const active = m.id === activePresetId;
            return (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onPreset(m)}
                className={[
                  'whitespace-nowrap rounded-s px-3 py-1.5 text-[12px] font-semibold transition-colors',
                  active
                    ? 'bg-accent-leather text-paper-cream'
                    : 'bg-surface-sunken text-paper-ink-muted hover:bg-surface-sunken/80',
                ].join(' ')}
              >
                {m.title}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface SelectedChipProps {
  personId: number;
  fullName: string;
  position: string | null;
  onRemove?: () => void;
}

function SelectedChip({ personId, fullName, position, onRemove }: SelectedChipProps) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-hairline-strong bg-surface-elevated py-1 pl-1.5 pr-2.5 shadow-sm">
      <PlayerHeadshot playerId={personId} playerName={fullName} size="sm" />
      <span className="text-[12.5px] font-semibold text-paper-ink">{fullName}</span>
      {position && <span className="mono text-[10.5px] text-paper-ink-soft">{position}</span>}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${fullName}`}
          className="rounded-full border border-hairline px-1.5 text-[12px] leading-none text-paper-ink-soft hover:border-bad/50 hover:text-bad"
        >
          ×
        </button>
      )}
    </span>
  );
}

interface SearchInputProps {
  disabled: boolean;
  excludeIds: ReadonlySet<number>;
  capacityHint: string | null;
  onPick: (personId: number) => void;
}

function SearchInput({ disabled, excludeIds, capacityHint, onPick }: SearchInputProps) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 200);
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
  const results = (search.data?.data.results ?? []).filter(
    (r) => !excludeIds.has(r.person_id),
  );
  const showDropdown = open && debounced.length >= 2 && !disabled;

  function pick(personId: number) {
    setQuery('');
    setDebounced('');
    setOpen(false);
    onPick(personId);
  }

  return (
    <div ref={containerRef} className="relative max-w-md">
      <label
        className={[
          'flex items-center gap-2 rounded-m border border-hairline-strong bg-surface-elevated px-3 py-2',
          disabled ? 'opacity-50' : '',
        ].join(' ')}
      >
        <svg
          width="14"
          height="14"
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
          disabled={disabled}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={disabled ? capacityHint ?? 'Max players reached' : 'Add a player by name…'}
          aria-label="Add a player by name"
          className="flex-1 border-0 bg-transparent text-[13px] text-paper-ink outline-none placeholder:text-paper-ink-soft disabled:cursor-not-allowed"
        />
      </label>

      {showDropdown && (
        <div
          role="listbox"
          aria-label="Search results"
          className="absolute left-0 top-[calc(100%+4px)] z-30 w-full overflow-hidden rounded-m border border-hairline-strong bg-surface-elevated shadow-lg"
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
                    onClick={() => pick(r.person_id)}
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
