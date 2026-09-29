import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import MultiSelectFilter, {
  NOTICE_TYPE_OPTIONS,
  SET_ASIDE_OPTIONS,
  STATE_OPTIONS,
} from '../components/MultiSelectFilter';
import NaicsPicker from '../components/NaicsPicker';
import PostedDateFilter from '../components/PostedDateFilter';
import InfoTip from '../components/InfoTip';
import { api } from '../lib/api';
import { compactSearchCriteria, OPPORTUNITY_SORT_OPTIONS, opportunityResultsUrl } from '../lib/opportunitySearch';
import type { SearchInterpretation, UserContext } from '../types';

const today = new Date();
const prior = new Date(today);
prior.setDate(today.getDate() - 30);
const iso = (value: Date) => value.toISOString().slice(0, 10);
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
  exclude_organization_name: '',
  include_terms_any: '',
  exclude_terms: '',
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
  const [searchParams] = useSearchParams();
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
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [userContext, setUserContext] = useState<UserContext | null>(null);
  const [aiQuery, setAiQuery] = useState('');
  const [profileMode, setProfileMode] = useState<'auto' | 'include' | 'exclude'>('auto');
  const [buildingPlan, setBuildingPlan] = useState(false);
  const [interpretation, setInterpretation] = useState<SearchInterpretation | null>(null);

  useEffect(() => {
    api<UserContext>('/me').then(setUserContext).catch(() => undefined);
  }, []);

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

  async function saveCurrentSearch() {
    const name = window.prompt('Name this search');
    if (!name) return;
    const criteria = compactSearchCriteria(filters);
    try {
      await api('/saved-searches', { method: 'POST', body: JSON.stringify({ name, criteria }) });
      setMessage(`Saved search “${name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save search');
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    navigate(opportunityResultsUrl(filters), { state: { recordHistory: true } });
  }

  async function buildAiSearch(event: FormEvent) {
    event.preventDefault();
    setBuildingPlan(true);
    setError('');
    setMessage('');
    try {
      const plan = await api<SearchInterpretation>('/opportunities/search/interpret', {
        method: 'POST',
        body: JSON.stringify({ query: aiQuery, profile_mode: userContext?.company ? profileMode : 'exclude' }),
      });
      const next = { ...EMPTY_FILTERS, ...plan.criteria };
      if (next.posted_within) {
        next.posted_from = '';
        next.posted_to = '';
        setPostedDateMode('rolling');
      } else {
        next.posted_from ||= iso(prior);
        next.posted_to ||= iso(today);
        setPostedDateMode('range');
      }
      setFilters(next);
      setInterpretation(plan);
      setMessage('Search filters are ready. Review or edit them, then search.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to build the search');
    } finally {
      setBuildingPlan(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">SAM.gov Contract Opportunities</p><h1>Search active opportunities</h1></div>
        <button type="button" className="usa-button usa-button--outline" onClick={saveCurrentSearch}>Save this search</button>
      </div>
      {userContext?.features.includes('natural_language_search') && (
        <section className="ai-search-builder" aria-labelledby="ai-search-heading">
          <div className="ai-search-builder__heading">
            <div><p className="page-kicker">AI search builder</p><h2 id="ai-search-heading">Describe what you want to find</h2></div>
            <span className="status-pill status-pill--enabled">Preview</span>
          </div>
          <form onSubmit={buildAiSearch}>
            <label className="usa-label" htmlFor="ai-search-query">Opportunity description</label>
            <span className="usa-hint">Use plain language. The builder creates editable local-search filters; it does not rank or process results with AI.</span>
            <textarea className="usa-textarea maxw-none" id="ai-search-query" rows={4} required minLength={5} maxLength={2000} value={aiQuery} onChange={(event) => setAiQuery(event.target.value)} placeholder={userContext.company ? 'Example: Find custom web application development and O&M support opportunities in the defense sector that fit our company.' : 'Example: Find custom web application development and O&M support opportunities in the defense sector.'} />
            <div className="ai-search-builder__actions">
              <div>
                {userContext.company ? (
                  <>
                    <label className="usa-label" htmlFor="profile-mode">Company profile</label>
                    <select className="usa-select" id="profile-mode" value={profileMode} onChange={(event) => setProfileMode(event.target.value as 'auto' | 'include' | 'exclude')}>
                      <option value="auto">Use automatically when relevant</option>
                      <option value="include">Always use company profile</option>
                      <option value="exclude">Do not use company profile</option>
                    </select>
                  </>
                ) : (
                  <>
                    <span className="usa-label">Company profile</span>
                    <Link className="usa-button usa-button--outline" to="/company-profile">Create a company profile</Link>
                  </>
                )}
              </div>
              <button className="usa-button" type="submit" disabled={buildingPlan}>{buildingPlan ? 'Building filters…' : 'Build search filters'}</button>
            </div>
            <p className="usa-hint">{userContext.company ? <>Shared profile: <Link to="/company-profile">{userContext.company.name}</Link></> : 'You can build search filters without a company profile, then create one to tailor future searches.'}</p>
          </form>
          {interpretation && (
            <div className="ai-search-plan" role="status">
              <strong>{interpretation.interpretation}</strong>
              <p>{interpretation.used_company_profile ? `Used ${interpretation.company_name || 'your company'}’s shared profile.` : 'The company profile was not used for this plan.'}</p>
              {interpretation.assumptions.length > 0 && <details><summary>Assumptions</summary><ul>{interpretation.assumptions.map((value) => <li key={value}>{value}</li>)}</ul></details>}
            </div>
          )}
        </section>
      )}
      <form className="search-panel" onSubmit={submit}>
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-6">
            <div className="field-label">
              <label className="usa-label" htmlFor="title">Title or keywords</label>
            </div>
            <input className="usa-input maxw-none" id="title" value={filters.title} onChange={(event) => update('title', event.target.value)} />
          </div>
          <div className="tablet:grid-col-3">
            <div className="field-label">
              <label className="usa-label" htmlFor="solicitation_number">Notice ID</label>
            </div>
            <input className="usa-input maxw-none" id="solicitation_number" value={filters.solicitation_number} onChange={(event) => update('solicitation_number', event.target.value)} />
          </div>
          <div className="tablet:grid-col-3">
            <div className="field-label">
              <label className="usa-label" htmlFor="sort">Sort results</label>
              <InfoTip text="Local results are sorted across all matches. A live SAM.gov fallback may require extra requests and has its own limits." label="About result sorting" />
            </div>
            <select className="usa-select maxw-none" id="sort" value={filters.sort} onChange={(event) => update('sort', event.target.value)}>
              {OPPORTUNITY_SORT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>
        <details className="filter-details">
          <summary>More filters</summary>
          <div className="grid-row grid-gap">
            <Filter label="Record ID" name="notice_id" value={filters.notice_id} update={update} />
            <Filter label="PSC / classification code" name="classification_code" value={filters.classification_code} update={update} hint="Separate multiple codes with commas." />
            <Filter label="Organization" name="organization_name" value={filters.organization_name} update={update} hint="Use one organization, or separate multiple exact organization names with |." />
            <Filter label="Exclude organizations" name="exclude_organization_name" value={filters.exclude_organization_name} update={update} hint="Separate multiple agencies or organizations with |. Useful for excluding DoD from civilian searches." />
            <Filter label="Any of these keywords" name="include_terms_any" value={filters.include_terms_any} update={update} hint="Match any of these terms in title, description, or agency." />
            <Filter label="Exclude keywords" name="exclude_terms" value={filters.exclude_terms} update={update} hint="Exclude results containing these terms." />
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
          <p className="usa-hint margin-top-2">Multiple values within one filter use OR. Different inclusion filters are combined with AND. Local search has no SAM.gov request-combination limit.</p>
        </details>
        <button className="usa-button margin-top-3" type="submit">Search opportunities</button>
      </form>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}
    </>
  );
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
