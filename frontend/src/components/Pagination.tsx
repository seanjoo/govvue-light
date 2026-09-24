interface Props {
  page: number;
  hasNext: boolean;
  onChange: (page: number) => void;
}

export default function Pagination({ page, hasNext, onChange }: Props) {
  return (
    <nav aria-label="Results pages" className="pager">
      <button className="usa-button usa-button--outline" type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </button>
      <span aria-current="page">Page {page}</span>
      <button className="usa-button usa-button--outline" type="button" disabled={!hasNext} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}
