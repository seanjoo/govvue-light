import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import OpportunityCard from '../components/OpportunityCard';
import { api } from '../lib/api';
import type { DailyNotificationResultsResponse, Opportunity } from '../types';

export default function DailyNotificationRunPage() {
  const { notificationId = '', runDate = '' } = useParams();
  const [data, setData] = useState<DailyNotificationResultsResponse | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [backStack, setBackStack] = useState<(string | null)[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function load(nextCursor: string | null) {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ limit: '25' });
      if (nextCursor) params.set('cursor', nextCursor);
      const response = await api<DailyNotificationResultsResponse>(`/daily-notifications/${encodeURIComponent(notificationId)}/runs/${encodeURIComponent(runDate)}?${params}`);
      setData(response);
      setCursor(nextCursor);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load daily results');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(null); }, [notificationId, runDate]);

  async function saveOpportunity(opportunity: Opportunity) {
    try {
      await api('/saved-opportunities', { method: 'POST', body: JSON.stringify({ opportunity }) });
      setMessage(`Saved “${opportunity.title}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save opportunity');
    }
  }

  function next() {
    if (!data?.next_cursor) return;
    setBackStack((current) => [...current, cursor]);
    load(data.next_cursor);
  }

  function previous() {
    if (!backStack.length) return;
    const previousCursor = backStack[backStack.length - 1];
    setBackStack((current) => current.slice(0, -1));
    load(previousCursor);
  }

  if (!data && loading) return <p>Loading…</p>;
  return <>
    <div className="page-heading"><div><p className="page-kicker">Daily results · {runDate}</p><h1>{data?.notification.name || 'Daily notification'}</h1></div><Link className="usa-button usa-button--outline" to={`/notifications/${notificationId}`}>Run history</Link></div>
    {error && <div className="usa-alert usa-alert--error margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
    {message && <div className="usa-alert usa-alert--success margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{message}</p></div></div>}
    {data && <section aria-busy={loading}><div className="results-summary"><h2>{data.run.match_count.toLocaleString()} matches</h2><span>Email: {data.run.email_status}</span></div>{data.items.length ? data.items.map((opportunity) => <OpportunityCard key={opportunity.notice_id} opportunity={opportunity} onSave={saveOpportunity} returnTo={`/notifications/${encodeURIComponent(notificationId)}/runs/${encodeURIComponent(runDate)}`} sourceLabel="daily notification results" />) : <div className="empty-state"><h3>No matching opportunities</h3><p>The daily email was still generated for this notification.</p></div>}<nav className="pager" aria-label="Daily result pages"><button className="usa-button usa-button--outline" type="button" disabled={!backStack.length || loading} onClick={previous}>Previous</button><button className="usa-button usa-button--outline" type="button" disabled={!data.next_cursor || loading} onClick={next}>Next</button></nav></section>}
  </>;
}
