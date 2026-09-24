import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import EntityCard from '../components/EntityCard';
import { api } from '../lib/api';
import type { Entity } from '../types';

export default function SavedEntitiesPage() {
  const [items, setItems] = useState<Entity[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');

  function load() {
    api<{ items: Entity[] }>('/saved-entities')
      .then((result) => setItems(result.items))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load saved entities'));
  }
  useEffect(load, []);

  function select(uei: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(uei); else next.delete(uei);
      return next;
    });
  }

  async function removeSelected() {
    if (!selected.size || !window.confirm(`Remove ${selected.size} saved entit${selected.size === 1 ? 'y' : 'ies'}?`)) return;
    try {
      await api('/saved-entities', { method: 'DELETE', body: JSON.stringify({ ueis: [...selected] }) });
      setSelected(new Set());
      load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to remove saved entities');
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">Your entity watchlist</p><h1>Saved entities</h1></div>
        <button className="usa-button usa-button--secondary" type="button" disabled={!selected.size} onClick={removeSelected}>Remove selected</button>
      </div>
      {error && <div className="usa-alert usa-alert--error margin-bottom-3"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
      {!items.length ? (
        <div className="empty-state"><h2>No saved entities</h2><p>Save an entity from entity search to keep it here.</p><Link className="usa-button" to="/entities">Search entities</Link></div>
      ) : items.map((entity) => <EntityCard key={entity.uei} entity={entity} selected={selected.has(entity.uei)} onSelect={select} returnTo="/saved-entities" sourceLabel="saved entities" />)}
    </>
  );
}
