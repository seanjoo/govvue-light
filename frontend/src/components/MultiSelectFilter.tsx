import { useEffect, useMemo, useRef, useState } from 'react';
import InfoTip from './InfoTip';

export interface FilterOption {
  value: string;
  label: string;
}

export const NOTICE_TYPE_OPTIONS: FilterOption[] = [
  { value: 'u', label: 'Justification (u)' },
  { value: 'p', label: 'Presolicitation (p)' },
  { value: 'a', label: 'Award notice (a)' },
  { value: 'r', label: 'Sources sought (r)' },
  { value: 's', label: 'Special notice (s)' },
  { value: 'o', label: 'Solicitation (o)' },
  { value: 'g', label: 'Sale of surplus property (g)' },
  { value: 'k', label: 'Combined synopsis/solicitation (k)' },
  { value: 'i', label: 'Intent to bundle requirements (i)' },
];

export const SET_ASIDE_OPTIONS: FilterOption[] = [
  { value: 'SBA', label: 'Total small business set-aside (SBA)' },
  { value: 'SBP', label: 'Partial small business set-aside (SBP)' },
  { value: '8A', label: '8(a) set-aside (8A)' },
  { value: '8AN', label: '8(a) sole source (8AN)' },
  { value: 'HZC', label: 'HUBZone set-aside (HZC)' },
  { value: 'HZS', label: 'HUBZone sole source (HZS)' },
  { value: 'SDVOSBC', label: 'SDVOSB set-aside (SDVOSBC)' },
  { value: 'SDVOSBS', label: 'SDVOSB sole source (SDVOSBS)' },
  { value: 'WOSB', label: 'WOSB set-aside (WOSB)' },
  { value: 'WOSBSS', label: 'WOSB sole source (WOSBSS)' },
  { value: 'EDWOSB', label: 'EDWOSB set-aside (EDWOSB)' },
  { value: 'EDWOSBSS', label: 'EDWOSB sole source (EDWOSBSS)' },
  { value: 'LAS', label: 'Local area set-aside (LAS)' },
  { value: 'IEE', label: 'Indian Economic Enterprise (IEE)' },
  { value: 'ISBEE', label: 'Indian Small Business Economic Enterprise (ISBEE)' },
  { value: 'BICiv', label: 'Buy Indian set-aside (BICiv)' },
  { value: 'VSA', label: 'Veteran-owned small business set-aside (VSA)' },
  { value: 'VSS', label: 'Veteran-owned small business sole source (VSS)' },
];

const STATE_NAMES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
  CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia',
  FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
  IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana',
  ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
  MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
  NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
  NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon',
  PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota',
  TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia',
  WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
  AS: 'American Samoa', GU: 'Guam', MP: 'Northern Mariana Islands', PR: 'Puerto Rico',
  VI: 'U.S. Virgin Islands', AA: 'Armed Forces Americas', AE: 'Armed Forces Europe',
  AP: 'Armed Forces Pacific',
};

export const STATE_OPTIONS: FilterOption[] = Object.entries(STATE_NAMES).map(
  ([value, name]) => ({ value, label: `${name} (${value})` }),
);

export default function MultiSelectFilter({
  id,
  label,
  value,
  options,
  update,
}: {
  id: string;
  label: string;
  value: string;
  options: FilterOption[];
  update: (value: string) => void;
}) {
  const selected = value.split(',').map((item) => item.trim()).filter(Boolean);
  const selectedSet = new Set(selected);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const pickerRef = useRef<HTMLDivElement>(null);
  const filteredOptions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return normalized
      ? options.filter((option) => `${option.value} ${option.label}`.toLocaleLowerCase().includes(normalized))
      : options;
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (!pickerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  function toggle(optionValue: string) {
    const next = new Set(selectedSet);
    if (next.has(optionValue)) next.delete(optionValue); else next.add(optionValue);
    update(options.filter((option) => next.has(option.value)).map((option) => option.value).join(','));
  }

  const selectionText = selected.length === 0
    ? 'Any'
    : selected.length === 1
      ? options.find((option) => option.value === selected[0])?.label || selected[0]
      : `${selected.length} selected`;

  return (
    <div className="tablet:grid-col-4 multi-select-filter checkbox-picker" ref={pickerRef}>
      <div className="multi-select-filter__heading">
        <div className="field-label">
          <span className="usa-label" id={`${id}-label`}>{label}</span>
          <InfoTip text="Choose one or more values. Multiple selections within this filter are matched with OR." label={`About ${label}`} />
        </div>
        {selected.length > 0 && (
          <button className="usa-button usa-button--unstyled" type="button" onClick={() => update('')}>Clear</button>
        )}
      </div>
      <button
        className="usa-select maxw-none checkbox-picker__toggle"
        id={id}
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-options`}
        aria-labelledby={`${id}-label ${id}`}
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selectionText}</span><span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="checkbox-picker__panel" id={`${id}-options`} role="group" aria-labelledby={`${id}-label`}>
          {options.length > 12 && (
            <div className="checkbox-picker__search">
              <label className="usa-sr-only" htmlFor={`${id}-search`}>Find {label.toLocaleLowerCase()}</label>
              <input
                className="usa-input maxw-none"
                id={`${id}-search`}
                type="search"
                placeholder={`Find ${label.toLocaleLowerCase()}`}
                value={query}
                autoFocus
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          )}
          <div className="checkbox-picker__options">
            {filteredOptions.map((option) => {
              const optionId = `${id}-${option.value.replace(/[^A-Za-z0-9_-]/g, '-')}`;
              return (
                <div className="usa-checkbox" key={option.value}>
                  <input className="usa-checkbox__input" id={optionId} type="checkbox" checked={selectedSet.has(option.value)} onChange={() => toggle(option.value)} />
                  <label className="usa-checkbox__label" htmlFor={optionId}>{option.label}</label>
                </div>
              );
            })}
            {!filteredOptions.length && <p className="usa-hint">No matching values</p>}
          </div>
          <div className="checkbox-picker__actions">
            <span>{selected.length ? `${selected.length} selected` : 'Nothing selected'}</span>
            <button className="usa-button usa-button--unstyled" type="button" onClick={() => setOpen(false)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
