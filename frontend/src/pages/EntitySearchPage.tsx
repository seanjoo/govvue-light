import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import EntityCard from '../components/EntityCard';
import InfoTip from '../components/InfoTip';
import MultiSelectFilter, { STATE_OPTIONS, type FilterOption } from '../components/MultiSelectFilter';
import NaicsPicker from '../components/NaicsPicker';
import Pagination from '../components/Pagination';
import { api } from '../lib/api';
import type { Entity, EntitySearchResponse, ResultNavigation } from '../types';

const REGISTRATION_STATUS_OPTIONS: FilterOption[] = [
  { value: 'A', label: 'Active' },
  { value: 'E', label: 'Expired' },
];
const PURPOSE_OPTIONS: FilterOption[] = [
  { value: 'Z1', label: 'Federal Assistance Awards (Z1)' },
  { value: 'Z2', label: 'All Awards (Z2)' },
];

const EMPTY_FILTERS: Record<string, string> = {
  legal_business_name: '', uei: '', cage_code: '', dodaac: '', dba_name: '',
  sam_registered: '', registration_status: 'A', debt_subject_to_offset: '', exclusion_status: '',
  purpose_registration_code: '', purpose_registration_description: '',
  registration_date_from: '', registration_date_to: '', activation_date_from: '', activation_date_to: '',
  update_date_from: '', update_date_to: '', expiration_date_from: '', expiration_date_to: '',
  uei_creation_date_from: '', uei_creation_date_to: '',
  city: '', congressional_district: '', country_code: '', state: '', zip: '',
  entity_structure_code: '', entity_structure_description: '', organization_structure_code: '', organization_structure_description: '',
  business_type_code: '', business_type_description: '', sba_business_type_code: '', sba_business_type_description: '',
  primary_naics: '', naics_code: '', naics_description: '', naics_limited_small_business: '',
  psc_code: '', psc_description: '',
  incorporation_state_code: '', incorporation_state_description: '', incorporation_country_code: '', incorporation_country_description: '',
  disaster_state_code: '', disaster_state_name: '', disaster_county_code: '', disaster_county_name: '', disaster_msa: '', disaster_response_participant: '',
};

