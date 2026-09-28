import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type Index = { status: string; source_date?: string; snapshot_source_date?: string; record_count?: number; published_at?: string; monthly_source_date?: string };
type Job = { id: string; dataset: string; status: string; started_at: string; finished_at: string; logs_url: string };
type Validation = { kind: string; total_records: number; source_date: string; duration_ms: number };
type Overview = {
  indexes: { opportunities: Index; entities: Index };
  jobs: Job[];
  queue: { waiting: number; running: number; dead_letters: number };
  schedules: Record<string, { state: string; expression: string; timezone: string }>;
  local_search_enabled: boolean;
  checked_at: string;
};

const jobNames: Record<string, string> = {
  'opportunity-daily': 'Opportunity full snapshot',
  'opportunity-poll': 'Opportunity recent-posted poll',
  'entity-monthly': 'Entity monthly baseline',
  'entity-daily': 'Entity daily update',
};

export default function AdminDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [running, setRunning] = useState('');
  const [validating, setValidating] = useState('');
  const [validations, setValidations] = useState<Record<string, Validation>>({});

  async function load() {
    try { setOverview(await api<Overview>('/admin/ingestion')); setError(''); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not load operations'); }
  }
  useEffect(() => { void load(); }, []);

  async function run(dataset: string) {
    if (!window.confirm(`Queue ${jobNames[dataset]} now? This may use SAM.gov API calls and AWS build minutes.`)) return;
    setRunning(dataset); setError(''); setNotice('');
    try {
      await api('/admin/ingestion/run', { method: 'POST', body: JSON.stringify({ dataset }) });
      setNotice(`${jobNames[dataset]} queued. Refresh to see build status.`);
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not queue job'); }
    finally { setRunning(''); }
  }

  async function validate(kind: 'opportunities' | 'entities') {
    setValidating(kind); setError('');
    try {
      const result = await api<Validation>('/admin/ingestion/validate', {
        method: 'POST', body: JSON.stringify({ kind }),
      });
      setValidations((current) => ({ ...current, [kind]: result }));
    } catch (caught) { setError(caught instanceof Error ? caught.message : `Could not validate ${kind} index`); }
    finally { setValidating(''); }
  }

  return <>
    <div className="page-header d-print-none"><div className="row align-items-center">
      <div className="col"><div className="page-pretitle">GovVue Light administration</div><h1 className="page-title">Data operations</h1></div>
      <div className="col-auto ms-auto"><button className="btn btn-outline-primary" onClick={() => void load()}>Refresh</button></div>
    </div></div>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {notice && <div className="alert alert-success" role="status">{notice}</div>}
    <div className="row row-cards mt-3">
      {(['opportunities', 'entities'] as const).map((kind) => {
        const index = overview?.indexes[kind];
        return <div className="col-md-6" key={kind}><div className="card"><div className="card-body">
          <div className="subheader">{kind} index</div>
          <div className="h2 mb-1">{index?.record_count?.toLocaleString() ?? 'Not published'}</div>
          <p className="text-secondary mb-0">Source date: {index?.source_date || '—'} · Published: {index?.published_at ? new Date(index.published_at).toLocaleString() : '—'}</p>
          {index?.snapshot_source_date && <p className="text-secondary mb-0">Full snapshot: {index.snapshot_source_date}</p>}
          {index?.monthly_source_date && <p className="text-secondary mb-0">Monthly baseline: {index.monthly_source_date}</p>}
          <button className="btn btn-sm btn-outline-primary mt-3" disabled={!index || !!validating} onClick={() => void validate(kind)}>
            {validating === kind ? 'Testing…' : 'Test local search'}
          </button>
          {validations[kind] && <p className="text-success mt-2 mb-0" role="status">
            {validations[kind].total_records.toLocaleString()} sample matches · {validations[kind].duration_ms.toLocaleString()} ms
          </p>}
        </div></div></div>;
      })}
    </div>
    <div className="row row-cards mt-2"><div className="col-12"><div className="card"><div className="card-header"><h2 className="card-title">Schedules and manual runs</h2></div>
      <div className="table-responsive"><table className="table table-vcenter card-table"><thead><tr><th>Job</th><th>Schedule</th><th>State</th><th></th></tr></thead><tbody>
        {Object.entries(jobNames).map(([dataset, label]) => <tr key={dataset}><td>{label}</td>
          <td><code>{overview?.schedules[dataset]?.expression ?? '—'}</code><span className="text-secondary ms-2">{overview?.schedules[dataset]?.timezone}</span></td>
          <td>{overview?.schedules[dataset]?.state ?? '—'}</td>
          <td><button className="btn btn-sm btn-outline-primary" disabled={!!running} onClick={() => void run(dataset)}>{running === dataset ? 'Queuing…' : 'Run now'}</button></td></tr>)}
        <tr><td>Ingestion health alert</td>
          <td><code>{overview?.schedules['ingest-health']?.expression ?? '—'}</code><span className="text-secondary ms-2">{overview?.schedules['ingest-health']?.timezone}</span></td>
          <td>{overview?.schedules['ingest-health']?.state ?? '—'}</td><td className="text-secondary">Emails on failure</td></tr>
      </tbody></table></div>
      <div className="card-footer text-secondary">Change schedules in the environment YAML, sync SSM, and deploy infrastructure. Enable them only after validating both baselines.</div>
    </div></div></div>
    <div className="row row-cards mt-2"><div className="col-12"><div className="card"><div className="card-header"><h2 className="card-title">Recent builds</h2></div>
      <div className="card-body text-secondary">Local search: {overview?.local_search_enabled ? 'enabled' : 'disabled'} · Queue: {overview?.queue.waiting ?? '—'} waiting, {overview?.queue.running ?? '—'} in progress, {overview?.queue.dead_letters ?? '—'} dead letters.</div>
      <div className="table-responsive"><table className="table table-vcenter card-table"><thead><tr><th>Started</th><th>Dataset</th><th>Status</th><th>Logs</th></tr></thead><tbody>
        {overview?.jobs.map((job) => <tr key={job.id}><td>{job.started_at ? new Date(job.started_at).toLocaleString() : '—'}</td><td>{jobNames[job.dataset] ?? job.dataset}</td><td>{job.status}</td><td>{job.logs_url && <a href={job.logs_url} target="_blank" rel="noreferrer">CloudWatch ↗</a>}</td></tr>)}
        {!overview?.jobs.length && <tr><td colSpan={4} className="text-secondary">No builds yet.</td></tr>}
      </tbody></table></div></div></div></div>
  </>;
}
