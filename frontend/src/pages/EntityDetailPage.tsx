import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { detailUrl, safeReturnTo, safeSourceLabel } from '../lib/detailNavigation';
import type { Entity, EntitySearchResponse, ResultNavigation, ResultNavigationState } from '../types';

export default function EntityDetailPage() {
  const { uei = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const routeState = location.state as ResultNavigationState | null;
  const incomingNavigation = routeState?.resultNavigation;
  const navigation = incomingNavigation?.kind === 'entity' ? incomingNavigation : undefined;
  const detailParams = new URLSearchParams(location.search);
  const returnTo = safeReturnTo(
    navigation?.return_to || routeState?.returnTo || detailParams.get('return_to'),
    '/entities',
  );
  const sourceLabel = safeSourceLabel(
    navigation?.source_label || routeState?.sourceLabel || detailParams.get('source_label'),
    'entity search',
  );
  const stateEntity = routeState?.entity?.uei === uei ? routeState.entity : undefined;
  const [entity, setEntity] = useState<Entity | null>(stateEntity || null);
  const [error, setError] = useState('');
  const [navigationError, setNavigationError] = useState('');
  const [navigationLoading, setNavigationLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError('');
    setSaved(false);
    if (stateEntity) {
      setEntity(stateEntity);
      return () => { cancelled = true; };
    }
    setEntity(null);
    api<Entity>(`/entities/${encodeURIComponent(uei)}`)
      .then((value) => { if (!cancelled) setEntity(value); })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to load entity'); });
    return () => { cancelled = true; };
  }, [uei, stateEntity]);

  async function save() {
    if (!entity) return;
    await api('/saved-entities', { method: 'POST', body: JSON.stringify({ entity }) });
    setSaved(true);
  }

  async function move(direction: -1 | 1) {
    if (!navigation || navigationLoading) return;
    setNavigationLoading(true);
    setNavigationError('');
    try {
      let nextNavigation: ResultNavigation = { ...navigation };
      let nextIndex = navigation.index + direction;
      if (nextIndex < 0 || nextIndex >= navigation.ids.length) {
        if (!navigation.paginated) return;
        const targetPage = navigation.page + direction;
        if (targetPage < 1 || (direction > 0 && !navigation.has_next)) return;
        const params = new URLSearchParams(navigation.criteria);
        params.set('page', String(targetPage));
        const response = await api<EntitySearchResponse>(`/entities/search?${params}`);
        if (!response.items.length) throw new Error('No adjacent result page was returned.');
        nextIndex = direction > 0 ? 0 : response.items.length - 1;
        nextNavigation = {
          ...navigation,
          ids: response.items.map((item) => item.uei),
          index: nextIndex,
          page: targetPage,
          per_page: response.per_page,
          total_records: response.total_records,
          has_next: response.has_next,
          return_to: resultPageUrl(navigation.return_to, targetPage),
          entities: response.items,
        };
      } else {
        nextNavigation.index = nextIndex;
      }
      const nextUei = nextNavigation.ids[nextIndex];
      const nextEntity = nextNavigation.entities?.find((item) => item.uei === nextUei);
      navigate(detailUrl(
        `/entities/${encodeURIComponent(nextUei)}`,
        nextNavigation.return_to,
        nextNavigation.source_label,
      ), {
        state: {
          resultNavigation: nextNavigation,
          entity: nextEntity,
          returnTo: nextNavigation.return_to,
          sourceLabel: nextNavigation.source_label,
        },
      });
    } catch (caught) {
      setNavigationError(caught instanceof Error ? caught.message : 'Unable to load the adjacent result');
    } finally {
      setNavigationLoading(false);
    }
  }

  const hasPrevious = Boolean(navigation && (navigation.index > 0 || (navigation.paginated && navigation.page > 1)));
  const hasNext = Boolean(navigation && (navigation.index < navigation.ids.length - 1 || (navigation.paginated && navigation.has_next)));
  const position = navigation ? (navigation.page - 1) * navigation.per_page + navigation.index + 1 : 0;

  if (error) return <div className="usa-alert usa-alert--error"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>;
  if (!entity) return <p>Loading entity…</p>;

  const physicalAddress = [
    entity.address.line1,
    entity.address.line2,
    [entity.address.city, entity.address.state, entity.address.zip].filter(Boolean).join(', '),
    entity.address.country,
  ].filter(Boolean).join(' · ');
  const businessTypes = [...entity.business_types, ...entity.sba_business_types]
    .map((item) => item.description || item.code)
    .filter(Boolean);

  return <>
    <div className="detail-action-bar">
      <div className="detail-result-navigation">
        <Link to={returnTo}>← Back to {sourceLabel}</Link>
        {navigation && <>
          <button className="usa-button usa-button--outline" type="button" disabled={!hasPrevious || navigationLoading} onClick={() => move(-1)}>Previous</button>
          <span aria-live="polite">{position.toLocaleString()} of {navigation.total_records.toLocaleString()}</span>
          <button className="usa-button usa-button--outline" type="button" disabled={!hasNext || navigationLoading} onClick={() => move(1)}>Next</button>
        </>}
      </div>
      <div>
        <button type="button" className="usa-button usa-button--outline" onClick={save} disabled={saved}>{saved ? 'Saved' : 'Save entity'}</button>
        <a className="usa-button" href={entity.sam_url} target="_blank" rel="noreferrer">View full entity on SAM.gov</a>
      </div>
    </div>
    {navigationError && <div className="usa-alert usa-alert--error margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{navigationError}</p></div></div>}
    <article className="detail-page entity-detail-page">
      <p className="page-kicker">{entity.registration_status || 'Registration status unavailable'}</p>
      <h1>{entity.legal_business_name}</h1>
      {entity.dba_name && <p>Doing business as {entity.dba_name}</p>}
      <dl className="detail-grid">
        <Field label="UEI" value={entity.uei} />
        <Field label="CAGE" value={entity.cage_code} />
        <Field label="Registration expires" value={entity.expiration_date} />
        <Field label="Purpose" value={entity.purpose_of_registration} />
        <Field label="Primary NAICS" value={entity.primary_naics} />
        <Field label="Exclusion status" value={entity.exclusion_status} />
        <Field label="Entity structure" value={entity.entity_structure} />
        <Field label="Organization structure" value={entity.organization_structure} />
      </dl>
      <h2>Contact and location</h2>
      <dl className="detail-grid">
        <Field label="Physical address" value={physicalAddress} />
        <Field label="Website" value={entity.website} link />
      </dl>
      <ClassificationList heading="Business types" values={businessTypes} />
      <ClassificationList heading="NAICS codes" values={entity.naics.map((item) => [item.code, item.description].filter(Boolean).join(' — '))} />
      <ClassificationList heading="PSC codes" values={entity.psc.map((item) => [item.code, item.description].filter(Boolean).join(' — '))} />
    </article>
  </>;
}

function resultPageUrl(value: string, page: number) {
  const [pathname, query = ''] = value.split('?', 2);
  const params = new URLSearchParams(query);
  params.set('page', String(page));
  return `${pathname}?${params}`;
}

function Field({ label, value, link = false }: { label: string; value: string; link?: boolean }) {
  const href = value && link ? (/^https?:\/\//i.test(value) ? value : `https://${value}`) : '';
  return <div><dt>{label}</dt><dd>{href ? <a href={href} target="_blank" rel="noreferrer">{value}</a> : value || '—'}</dd></div>;
}

function ClassificationList({ heading, values }: { heading: string; values: string[] }) {
  if (!values.length) return null;
  return <section className="entity-detail-classifications"><h2>{heading}</h2><ul className="usa-list">{values.map((value) => <li key={value}>{value}</li>)}</ul></section>;
}
