import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { DailyNotificationRunsResponse } from '../types';

export default function DailyNotificationDetailPage() {
  const { notificationId = '' } = useParams();
  const [data, setData] = useState<DailyNotificationRunsResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<DailyNotificationRunsResponse>(`/daily-notifications/${encodeURIComponent(notificationId)}/runs`)
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load notification'));
  }, [notificationId]);

  if (error) return <div className="usa-alert usa-alert--error"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>;
  if (!data) return <p>Loading…</p>;

  return <>
    <div className="page-heading"><div><p className="page-kicker">Daily notification</p><h1>{data.notification.name}</h1><p>{data.notification.enabled ? 'Enabled' : 'Paused'} · Daily at {formatScheduleTime(data.notification.schedule_time)} Eastern · {data.notification.recipient_email}</p></div><Link className="usa-button usa-button--outline" to="/notifications">Manage notifications</Link></div>
    <section className="search-panel"><h2>Filters</h2><p>{describe(data.notification.criteria)}</p><p className="usa-hint">Every run covers opportunities posted yesterday through the run date.</p></section>
    <section className="results-section"><h2>Daily runs</h2>{data.items.length ? <div className="table-scroll"><table className="usa-table usa-table--borderless width-full"><thead><tr><th>Date</th><th>Matches</th><th>Email</th><th>Completed</th></tr></thead><tbody>{data.items.map((run) => <tr key={run.run_date}><td><Link to={`/notifications/${notificationId}/runs/${run.run_date}`}>{run.run_date}</Link></td><td>{run.match_count.toLocaleString()}</td><td>{run.email_status}</td><td>{run.completed_at ? new Date(run.completed_at * 1000).toLocaleString() : '—'}</td></tr>)}</tbody></table></div> : <div className="empty-state"><h3>No runs yet</h3><p>The first run appears after the next scheduled feed or a manual run.</p></div>}</section>
  </>;
}

function describe(criteria: Record<string, string>) {
  const entries = Object.entries(criteria).filter(([, value]) => value);
  return entries.length ? entries.map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ') : 'All active opportunities';
}

function formatScheduleTime(value: string) {
  const [hour, minute] = value.split(':').map(Number);
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return value;
  return new Date(2000, 0, 1, hour, minute).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });
}
