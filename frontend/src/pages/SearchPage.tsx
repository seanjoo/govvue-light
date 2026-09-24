import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import OpportunityCard from '../components/OpportunityCard';
import Pagination from '../components/Pagination';
import MultiSelectFilter, {
  NOTICE_TYPE_OPTIONS,
  SET_ASIDE_OPTIONS,
  STATE_OPTIONS,
} from '../components/MultiSelectFilter';
import NaicsPicker from '../components/NaicsPicker';
import PostedDateFilter from '../components/PostedDateFilter';
import InfoTip from '../components/InfoTip';
import { api } from '../lib/api';
import { createNotificationDraft } from '../lib/notificationDraft';
import type { Opportunity, ResultNavigation, SearchResponse } from '../types';

const today = new Date();
const prior = new Date(today);
prior.setDate(today.getDate() - 30);
const iso = (value: Date) => value.toISOString().slice(0, 10);
const SORT_OPTIONS = [
  ['response_deadline_desc', 'Response due — latest first'],
  ['response_deadline_asc', 'Response due — soonest first'],
  ['posted_desc', 'Posted date — newest first'],
  ['posted_asc', 'Posted date — oldest first'],
] as const;

const EMPTY_FILTERS: Record<string, string> = {
  title: '',
  notice_id: '',
  solicitation_number: '',
  ptype: '',
  naics_code: '',
  classification_code: '',
  set_aside: '',
  state: '',
  organization_name: '',
  posted_within: '',
  posted_from: iso(prior),
  posted_to: iso(today),
  response_deadline_from: '',
  response_deadline_to: '',
  open_deadlines_only: '',
  sort: 'response_deadline_desc',
};

