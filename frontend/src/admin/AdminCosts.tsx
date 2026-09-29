import { Fragment, useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';

type Service = { name: string; amount_usd: number };
type Month = { month: string; total_usd: number; estimated: boolean; services: Service[] };
type View = 'cards' | 'list';
type MonthSort = 'latest' | 'oldest' | 'cost-high' | 'cost-low';
type ServiceSort = 'cost-high' | 'cost-low' | 'name-asc' | 'name-desc';

function sortedMonths(months: Month[], sort: MonthSort): Month[] {
  return [...months].sort((left, right) => {
    if (sort === 'oldest') return left.month.localeCompare(right.month);
    if (sort === 'cost-high') return right.total_usd - left.total_usd || right.month.localeCompare(left.month);
    if (sort === 'cost-low') return left.total_usd - right.total_usd || right.month.localeCompare(left.month);
    return right.month.localeCompare(left.month);
  });
}

function sortedServices(services: Service[], sort: ServiceSort): Service[] {
  return services.filter((service) => Math.abs(service.amount_usd) > 0.005).sort((left, right) => {
    if (sort === 'cost-low') return left.amount_usd - right.amount_usd || left.name.localeCompare(right.name);
    if (sort === 'name-asc') return left.name.localeCompare(right.name);
    if (sort === 'name-desc') return right.name.localeCompare(left.name);
    return right.amount_usd - left.amount_usd || left.name.localeCompare(right.name);
  });
}

function usd(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
}

function ServiceBreakdown({ month, sort }: { month: Month; sort: ServiceSort }) {
  const services = sortedServices(month.services, sort);
  return <div className="table-responsive">
    <table className="table card-table mb-0">
      <caption className="visually-hidden">{month.month} costs by service</caption>
      <thead><tr><th scope="col">Service</th><th scope="col" className="text-end">Cost</th></tr></thead>
      <tbody>{services.length ? services.map((service) => <tr key={service.name}>
        <td>{service.name}</td><td className="text-end">{usd(service.amount_usd)}</td>
      </tr>) : <tr><td colSpan={2} className="text-secondary">No service charges to show.</td></tr>}</tbody>
    </table>
  </div>;
}

export default function AdminCosts() {
  const [months, setMonths] = useState<Month[]>([]);
  const [view, setView] = useState<View>('cards');
  const [monthSort, setMonthSort] = useState<MonthSort>('latest');
  const [serviceSort, setServiceSort] = useState<ServiceSort>('cost-high');
  const [expanded, setExpanded] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const orderedMonths = useMemo(() => sortedMonths(months, monthSort), [months, monthSort]);

  useEffect(() => {
    api<{ months: Month[] }>('/admin/costs').then((result) => setMonths(result.months))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load costs'))
      .finally(() => setLoading(false));
  }, []);

  function toggleBreakdown(month: string) {
    setExpanded((current) => current.includes(month)
      ? current.filter((value) => value !== month)
      : [...current, month]);
  }

  return <>
    <div className="page-header"><div className="page-pretitle">AWS Cost Explorer</div><h1 className="page-title">Account costs</h1></div>
    <p className="text-secondary mt-3">These are workshop account totals, not GovVue-only charges. Cost Explorer data may lag and the current month is estimated.</p>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {loading && <p>Loading costs…</p>}
    {!loading && !error && <>
      <div className="admin-cost-toolbar mb-3">
        <div className="btn-group" role="group" aria-label="Cost view">
          <button className={`btn ${view === 'cards' ? 'btn-primary' : 'btn-outline-primary'}`} type="button" aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Cards</button>
          <button className={`btn ${view === 'list' ? 'btn-primary' : 'btn-outline-primary'}`} type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>List</button>
        </div>
        <label>Sort months
          <select className="form-select" value={monthSort} onChange={(event) => setMonthSort(event.target.value as MonthSort)}>
            <option value="latest">Newest first</option><option value="oldest">Oldest first</option>
            <option value="cost-high">Highest total first</option><option value="cost-low">Lowest total first</option>
          </select>
        </label>
        <label>Sort services
          <select className="form-select" value={serviceSort} onChange={(event) => setServiceSort(event.target.value as ServiceSort)}>
            <option value="cost-high">Highest cost first</option><option value="cost-low">Lowest cost first</option>
            <option value="name-asc">Service A–Z</option><option value="name-desc">Service Z–A</option>
          </select>
        </label>
      </div>
      {!orderedMonths.length && <div className="alert alert-info">No account cost data is available yet.</div>}
      {view === 'cards' && <div className="row row-cards">
        {orderedMonths.map((month) => <div className="col-md-6" key={month.month}><div className="card">
          <div className="card-header"><h2 className="card-title">{month.month}{month.estimated ? ' (estimated)' : ''}</h2></div>
          <div className="card-body"><div className="h1">{usd(month.total_usd)}</div></div>
          <ServiceBreakdown month={month} sort={serviceSort} />
        </div></div>)}
      </div>}
      {view === 'list' && orderedMonths.length > 0 && <div className="card"><div className="table-responsive">
        <table className="table table-vcenter card-table mb-0">
          <thead><tr><th scope="col">Month</th><th scope="col" className="text-end">Total cost</th><th scope="col" className="w-1">Breakdown</th></tr></thead>
          <tbody>{orderedMonths.map((month) => <Fragment key={month.month}>
            <tr>
              <td>{month.month}{month.estimated && <span className="badge bg-blue-lt ms-2">Estimated</span>}</td>
              <td className="text-end fw-bold">{usd(month.total_usd)}</td>
              <td><button className="btn btn-outline-primary btn-sm" type="button" aria-expanded={expanded.includes(month.month)} onClick={() => toggleBreakdown(month.month)}>
                {expanded.includes(month.month) ? 'Hide breakdown' : 'View breakdown'}
              </button></td>
            </tr>
            {expanded.includes(month.month) && <tr><td colSpan={3} className="p-0"><ServiceBreakdown month={month} sort={serviceSort} /></td></tr>}
          </Fragment>)}</tbody>
        </table>
      </div></div>}
    </>}
  </>;
}
