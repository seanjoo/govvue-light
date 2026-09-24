import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import type { Opportunity } from '../types';

export default function SavedOpportunitiesPage() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');

  function load() {
    api<{ items: Opportunity[] }>('/saved-opportunities')
      .then((result) => setItems(result.items))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load saved opportunities'));
  }
  useEffect(load, []);

  function toggle(noticeId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(noticeId)) next.delete(noticeId); else next.add(noticeId);
      return next;
    });
  }

  async function removeSelected() {
    if (!selected.size || !window.confirm(`Remove ${selected.size} saved opportunity${selected.size === 1 ? '' : 's'}?`)) return;
    await api('/saved-opportunities', { method: 'DELETE', body: JSON.stringify({ notice_ids: [...selected] }) });
    setSelected(new Set());
    load();
  }

  return (
    <>
      <div className="page-heading"><div><p className="page-kicker">Your workspace</p><h1>Saved opportunities</h1></div><button className="usa-button usa-button--secondary" type="button" disabled={!selected.size} onClick={removeSelected}>Remove selected</button></div>
      {error && <p className="usa-error-message">{error}</p>}
      {!items.length ? <div className="empty-state"><h2>No saved opportunities</h2><p>Save an opportunity from search results to keep it here.</p><Link className="usa-button" to="/search">Search opportunities</Link></div> : (
        <div className="table-scroll">
          <table className="usa-table usa-table--borderless width-full">
            <thead><tr><th scope="col"><span className="usa-sr-only">Select</span></th><th scope="col">Opportunity</th><th scope="col">Notice ID</th><th scope="col">Due date</th><th scope="col">Set-aside</th><th scope="col">NAICS</th></tr></thead>
            <tbody>{items.map((item) => <tr key={item.notice_id}>
              <td><input className="usa-checkbox__input" type="checkbox" aria-label={`Select ${item.title}`} checked={selected.has(item.notice_id)} onChange={() => toggle(item.notice_id)} /></td>
              <td><Link
                to={`/opportunities/${encodeURIComponent(item.notice_id)}?${new URLSearchParams({ return_to: '/saved', source_label: 'saved opportunities' })}`}
                state={{ returnTo: '/saved', sourceLabel: 'saved opportunities' }}
              >{item.title}</Link></td>
              <td>{item.notice_id}</td><td>{item.response_deadline || '—'}</td><td>{item.set_aside || '—'}</td><td>{item.naics_code || '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </>
  );
}
