import { FormEvent, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import MultiSelectFilter, {
  NOTICE_TYPE_OPTIONS,
  SET_ASIDE_OPTIONS,
  STATE_OPTIONS,
} from '../components/MultiSelectFilter';
import NaicsPicker from '../components/NaicsPicker';
import InfoTip from '../components/InfoTip';
import { api } from '../lib/api';
import { createNotificationDraft, type NotificationDraft } from '../lib/notificationDraft';
import { runtimeConfig } from '../runtimeConfig';
import type { DailyNotification, SavedSearch } from '../types';

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
  response_deadline_from: '',
  response_deadline_to: '',
  open_deadlines_only: '',
};

export default function DailyNotificationsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const incomingDraft = (location.state as { notificationDraft?: NotificationDraft } | null)?.notificationDraft;
  const [items, setItems] = useState<DailyNotification[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [selectedSavedSearchId, setSelectedSavedSearchId] = useState('');
  const [formOpen, setFormOpen] = useState(Boolean(incomingDraft));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState(incomingDraft?.name || '');
  const [enabled, setEnabled] = useState(true);
  const [scheduleTime, setScheduleTime] = useState(runtimeConfig.dailyNotificationDefaultTime);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, ...incomingDraft?.criteria });
  const [error, setError] = useState('');
  const [message, setMessage] = useState(incomingDraft ? 'Search filters loaded. Review them, then create the notification.' : '');
  const [saving, setSaving] = useState(false);
  const [runningNow, setRunningNow] = useState(false);

  async function load() {
    try {
      const [notificationResponse, savedSearchResponse] = await Promise.all([
        api<{ items: DailyNotification[] }>('/daily-notifications'),
        api<{ items: SavedSearch[] }>('/saved-searches'),
      ]);
      setItems(notificationResponse.items);
      setSavedSearches(savedSearchResponse.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load daily notifications');
    }
  }

  useEffect(() => {
    load();
    if (incomingDraft) navigate(location.pathname, { replace: true, state: null });
  }, []);

  function updateFilter(key: string, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function reset() {
    setEditingId(null);
    setName('');
    setEnabled(true);
    setScheduleTime(runtimeConfig.dailyNotificationDefaultTime);
    setFilters({ ...EMPTY_FILTERS });
    setSelectedSavedSearchId('');
  }

  function openCreateForm() {
    reset();
    setError('');
    setMessage('');
    setFormOpen(true);
  }

  function closeForm() {
    reset();
    setFormOpen(false);
  }

  function loadSavedSearch() {
    const savedSearch = savedSearches.find((item) => item.id === selectedSavedSearchId);
    if (!savedSearch) return;
    const draft = createNotificationDraft(savedSearch.name, savedSearch.criteria);
    setEditingId(null);
    setName(draft.name);
    setEnabled(true);
    setScheduleTime(runtimeConfig.dailyNotificationDefaultTime);
    setFilters({ ...EMPTY_FILTERS, ...draft.criteria });
    setMessage(`Loaded saved search “${savedSearch.name}”. Review the filters, then create the notification.`);
    setError('');
  }

  function edit(item: DailyNotification) {
    setEditingId(item.id);
    setName(item.name);
    setEnabled(item.enabled);
    setScheduleTime(item.schedule_time || runtimeConfig.dailyNotificationDefaultTime);
    setFilters({ ...EMPTY_FILTERS, ...item.criteria });
    setMessage('');
    setFormOpen(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    const criteria = Object.fromEntries(Object.entries(filters).filter(([, value]) => value.trim()));
    try {
      const path = editingId ? `/daily-notifications/${editingId}` : '/daily-notifications';
      await api(path, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify({ name, enabled, schedule_time: scheduleTime, criteria }),
      });
      setMessage(editingId ? 'Daily notification updated.' : 'Daily notification created.');
      reset();
      setFormOpen(false);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save daily notification');
    } finally {
      setSaving(false);
    }
  }

  async function remove(item: DailyNotification) {
    if (!window.confirm(`Delete “${item.name}”? Historical runs will expire automatically.`)) return;
    try {
      await api(`/daily-notifications/${item.id}`, { method: 'DELETE' });
      if (editingId === item.id) closeForm();
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete daily notification');
    }
  }

  async function runNow() {
    setRunningNow(true);
    setError('');
    setMessage('');
    try {
      await api('/daily-notifications/run', { method: 'POST' });
      setMessage('Daily notification run queued. Results will appear on each notification page when processing completes.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to start daily notifications');
    } finally {
      setRunningNow(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">Daily email digest</p><h1>Daily notifications</h1></div>
        <div className="page-heading__actions">
          <button className="usa-button usa-button--outline" type="button" disabled={runningNow || !items.some((item) => item.enabled)} onClick={runNow}>{runningNow ? 'Starting…' : 'Run now'}</button>
          {!formOpen && <button className="usa-button" type="button" onClick={openCreateForm}>Create notification</button>}
        </div>
      </div>
      <p className="measure-6">Each enabled notification runs daily at its selected Eastern Time, filters the shared SAM.gov feed locally, and sends one email, including when no opportunities match.</p>
      {formOpen && <form className="search-panel notification-form" onSubmit={submit}>
        <div className="section-heading">
          <h2>{editingId ? 'Edit notification' : 'Create notification'}</h2>
          <button className="usa-button usa-button--unstyled" type="button" onClick={closeForm}>{editingId ? 'Cancel edit' : 'Cancel'}</button>
        </div>
        {!editingId && (
          <section className="notification-import" aria-labelledby="notification-import-heading">
            <div className="field-label">
              <h3 id="notification-import-heading">Start from a saved search</h3>
              <InfoTip text="Copies compatible filters into this form. Posted-date filters are omitted because each daily run uses the daily feed window." label="About importing a saved search" />
            </div>
            <div className="notification-import__controls">
              <label className="usa-sr-only" htmlFor="notification-saved-search">Saved search</label>
              <select className="usa-select maxw-none" id="notification-saved-search" value={selectedSavedSearchId} onChange={(event) => setSelectedSavedSearchId(event.target.value)}>
                <option value="">Select a saved search</option>
                {savedSearches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <button className="usa-button usa-button--outline" type="button" disabled={!selectedSavedSearchId} onClick={loadSavedSearch}>Use saved search</button>
            </div>
          </section>
        )}
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-4">
            <label className="usa-label" htmlFor="notification-name">Name</label>
            <input className="usa-input maxw-none" id="notification-name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="tablet:grid-col-4 notification-enabled">
            <div className="usa-checkbox">
              <input className="usa-checkbox__input" id="notification-enabled" type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
              <label className="usa-checkbox__label" htmlFor="notification-enabled">Send daily email</label>
            </div>
          </div>
          <div className="tablet:grid-col-4">
            <div className="field-label">
              <label className="usa-label" htmlFor="notification-schedule-time">Daily run time</label>
              <InfoTip text="Eastern Time. Scheduled notifications are dispatched within five minutes of this time." label="About daily run time" />
            </div>
            <input className="usa-input maxw-none" id="notification-schedule-time" type="time" required step={300} value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} />
          </div>
        </div>
        <div className="grid-row grid-gap">
          <Filter label="Title or keywords" name="title" value={filters.title} update={updateFilter} wide />
          <Filter label="Notice ID" name="notice_id" value={filters.notice_id} update={updateFilter} />
          <Filter label="Solicitation number" name="solicitation_number" value={filters.solicitation_number} update={updateFilter} />
          <Filter label="PSC / classification code" name="classification_code" value={filters.classification_code} update={updateFilter} hint="Separate multiple codes with commas." />
          <Filter label="Organization" name="organization_name" value={filters.organization_name} update={updateFilter} />
          <Filter label="Response due from" name="response_deadline_from" value={filters.response_deadline_from} update={updateFilter} type="date" />
          <Filter label="Response due to" name="response_deadline_to" value={filters.response_deadline_to} update={updateFilter} type="date" />
          <div className="tablet:grid-col-4 deadline-filter">
            <div className="usa-checkbox">
              <input
                className="usa-checkbox__input"
                id="notification-open-deadlines-only"
                type="checkbox"
                checked={filters.open_deadlines_only === 'true'}
                onChange={(event) => updateFilter('open_deadlines_only', event.target.checked ? 'true' : '')}
              />
              <label className="usa-checkbox__label" htmlFor="notification-open-deadlines-only">Exclude past response deadlines</label>
            </div>
            <InfoTip text="Uses the current date for each daily run. Opportunities without a response deadline are excluded." label="About excluding past response deadlines" />
          </div>
          <MultiSelectFilter id="notification-ptype" label="Notice type" value={filters.ptype} options={NOTICE_TYPE_OPTIONS} update={(value) => updateFilter('ptype', value)} />
          <MultiSelectFilter id="notification-set-aside" label="Set-aside" value={filters.set_aside} options={SET_ASIDE_OPTIONS} update={(value) => updateFilter('set_aside', value)} />
          <MultiSelectFilter id="notification-state" label="Place-of-performance state" value={filters.state} options={STATE_OPTIONS} update={(value) => updateFilter('state', value)} />
          <NaicsPicker id="notification" value={filters.naics_code} update={(value) => updateFilter('naics_code', value)} maxSelections={20} />
        </div>
        <p className="usa-hint margin-top-2">Multiple values within one filter use OR; different filters use AND. The posted-date window is always yesterday through today.</p>
        <button className="usa-button margin-top-2" type="submit" disabled={saving}>{saving ? 'Saving…' : editingId ? 'Update notification' : 'Create notification'}</button>
      </form>}

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}

      <section className="results-section">
        <h2>Your notifications</h2>
        <div className="saved-search-grid">
          {items.length ? items.map((item) => (
            <article className="saved-search-card" key={item.id}>
              <div className="notification-card-heading"><h3>{item.name}</h3><span className={`status-pill ${item.enabled ? 'status-pill--enabled' : ''}`}>{item.enabled ? 'Enabled' : 'Paused'}</span></div>
              <p>{describe(item.criteria)}</p>
              <p className="text-base">Schedule: {formatScheduleTime(item.schedule_time)} Eastern</p>
              <p className="text-base">Email: {item.recipient_email}</p>
              <div>
                <Link className="usa-button" to={`/notifications/${item.id}`}>View results</Link>
                <button className="usa-button usa-button--unstyled" type="button" onClick={() => edit(item)}>Edit</button>
                <button className="usa-button usa-button--unstyled text-secondary-dark" type="button" onClick={() => remove(item)}>Delete</button>
              </div>
            </article>
          )) : <p>No daily notifications yet.</p>}
        </div>
      </section>
    </>
  );
}

function Filter({ label, name, value, update, type = 'text', hint, wide = false }: { label: string; name: string; value: string; update: (name: string, value: string) => void; type?: string; hint?: string; wide?: boolean }) {
  const id = `notification-${name}`;
  return <div className={wide ? 'tablet:grid-col-8' : 'tablet:grid-col-4'}><div className="field-label"><label className="usa-label" htmlFor={id}>{label}</label>{hint && <InfoTip text={hint} label={`About ${label}`} />}</div><input className="usa-input maxw-none" id={id} type={type} value={value} onChange={(event) => update(name, event.target.value)} /></div>;
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

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-top-3`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
