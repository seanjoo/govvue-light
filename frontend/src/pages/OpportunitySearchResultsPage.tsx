import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import OpportunityCard from '../components/OpportunityCard';
import Pagination from '../components/Pagination';
import SavedSearchCriteria from '../components/SavedSearchCriteria';
import { api } from '../lib/api';
import { createNotificationDraft } from '../lib/notificationDraft';
import {
  OPPORTUNITY_SORT_OPTIONS,
  opportunityFiltersUrl,
  opportunityResultsQuery,
  opportunityResultsUrl,
} from '../lib/opportunitySearch';
import type { Opportunity, ResultNavigation, SearchResponse } from '../types';

const PER_PAGE = 25;

export default function OpportunitySearchResultsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { criteria, page } = useMemo(() => opportunityResultsQuery(location.search), [location.search]);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    const recordHistory = page === 1 && Boolean((location.state as { recordHistory?: boolean } | null)?.recordHistory);
    const params = new URLSearchParams(criteria);
    params.set('page', String(page));
    params.set('per_page', String(PER_PAGE));
    params.set('record_history', String(recordHistory));
    setResult(null);
    setLoading(true);
    setError('');
    setMessage('');
    if (recordHistory) navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
    api<SearchResponse>(`/opportunities/search?${params}`)
      .then((response) => {
        if (cancelled) return;
        const lastPage = Math.max(1, Math.min(10_000, Math.ceil(response.total_records / response.per_page)));
        if (page > lastPage) {
          navigate(opportunityResultsUrl(criteria, lastPage), { replace: true });
        } else {
          setResult(response);
        }
      })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Search failed'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [location.search]);

  async function saveOpportunity(opportunity: Opportunity) {
    setError('');
    try {
      await api('/saved-opportunities', { method: 'POST', body: JSON.stringify({ opportunity }) });
      setMessage(`Saved “${opportunity.title}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save opportunity');
    }
  }

  async function saveSearch() {
    const name = window.prompt('Name this search');
    if (!name) return;
    setError('');
    try {
      await api('/saved-searches', { method: 'POST', body: JSON.stringify({ name, criteria }) });
      setMessage(`Saved search “${name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save search');
    }
  }

  function createDailyNotification() {
    navigate('/notifications', {
      state: { notificationDraft: createNotificationDraft(criteria.title || 'Opportunity search', criteria) },
    });
  }

  function changePage(nextPage: number) {
    navigate(opportunityResultsUrl(criteria, nextPage));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const returnTo = `${location.pathname}${location.search}`;
  const totalPages = result ? Math.max(1, Math.min(10_000, Math.ceil(result.total_records / result.per_page))) : 1;
  const displayCriteria = Object.fromEntries(Object.entries(criteria).filter(([key]) => key !== 'sort'));

  return <>
    <div className="page-heading">
      <div><p className="page-kicker">SAM.gov Contract Opportunities</p><h1>Search results</h1></div>
      <div className="page-heading__actions">
        <Link className="usa-button usa-button--outline" to={opportunityFiltersUrl(criteria)}>← Edit search filters</Link>
        <button className="usa-button usa-button--outline" type="button" onClick={saveSearch}>Save this search</button>
      </div>
    </div>

    <div className="search-results-criteria">
      <strong>Current search</strong>
      <SavedSearchCriteria criteria={displayCriteria} emptyLabel="All active opportunities" />
    </div>

    {error && <div className="usa-alert usa-alert--error margin-bottom-3" role="alert"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
    {message && <div className="usa-alert usa-alert--success margin-bottom-3" role="status"><div className="usa-alert__body"><p className="usa-alert__text">{message}</p></div></div>}

    <div className="search-results-toolbar">
      <div>{result ? <strong>{result.total_records.toLocaleString()} active opportunities</strong> : loading ? 'Searching active opportunities…' : 'Search results'}</div>
      <label className="search-results-toolbar__sort" htmlFor="results-sort">Sort by
        <select className="usa-select" id="results-sort" value={criteria.sort} onChange={(event) => navigate(opportunityResultsUrl({ ...criteria, sort: event.target.value }))}>
          {OPPORTUNITY_SORT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
    </div>

    {loading && <p role="status">Loading results…</p>}
    {result && <section aria-live="polite" className="results-section">
      <div className="results-summary">
        <span>{result.source === 'local' ? `Local index · SAM data as of ${result.source_date || 'unknown'}` : result.cache_hit ? 'Cached SAM.gov response' : 'Fresh SAM.gov response'}{result.upstream_queries > 1 ? ` · merged ${result.upstream_queries} searches` : ''}</span>
        <button className="usa-button usa-button--outline" type="button" onClick={createDailyNotification}>Create daily notification</button>
      </div>
      {result.items.length ? result.items.map((opportunity, index) => (
        <OpportunityCard
          key={opportunity.notice_id}
          opportunity={opportunity}
          onSave={saveOpportunity}
          navigation={resultNavigation(result, index, criteria, returnTo)}
        />
      )) : <div>
        <p>No active opportunities matched these filters.</p>
        {criteria.notice_id && !criteria.notice_id.includes(',') && <p>Looking for an older notice? <a href={`https://sam.gov/opp/${encodeURIComponent(criteria.notice_id.trim())}/view`} target="_blank" rel="noreferrer">Try opening it on SAM.gov ↗</a></p>}
      </div>}
      <Pagination page={page} hasNext={result.has_next} totalPages={totalPages} onChange={changePage} />
    </section>}
  </>;
}

function resultNavigation(result: SearchResponse, index: number, criteria: Record<string, string>, returnTo: string): ResultNavigation {
  return {
    kind: 'opportunity',
    ids: result.items.map((item) => item.notice_id),
    index,
    page: result.page,
    per_page: result.per_page,
    total_records: result.total_records,
    has_next: result.has_next,
    criteria,
    return_to: returnTo,
    source_label: 'search results',
    paginated: true,
  };
}
