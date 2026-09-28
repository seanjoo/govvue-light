import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type Month = { month: string; total_usd: number; estimated: boolean; services: { name: string; amount_usd: number }[] };

export default function AdminCosts() {
  const [months, setMonths] = useState<Month[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api<{ months: Month[] }>('/admin/costs').then((result) => setMonths(result.months))
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load costs'))
      .finally(() => setLoading(false));
  }, []);
  return <>
    <div className="page-header"><div className="page-pretitle">AWS Cost Explorer</div><h1 className="page-title">Account costs</h1></div>
    <p className="text-secondary mt-3">These are workshop account totals, not GovVue-only charges. Cost Explorer data may lag and the current month is estimated.</p>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {loading && <p>Loading costs…</p>}
    <div className="row row-cards">
      {months.map((month) => <div className="col-md-6" key={month.month}><div className="card">
        <div className="card-header"><h2 className="card-title">{month.month}{month.estimated ? ' (estimated)' : ''}</h2></div>
        <div className="card-body"><div className="h1">${month.total_usd.toFixed(2)}</div></div>
        <div className="table-responsive"><table className="table card-table"><thead><tr><th>Service</th><th>USD</th></tr></thead><tbody>
          {month.services.filter((item) => item.amount_usd > 0.005).map((service) => <tr key={service.name}><td>{service.name}</td><td>${service.amount_usd.toFixed(2)}</td></tr>)}
        </tbody></table></div>
      </div></div>)}
    </div>
  </>;
}
