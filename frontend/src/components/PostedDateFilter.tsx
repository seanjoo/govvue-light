const ROLLING_WINDOWS = [7, 14, 30, 60, 90] as const;

type PostedDateFilterProps = {
  mode: 'range' | 'rolling';
  postedFrom: string;
  postedTo: string;
  postedWithin: string;
  updateMode: (mode: 'range' | 'rolling') => void;
  update: (name: string, value: string) => void;
};

export default function PostedDateFilter({
  mode,
  postedFrom,
  postedTo,
  postedWithin,
  updateMode,
  update,
}: PostedDateFilterProps) {
  return (
    <fieldset className="usa-fieldset posted-date-filter tablet:grid-col-12">
      <legend className="usa-legend">Posted date</legend>
      <span className="usa-hint">SAM.gov requires a posted-date window.</span>
      <div className="posted-date-filter__modes">
        <div className="usa-radio">
          <input
            className="usa-radio__input"
            id="posted-date-range"
            type="radio"
            name="posted-date-mode"
            value="range"
            checked={mode === 'range'}
            onChange={() => updateMode('range')}
          />
          <label className="usa-radio__label" htmlFor="posted-date-range">Date range</label>
        </div>
        <div className="usa-radio">
          <input
            className="usa-radio__input"
            id="posted-date-rolling"
            type="radio"
            name="posted-date-mode"
            value="rolling"
            checked={mode === 'rolling'}
            onChange={() => updateMode('rolling')}
          />
          <label className="usa-radio__label" htmlFor="posted-date-rolling">Rolling window</label>
        </div>
      </div>

      {mode === 'range' ? (
        <div className="grid-row grid-gap posted-date-filter__values">
          <div className="tablet:grid-col-4">
            <label className="usa-label" htmlFor="posted_from">Posted from</label>
            <input
              className="usa-input maxw-none"
              id="posted_from"
              type="date"
              required
              value={postedFrom}
              onChange={(event) => update('posted_from', event.target.value)}
            />
          </div>
          <div className="tablet:grid-col-4">
            <label className="usa-label" htmlFor="posted_to">Posted to</label>
            <input
              className="usa-input maxw-none"
              id="posted_to"
              type="date"
              required
              value={postedTo}
              onChange={(event) => update('posted_to', event.target.value)}
            />
          </div>
        </div>
      ) : (
        <div className="posted-date-filter__values posted-date-filter__rolling">
          <label className="usa-label" htmlFor="posted_within">Posted within</label>
          <select
            className="usa-select"
            id="posted_within"
            required
            value={postedWithin}
            onChange={(event) => update('posted_within', event.target.value)}
          >
            {ROLLING_WINDOWS.map((days) => <option key={days} value={days}>Last {days} days</option>)}
          </select>
          <span className="usa-hint">The date range is recalculated whenever the search runs.</span>
        </div>
      )}
    </fieldset>
  );
}
