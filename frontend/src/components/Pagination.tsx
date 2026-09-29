import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';

interface Props {
  page: number;
  hasNext: boolean;
  totalPages?: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, hasNext, totalPages, onChange }: Props) {
  const [targetPage, setTargetPage] = useState(String(page));
  useEffect(() => setTargetPage(String(page)), [page]);
  const pages = totalPages === undefined ? [] : [...new Set([
    1,
    totalPages,
    ...Array.from({ length: 5 }, (_, index) => page - 2 + index),
  ])].filter((value) => value >= 1 && value <= totalPages).sort((a, b) => a - b);

  function jump(event: FormEvent) {
    event.preventDefault();
    const requested = Number(targetPage);
    if (totalPages !== undefined && Number.isSafeInteger(requested)) {
      const next = Math.max(1, Math.min(requested, totalPages));
      setTargetPage(String(next));
      if (next !== page) onChange(next);
    }
  }

  return (
    <nav aria-label="Results pages" className="pager">
      <button className="usa-button usa-button--outline" type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </button>
      {totalPages === undefined ? <span aria-current="page">Page {page}</span> : <>
        <div className="pager__pages" aria-label="Page numbers">
          {pages.map((value, index) => <span key={value}>
            {index > 0 && value - pages[index - 1] > 1 && <span className="pager__ellipsis" aria-hidden="true">…</span>}
            <button className={`usa-button ${value === page ? '' : 'usa-button--outline'}`} type="button" aria-label={`Page ${value}`} aria-current={value === page ? 'page' : undefined} disabled={value === page} onClick={() => onChange(value)}>{value}</button>
          </span>)}
        </div>
        <form className="pager__jump" onSubmit={jump}>
          <label htmlFor="results-page-jump">Page {page} of {totalPages}. Go to</label>
          <input className="usa-input" id="results-page-jump" type="number" min="1" max={totalPages} value={targetPage} onChange={(event) => setTargetPage(event.target.value)} />
          <button className="usa-button usa-button--outline" type="submit">Go</button>
        </form>
      </>}
      <button className="usa-button usa-button--outline" type="button" disabled={!hasNext || (totalPages !== undefined && page >= totalPages)} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}
