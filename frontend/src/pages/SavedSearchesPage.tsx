import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import SavedSearchCriteria from '../components/SavedSearchCriteria';
import { api } from '../lib/api';
import { createNotificationDraft } from '../lib/notificationDraft';
import type { DailyNotification, SavedSearch, SearchHistory } from '../types';

export default function SavedSearchesPage() {
  const navigate = useNavigate();
  const [saved, setSaved] = useState<SavedSearch[]>([]);
  const [history, setHistory] = useState<SearchHistory[]>([]);
  const [creatingNotificationId, setCreatingNotificationId] = useState('');
  const [error, setError] = useState('');

  function load() {
    Promise.all([
      api<{ items: SavedSearch[] }>('/saved-searches'),
      api<{ items: SearchHistory[] }>('/search-history'),
    ]).then(([savedResult, historyResult]) => {
      setSaved(savedResult.items);
      setHistory(historyResult.items);
    });
  }
  useEffect(load, []);

  function searchUrl(criteria: Record<string, string>) {
    return `/search?${new URLSearchParams(criteria)}`;
  }

  async function remove(searchId: string) {
    await api(`/saved-searches/${searchId}`, { method: 'DELETE' });
    load();
  }

  async function clearHistory() {
    if (!window.confirm('Clear your search history?')) return;
    await api('/search-history', { method: 'DELETE' });
    setHistory([]);
  }

  async function createNotification(item: SavedSearch) {
    setCreatingNotificationId(item.id);
    setError('');
    const draft = createNotificationDraft(item.name, item.criteria);
    try {
      const notification = await api<DailyNotification>('/daily-notifications', {
        method: 'POST',
        body: JSON.stringify({ name: draft.name, enabled: true, criteria: draft.criteria }),
      });
      navigate(`/notifications/${notification.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create daily notification');
      setCreatingNotificationId('');
    }
  }

  return (
    <>
      <div className="page-heading"><div><p className="page-kicker">Reusable filters</p><h1>Saved searches</h1></div></div>
      {error && <div className="usa-alert usa-alert--error margin-bottom-3" role="alert"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
      <div className="saved-search-grid">
        {saved.length ? saved.map((item) => (
          <article className="saved-search-card" key={item.id}>
            <h2>{item.name}</h2>
            <SavedSearchCriteria criteria={item.criteria} emptyLabel="All active opportunities" />
            <div>
              <Link className="usa-button" to={searchUrl(item.criteria)}>Run search</Link>
              <button
                className="usa-button usa-button--outline"
                type="button"
                disabled={Boolean(creatingNotificationId)}
                onClick={() => createNotification(item)}
              >{creatingNotificationId === item.id ? 'Creating…' : 'Create notification'}</button>
              <button className="usa-button usa-button--unstyled" type="button" onClick={() => remove(item.id)}>Delete</button>
            </div>
          </article>
        )) : <p>No saved searches yet.</p>}
      </div>
      <div className="section-heading"><h2>Recent search history</h2><button type="button" className="usa-button usa-button--unstyled" disabled={!history.length} onClick={clearHistory}>Clear history</button></div>
      <ul className="usa-list usa-list--unstyled history-list">
        {history.map((item) => <li key={`${item.created_at}-${JSON.stringify(item.criteria)}`}><Link to={searchUrl(item.criteria)}>{describe(item.criteria)}</Link><span>{item.result_count.toLocaleString()} results · {new Date(item.created_at * 1000).toLocaleString()}</span></li>)}
      </ul>
    </>
  );
}

function describe(criteria: Record<string, string>) {
  const meaningful = Object.entries(criteria).filter(([, value]) => value).slice(0, 4);
  return meaningful.length ? meaningful.map(([key, value]) => (
    key === 'posted_within'
      ? `posted date: last ${value} days`
      : `${key.replaceAll('_', ' ')}: ${value}`
  )).join(' · ') : 'All active opportunities';
}