export default function SearchPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = useMemo(() => {
    const values = { ...EMPTY_FILTERS };
    for (const key of Object.keys(values)) values[key] = searchParams.get(key) ?? values[key];
    if (values.posted_within) {
      values.posted_from = '';
      values.posted_to = '';
    }
    return values;
  }, []); // intentionally only read the initial URL
  const [filters, setFilters] = useState(initial);
  const [postedDateMode, setPostedDateMode] = useState<'range' | 'rolling'>(
    initial.posted_within ? 'rolling' : 'range',
  );
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [page, setPage] = useState(Number(searchParams.get('page') ?? '1'));
  const [lastSearchCriteria, setLastSearchCriteria] = useState<Record<string, string> | null>(null);

  const hasInitialCriteria = [...searchParams.keys()].some((key) => key !== 'page');
  useEffect(() => {
    if (hasInitialCriteria) runSearch(page, false);
  }, []); // saved-search URL should run once

  function update(name: string, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function updatePostedDateMode(mode: 'range' | 'rolling') {
    setPostedDateMode(mode);
    setFilters((current) => mode === 'rolling'
      ? { ...current, posted_from: '', posted_to: '', posted_within: current.posted_within || '30' }
      : {
        ...current,
        posted_within: '',
        posted_from: current.posted_from || iso(prior),
        posted_to: current.posted_to || iso(today),
      });
  }

  async function runSearch(nextPage = 1, recordHistory = nextPage === 1) {
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const criteria = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      const params = new URLSearchParams();
      Object.entries(criteria).forEach(([key, value]) => params.set(key, value));
      params.set('page', String(nextPage));
      params.set('per_page', '25');
      params.set('record_history', String(recordHistory));
      const response = await api<SearchResponse>(`/opportunities/search?${params}`);
      setResult(response);
      setLastSearchCriteria(criteria);
      setPage(nextPage);
      const visibleParams = new URLSearchParams(params);
      visibleParams.delete('record_history');
      visibleParams.delete('per_page');
      setSearchParams(visibleParams, { replace: true });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  async function saveOpportunity(opportunity: Opportunity) {
    try {
      await api('/saved-opportunities', { method: 'POST', body: JSON.stringify({ opportunity }) });
      setMessage(`Saved “${opportunity.title}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save opportunity');
    }
  }

  async function saveCurrentSearch() {
    const name = window.prompt('Name this search');
    if (!name) return;
    const criteria = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
    try {
      await api('/saved-searches', { method: 'POST', body: JSON.stringify({ name, criteria }) });
      setMessage(`Saved search “${name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save search');
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    runSearch(1, true);
  }

  function createDailyNotification() {
    if (!lastSearchCriteria) return;
    const sourceName = lastSearchCriteria.title || 'Opportunity search';
    navigate('/notifications', {
      state: { notificationDraft: createNotificationDraft(sourceName, lastSearchCriteria) },
    });
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">SAM.gov Contract Opportunities</p><h1>Search active opportunities</h1></div>
        <button type="button" className="usa-button usa-button--outline" onClick={saveCurrentSearch}>Save this search</button>
      </div>
      <form className="search-panel" onSubmit={submit}>
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-6">
            <label className="usa-label" htmlFor="title">Title or keywords</label>
            <input className="usa-input maxw-none" id="title" value={filters.title} onChange={(event) => update('title', event.target.value)} />
          </div>
          <div className="tablet:grid-col-3">
            <label className="usa-label" htmlFor="notice_id">Notice ID</label>
            <input className="usa-input maxw-none" id="notice_id" value={filters.notice_id} onChange={(event) => update('notice_id', event.target.value)} />
          </div>
          <div className="tablet:grid-col-3">
            <div className="field-label">
              <label className="usa-label" htmlFor="sort">Sort results</label>
              <InfoTip text="SAM.gov does not sort upstream. Non-default orders load the complete matching page set before sorting." label="About result sorting" />
            </div>
            <select className="usa-select maxw-none" id="sort" value={filters.sort} onChange={(event) => update('sort', event.target.value)}>
              {SORT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>
        <details className="filter-details">
          <summary>More filters</summary>
          <div className="grid-row grid-gap">
            <Filter label="Solicitation number" name="solicitation_number" value={filters.solicitation_number} update={update} />
            <Filter label="PSC / classification code" name="classification_code" value={filters.classification_code} update={update} hint="Separate multiple codes with commas." />
            <Filter label="Organization" name="organization_name" value={filters.organization_name} update={update} />
            <PostedDateFilter
              mode={postedDateMode}
              postedFrom={filters.posted_from}
              postedTo={filters.posted_to}
              postedWithin={filters.posted_within}
              updateMode={updatePostedDateMode}
              update={update}
            />
            <Filter label="Response due from" name="response_deadline_from" value={filters.response_deadline_from} update={update} type="date" />
            <Filter label="Response due to" name="response_deadline_to" value={filters.response_deadline_to} update={update} type="date" />
            <div className="tablet:grid-col-4 deadline-filter">
              <div className="usa-checkbox">
                <input
                  className="usa-checkbox__input"
                  id="open_deadlines_only"
                  type="checkbox"
                  checked={filters.open_deadlines_only === 'true'}
                  onChange={(event) => update('open_deadlines_only', event.target.checked ? 'true' : '')}
                />
                <label className="usa-checkbox__label" htmlFor="open_deadlines_only">Exclude past response deadlines</label>
              </div>
              <InfoTip text="Uses the current date each time the search runs, including from a saved search." label="About excluding past response deadlines" />
            </div>
            <MultiSelectFilter id="ptype" label="Notice type" value={filters.ptype} options={NOTICE_TYPE_OPTIONS} update={(value) => update('ptype', value)} />
            <MultiSelectFilter id="set_aside" label="Set-aside" value={filters.set_aside} options={SET_ASIDE_OPTIONS} update={(value) => update('set_aside', value)} />
            <MultiSelectFilter id="state" label="Place-of-performance state" value={filters.state} options={STATE_OPTIONS} update={(value) => update('state', value)} />
            <NaicsPicker id="search" value={filters.naics_code} update={(value) => update('naics_code', value)} />
          </div>
          <p className="usa-hint margin-top-2">Multiple values within one filter use OR. Different filters are combined with AND. A search is limited to 12 SAM.gov request combinations.</p>
        </details>
        <button className="usa-button margin-top-3" type="submit" disabled={loading}>{loading ? 'Searching…' : 'Search SAM.gov'}</button>
      </form>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}
      {result && (
        <section aria-live="polite" aria-busy={loading} className="results-section">
          <div className="results-summary">
            <h2>{result.total_records.toLocaleString()} active opportunities</h2>
            <div className="results-summary__actions">
              <span>{result.cache_hit ? 'Cached SAM.gov response' : 'Fresh SAM.gov response'}{result.upstream_queries > 1 ? ` · merged ${result.upstream_queries} searches` : ''}</span>
              <button className="usa-button usa-button--outline" type="button" onClick={createDailyNotification}>Create daily notification</button>
            </div>
          </div>
          {result.items.length ? result.items.map((opportunity, index) => (
            <OpportunityCard
              key={opportunity.notice_id}
              opportunity={opportunity}
              onSave={saveOpportunity}
              navigation={resultNavigation(result, index, page, lastSearchCriteria || criteriaFromFilters(filters), `${location.pathname}${location.search}`)}
            />
          )) : <p>No active opportunities matched these filters.</p>}
          <Pagination page={page} hasNext={result.has_next} onChange={(value) => runSearch(value, false)} />
        </section>
      )}
    </>
  );
}

function criteriaFromFilters(filters: Record<string, string>) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
}

function resultNavigation(
  result: SearchResponse,
  index: number,
  page: number,
  criteria: Record<string, string>,
  returnTo: string,
): ResultNavigation {
  return {
    kind: 'opportunity',
    ids: result.items.map((item) => item.notice_id),
    index,
    page,
    per_page: result.per_page,
    total_records: result.total_records,
    has_next: result.has_next,
    criteria,
    return_to: returnTo,
    source_label: 'opportunity search results',
    paginated: true,
  };
}

function Filter({ label, name, value, update, type = 'text', hint }: { label: string; name: string; value: string; update: (name: string, value: string) => void; type?: string; hint?: string }) {
  return (
    <div className="tablet:grid-col-4">
      <div className="field-label">
        <label className="usa-label" htmlFor={name}>{label}</label>
        {hint && <InfoTip text={hint} label={`About ${label}`} />}
      </div>
      <input className="usa-input maxw-none" id={name} type={type} value={value} onChange={(event) => update(name, event.target.value)} />
    </div>
  );
}

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-top-3`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