export default function EntitySearchPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = useMemo(() => {
    const values = { ...EMPTY_FILTERS };
    for (const key of Object.keys(values)) values[key] = searchParams.get(key) ?? values[key];
    return values;
  }, []);
  const [filters, setFilters] = useState(initial);
  const [result, setResult] = useState<EntitySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [page, setPage] = useState(Number(searchParams.get('page') ?? '1'));
  const hasInitialCriteria = [...searchParams.keys()].some((key) => key !== 'page');

  useEffect(() => { if (hasInitialCriteria) runSearch(page, initial); }, []);

  function update(name: string, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function updateSamRegistered(value: string) {
    setFilters((current) => ({
      ...current,
      sam_registered: value,
      registration_status: value === 'No' ? '' : current.registration_status || 'A',
    }));
  }

  function criteriaFrom(values: Record<string, string>) {
    return Object.fromEntries(Object.entries(values).filter(([, value]) => value));
  }

  async function runSearch(nextPage = 1, values = filters) {
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const criteria = criteriaFrom(values);
      const params = new URLSearchParams(criteria);
      params.set('page', String(nextPage));
      const response = await api<EntitySearchResponse>(`/entities/search?${params}`);
      setResult(response);
      setPage(nextPage);
      setSearchParams(params, { replace: true });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Entity search failed');
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    runSearch(1);
  }

  function reset() {
    setFilters({ ...EMPTY_FILTERS });
    setResult(null);
    setSearchParams({}, { replace: true });
    setError('');
    setMessage('');
  }

  async function saveEntity(entity: Entity) {
    try {
      await api('/saved-entities', { method: 'POST', body: JSON.stringify({ entity }) });
      setMessage(`Saved “${entity.legal_business_name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save entity');
    }
  }

  async function saveCurrentSearch() {
    const name = window.prompt('Name this entity search');
    if (!name) return;
    try {
      await api('/saved-entity-searches', {
        method: 'POST',
        body: JSON.stringify({ name, criteria: criteriaFrom(filters) }),
      });
      setMessage(`Saved entity search “${name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save entity search');
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">SAM.gov Entity Information</p><h1>Search entities</h1></div>
        <button type="button" className="usa-button usa-button--outline" onClick={saveCurrentSearch}>Save this search</button>
      </div>
      <form className="search-panel entity-search-panel" onSubmit={submit}>
        <div className="grid-row grid-gap">
          <Filter width="tablet:grid-col-6" label="Legal business name" name="legal_business_name" value={filters.legal_business_name} update={update} hint="Partial or complete name." />
          <Filter label="UEI" name="uei" value={filters.uei} update={update} hint="A 12-character UEI. Separate multiple UEIs with commas." />
          <Filter label="CAGE code" name="cage_code" value={filters.cage_code} update={update} hint="A five-character CAGE code. Separate multiple codes with commas." />
        </div>

        <details className="filter-details">
          <summary>Registration and identity filters</summary>
          <div className="grid-row grid-gap">
            <Filter label="DBA name" name="dba_name" value={filters.dba_name} update={update} />
            <Filter label="DoDAAC" name="dodaac" value={filters.dodaac} update={update} />
            <MultiSelectFilter id="entity-registration-status" label="Registration status" value={filters.registration_status} options={REGISTRATION_STATUS_OPTIONS} update={(value) => update('registration_status', value)} />
            <Select label="SAM registered" name="sam_registered" value={filters.sam_registered} update={(_, value) => updateSamRegistered(value)} options={[['', 'Registered entities (default)'], ['Yes', 'Yes'], ['No', 'No / UEI assigned only']]} />
            <MultiSelectFilter id="entity-purpose" label="Purpose of registration" value={filters.purpose_registration_code} options={PURPOSE_OPTIONS} update={(value) => update('purpose_registration_code', value)} />
            <Filter label="Purpose description" name="purpose_registration_description" value={filters.purpose_registration_description} update={update} />
            <Select label="Exclusion status" name="exclusion_status" value={filters.exclusion_status} update={update} options={[['', 'Any'], ['N', 'No active exclusion'], ['Y', 'Has exclusion']]} />
            <Select label="Debt subject to offset" name="debt_subject_to_offset" value={filters.debt_subject_to_offset} update={update} options={[['', 'Any'], ['Y', 'Yes'], ['N', 'No'], ['U', 'Unknown']]} />
          </div>
        </details>

        <details className="filter-details">
          <summary>Registration date filters</summary>
          <div className="grid-row grid-gap entity-date-grid">
            <DatePair label="Registration date" name="registration_date" filters={filters} update={update} />
            <DatePair label="Activation date" name="activation_date" filters={filters} update={update} />
            <DatePair label="Last update date" name="update_date" filters={filters} update={update} />
            <DatePair label="Expiration date" name="expiration_date" filters={filters} update={update} />
            <DatePair label="UEI creation date" name="uei_creation_date" filters={filters} update={update} />
          </div>
        </details>

        <details className="filter-details">
          <summary>Location and incorporation filters</summary>
          <div className="grid-row grid-gap">
            <MultiSelectFilter id="entity-state" label="Physical-address state" value={filters.state} options={STATE_OPTIONS} update={(value) => update('state', value)} />
            <Filter label="City" name="city" value={filters.city} update={update} />
            <Filter label="ZIP / postal code" name="zip" value={filters.zip} update={update} />
            <Filter label="Country code" name="country_code" value={filters.country_code} update={update} hint="Three-character country code, such as USA." />
            <Filter label="Congressional district" name="congressional_district" value={filters.congressional_district} update={update} />
            <MultiSelectFilter id="entity-incorporation-state" label="State of incorporation" value={filters.incorporation_state_code} options={STATE_OPTIONS} update={(value) => update('incorporation_state_code', value)} />
            <Filter label="State of incorporation description" name="incorporation_state_description" value={filters.incorporation_state_description} update={update} />
            <Filter label="Country of incorporation code" name="incorporation_country_code" value={filters.incorporation_country_code} update={update} />
            <Filter label="Country of incorporation description" name="incorporation_country_description" value={filters.incorporation_country_description} update={update} />
          </div>
        </details>

        <details className="filter-details">
          <summary>Industry, product, and business-type filters</summary>
          <div className="grid-row grid-gap">
            <NaicsPicker id="entity-search" value={filters.naics_code} update={(value) => update('naics_code', value)} maxSelections={20} />
            <Filter label="Primary NAICS" name="primary_naics" value={filters.primary_naics} update={update} hint="Six-digit codes; separate multiple codes with commas." />
            <Filter label="NAICS description" name="naics_description" value={filters.naics_description} update={update} />
            <Filter label="NAICS limited small business" name="naics_limited_small_business" value={filters.naics_limited_small_business} update={update} hint="Six-digit NAICS code." />
            <Filter label="PSC code" name="psc_code" value={filters.psc_code} update={update} hint="Four-character codes; separate multiple codes with commas." />
            <Filter label="PSC description" name="psc_description" value={filters.psc_description} update={update} />
            <Filter label="Business type code" name="business_type_code" value={filters.business_type_code} update={update} hint="Two-character codes; separate multiple codes with commas." />
            <Filter label="Business type description" name="business_type_description" value={filters.business_type_description} update={update} />
            <Filter label="SBA business type code" name="sba_business_type_code" value={filters.sba_business_type_code} update={update} />
            <Filter label="SBA business type description" name="sba_business_type_description" value={filters.sba_business_type_description} update={update} />
            <Filter label="Entity structure code" name="entity_structure_code" value={filters.entity_structure_code} update={update} />
            <Filter label="Entity structure description" name="entity_structure_description" value={filters.entity_structure_description} update={update} />
            <Filter label="Organization structure code" name="organization_structure_code" value={filters.organization_structure_code} update={update} />
            <Filter label="Organization structure description" name="organization_structure_description" value={filters.organization_structure_description} update={update} />
          </div>
        </details>

        <details className="filter-details">
          <summary>Disaster-response filters</summary>
          <div className="grid-row grid-gap">
            <Select label="Disaster-response participant" name="disaster_response_participant" value={filters.disaster_response_participant} update={update} options={[['', 'Any'], ['Yes', 'Yes'], ['No', 'No']]} />
            <MultiSelectFilter id="entity-disaster-state" label="State served" value={filters.disaster_state_code} options={STATE_OPTIONS} update={(value) => update('disaster_state_code', value)} />
            <Filter label="State served name" name="disaster_state_name" value={filters.disaster_state_name} update={update} />
            <Filter label="County served code" name="disaster_county_code" value={filters.disaster_county_code} update={update} />
            <Filter label="County served name" name="disaster_county_name" value={filters.disaster_county_name} update={update} />
            <Filter label="Metropolitan statistical area" name="disaster_msa" value={filters.disaster_msa} update={update} />
          </div>
        </details>

        <p className="usa-hint margin-top-2">Multiple values within one filter use OR; different filters use AND. GovVue requests public summary sections and displays 10 records per SAM.gov page.</p>
        <div className="entity-search-actions">
          <button className="usa-button" type="submit" disabled={loading}>{loading ? 'Searching…' : 'Search SAM.gov'}</button>
          <button className="usa-button usa-button--unstyled" type="button" onClick={reset}>Reset filters</button>
        </div>
      </form>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}
      {result && (
        <section aria-live="polite" aria-busy={loading} className="results-section">
          <div className="results-summary"><h2>{result.total_records.toLocaleString()} entities</h2><span>{result.cache_hit ? 'Cached SAM.gov response' : 'Fresh SAM.gov response'} · 10 per page</span></div>
          {result.items.length ? result.items.map((entity, index) => (
            <EntityCard
              key={entity.uei}
              entity={entity}
              onSave={saveEntity}
              navigation={resultNavigation(result, index, page, criteriaFrom(filters), `${location.pathname}${location.search}`)}
            />
          )) : <p>No entities matched these filters.</p>}
          <Pagination page={page} hasNext={result.has_next} onChange={(value) => runSearch(value)} />
        </section>
      )}
    </>
  );
}

function resultNavigation(
  result: EntitySearchResponse,
  index: number,
  page: number,
  criteria: Record<string, string>,
  returnTo: string,
): ResultNavigation {
  return {
    kind: 'entity',
    ids: result.items.map((item) => item.uei),
    index,
    page,
    per_page: result.per_page,
    total_records: result.total_records,
    has_next: result.has_next,
    criteria,
    return_to: returnTo,
    source_label: 'entity search results',
    paginated: true,
    entities: result.items,
  };
}

function Filter({ label, name, value, update, type = 'text', hint, width = 'tablet:grid-col-4' }: { label: string; name: string; value: string; update: (name: string, value: string) => void; type?: string; hint?: string; width?: string }) {
  return <div className={width}><div className="field-label"><label className="usa-label" htmlFor={name}>{label}</label>{hint && <InfoTip text={hint} label={`About ${label}`} />}</div><input className="usa-input maxw-none" id={name} type={type} value={value} onChange={(event) => update(name, event.target.value)} /></div>;
}

function Select({ label, name, value, update, options }: { label: string; name: string; value: string; update: (name: string, value: string) => void; options: [string, string][] }) {
  return <div className="tablet:grid-col-4"><label className="usa-label" htmlFor={name}>{label}</label><select className="usa-select maxw-none" id={name} value={value} onChange={(event) => update(name, event.target.value)}>{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select></div>;
}

function DatePair({ label, name, filters, update }: { label: string; name: string; filters: Record<string, string>; update: (name: string, value: string) => void }) {
  return <fieldset className="tablet:grid-col-6 entity-date-pair"><legend>{label}</legend><div><Filter width="" label="From" name={`${name}_from`} value={filters[`${name}_from`]} update={update} type="date" /><Filter width="" label="To" name={`${name}_to`} value={filters[`${name}_to`]} update={update} type="date" /></div></fieldset>;
}

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-top-3`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
