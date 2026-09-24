import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { detailUrl, safeReturnTo, safeSourceLabel } from '../lib/detailNavigation';
import type { Opportunity, ResultNavigation, ResultNavigationState, SearchResponse } from '../types';

export default function OpportunityDetailPage() {
  const { noticeId = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [opportunity, setOpportunity] = useState<Opportunity | null>(null);
  const [error, setError] = useState('');
  const [navigationError, setNavigationError] = useState('');
  const [navigationLoading, setNavigationLoading] = useState(false);
  const routeState = location.state as ResultNavigationState | null;
  const incomingNavigation = routeState?.resultNavigation;
  const navigation = incomingNavigation?.kind === 'opportunity' ? incomingNavigation : undefined;
  const detailParams = new URLSearchParams(location.search);
  const returnTo = safeReturnTo(
    navigation?.return_to || routeState?.returnTo || detailParams.get('return_to'),
    '/search',
  );
  const sourceLabel = safeSourceLabel(
    navigation?.source_label || routeState?.sourceLabel || detailParams.get('source_label'),
    'opportunity search',
  );
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setOpportunity(null);
    setError('');
    setSaved(false);
    api<Opportunity>(`/opportunities/${encodeURIComponent(noticeId)}`)
      .then((value) => { if (!cancelled) setOpportunity(value); })
      .catch((caught) => { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to load opportunity'); });
    return () => { cancelled = true; };
  }, [noticeId]);

  async function save() {
    if (!opportunity) return;
    await api('/saved-opportunities', { method: 'POST', body: JSON.stringify({ opportunity }) });
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
        params.set('per_page', String(navigation.per_page));
        params.set('record_history', 'false');
        const response = await api<SearchResponse>(`/opportunities/search?${params}`);
        if (!response.items.length) throw new Error('No adjacent result page was returned.');
        nextIndex = direction > 0 ? 0 : response.items.length - 1;
        nextNavigation = {
          ...navigation,
          ids: response.items.map((item) => item.notice_id),
          index: nextIndex,
          page: targetPage,
          per_page: response.per_page,
          total_records: response.total_records,
          has_next: response.has_next,
          return_to: resultPageUrl(navigation.return_to, targetPage),
        };
      } else {
        nextNavigation.index = nextIndex;
      }
      navigate(detailUrl(
        `/opportunities/${encodeURIComponent(nextNavigation.ids[nextIndex])}`,
        nextNavigation.return_to,
        nextNavigation.source_label,
      ), {
        state: {
          resultNavigation: nextNavigation,
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
  if (!opportunity) return <p>Loading opportunity…</p>;

  return (
    <>
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
          <button type="button" className="usa-button usa-button--outline" onClick={save} disabled={saved}>{saved ? 'Saved' : 'Save opportunity'}</button>
          <a className="usa-button" href={opportunity.sam_url} target="_blank" rel="noreferrer">View full notice on SAM.gov</a>
        </div>
      </div>
      {navigationError && <div className="usa-alert usa-alert--error margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{navigationError}</p></div></div>}
      <article className="detail-page">
        <p className="page-kicker">{opportunity.type}</p>
        <h1>{opportunity.title}</h1>
        <dl className="detail-grid">
          <Field label="Notice ID" value={opportunity.notice_id} />
          <Field label="Solicitation number" value={opportunity.solicitation_number} />
          <Field label="Posted" value={opportunity.posted_date} />
          <Field label="Response due" value={opportunity.response_deadline} important />
          <Field label="NAICS" value={opportunity.naics_code} />
          <Field label="PSC" value={opportunity.classification_code} />
          <Field label="Set-aside" value={opportunity.set_aside} />
          <Field label="Organization" value={opportunity.organization_name || opportunity.agency_path} />
        </dl>
        <h2>Description</h2>
        <div className="opportunity-description">
          {opportunity.description ? opportunity.description.split('\n').map((paragraph, index) => <p key={index}>{paragraph}</p>) : <p>No description was returned by SAM.gov. Use the full-notice link above.</p>}
        </div>
      </article>
    </>
  );
}

function resultPageUrl(value: string, page: number) {
  const [pathname, query = ''] = value.split('?', 2);
  const params = new URLSearchParams(query);
  params.set('page', String(page));
  return `${pathname}?${params}`;
}

function Field({ label, value, important = false }: { label: string; value: string; important?: boolean }) {
  return <div className={important ? 'detail-grid__important' : ''}><dt>{label}</dt><dd>{value || '—'}</dd></div>;
}
