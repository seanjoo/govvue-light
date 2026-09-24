import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import SavedSearchCriteria from '../components/SavedSearchCriteria';
import { api } from '../lib/api';
import type { SavedSearch } from '../types';

export default function SavedEntitySearchesPage() {
  const [items, setItems] = useState<SavedSearch[]>([]);
  const [error, setError] = useState('');

  function load() {
    api<{ items: SavedSearch[] }>('/saved-entity-searches')
      .then((response) => setItems(response.items))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load saved entity searches'));
  }

  useEffect(load, []);

  async function remove(id: string) {
    if (!window.confirm('Delete this saved entity search?')) return;
    try {
      await api(`/saved-entity-searches/${id}`, { method: 'DELETE' });
      load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete saved entity search');
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">Reusable entity filters</p><h1>Saved entity searches</h1></div>
        <Link className="usa-button usa-button--outline" to="/entities">New entity search</Link>
      </div>
      {error && <div className="usa-alert usa-alert--error margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
      <div className="saved-search-grid">
        {items.length ? items.map((item) => (
          <article className="saved-search-card" key={item.id}>
            <h2>{item.name}</h2>
            <SavedSearchCriteria criteria={item.criteria} emptyLabel="Active registered entities" />
            <div>
              <Link className="usa-button" to={`/entities?${new URLSearchParams(item.criteria)}`}>Run search</Link>
              <button className="usa-button usa-button--unstyled" type="button" onClick={() => remove(item.id)}>Delete</button>
            </div>
          </article>
        )) : <div className="empty-state"><h2>No saved entity searches</h2><p>Save filters from Entity Search to reuse them here.</p><Link className="usa-button" to="/entities">Search entities</Link></div>}
      </div>
    </>
  );
}
