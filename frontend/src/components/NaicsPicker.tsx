import { useEffect, useMemo, useRef, useState } from 'react';
import InfoTip from './InfoTip';

interface NaicsRecord {
  code: string;
  title: string;
  parent: string | null;
}

interface NaicsNode extends NaicsRecord {
  children: NaicsNode[];
  leafCount: number;
}

interface NaicsCatalogData {
  roots: NaicsNode[];
  leaves: NaicsRecord[];
  recordByCode: Map<string, NaicsRecord>;
}

let catalogPromise: Promise<NaicsCatalogData> | null = null;

function buildCatalog(records: NaicsRecord[]): NaicsCatalogData {
  const recordByCode = new Map(records.map((record) => [record.code, record]));
  const nodes = new Map<string, NaicsNode>(
    records.map((record) => [record.code, { ...record, children: [], leafCount: 0 }]),
  );
  const roots: NaicsNode[] = [];
  for (const node of nodes.values()) {
    const parent = node.parent ? nodes.get(node.parent) : undefined;
    if (parent) parent.children.push(node); else roots.push(node);
  }
  function countLeaves(node: NaicsNode): number {
    node.leafCount = node.code.length === 6
      ? 1
      : node.children.reduce((total, child) => total + countLeaves(child), 0);
    return node.leafCount;
  }
  roots.forEach(countLeaves);
  return {
    roots,
    leaves: records.filter((record) => record.code.length === 6),
    recordByCode,
  };
}

function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = import('../data/naics-2022.json').then((module) =>
      buildCatalog(module.default.records as NaicsRecord[]),
    );
  }
  return catalogPromise;
}

function breadcrumb(record: NaicsRecord, recordByCode: Map<string, NaicsRecord>) {
  const codes: string[] = [];
  let current: NaicsRecord | undefined = record;
  while (current) {
    codes.unshift(current.code);
    current = current.parent ? recordByCode.get(current.parent) : undefined;
  }
  return codes.join(' › ');
}

export default function NaicsPicker({
  id,
  value,
  update,
  maxSelections = 12,
}: {
  id: string;
  value: string;
  update: (value: string) => void;
  maxSelections?: number;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [data, setData] = useState<NaicsCatalogData | null>(null);
  const [draftSelected, setDraftSelected] = useState<string[]>([]);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selected = value.split(',').map((item) => item.trim()).filter(Boolean);
  const draftSelectedSet = new Set(draftSelected);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matches = useMemo(() => {
    if (!normalizedQuery || !data) return [];
    const terms = normalizedQuery.split(/\s+/);
    return data.leaves.filter((record) => {
      const searchable = `${record.code} ${record.title}`.toLocaleLowerCase();
      return terms.every((term) => searchable.includes(term));
    }).slice(0, 100);
  }, [data, normalizedQuery]);

  useEffect(() => {
    if (!open && selected.length === 0) return;
    let active = true;
    loadCatalog().then((loaded) => {
      if (active) setData(loaded);
    });
    return () => { active = false; };
  }, [open, selected.length]);

  useEffect(() => {
    if (!open || !dialogRef.current || dialogRef.current.open) return;
    dialogRef.current.showModal();
  }, [open]);

  function openPicker() {
    setDraftSelected(selected);
    setQuery('');
    setOpen(true);
  }

  function closePicker() {
    dialogRef.current?.close();
  }

  function toggleDraft(code: string) {
    const next = new Set(draftSelectedSet);
    if (next.has(code)) next.delete(code);
    else if (next.size < maxSelections) next.add(code);
    setDraftSelected([...next].sort());
  }

  function applySelection() {
    update([...draftSelected].sort().join(','));
    closePicker();
  }

  function removeSelected(code: string) {
    update(selected.filter((item) => item !== code).join(','));
  }

  const atLimit = draftSelected.length >= maxSelections;
  return (
    <div className="tablet:grid-col-8 naics-picker">
      <div className="naics-picker__heading">
        <div className="field-label">
          <span className="usa-label" id={`${id}-label`}>NAICS codes</span>
          <InfoTip text="Browse the official 2022 hierarchy or search by code or industry title. Only six-digit industries can be selected." label="About the NAICS picker" />
        </div>
        {selected.length > 0 && (
          <button className="usa-button usa-button--unstyled" type="button" onClick={() => update('')}>Clear all</button>
        )}
      </div>
      <button
        className="usa-button usa-button--outline naics-picker__toggle"
        type="button"
        ref={triggerRef}
        aria-haspopup="dialog"
        onClick={openPicker}
      >
        {selected.length ? `Edit ${selected.length} selected NAICS code${selected.length === 1 ? '' : 's'}` : 'Choose NAICS codes'}
      </button>
      {selected.length > 0 && (
        <ul className="naics-picker__selected" aria-label="Selected NAICS codes">
          {selected.map((code) => (
            <li key={code}>
              <span><strong>{code}</strong> {data?.recordByCode.get(code)?.title || (data ? 'Unknown NAICS code' : 'Loading industry…')}</span>
              <button type="button" aria-label={`Remove NAICS ${code}`} onClick={() => removeSelected(code)}>×</button>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <dialog
          className="naics-dialog"
          ref={dialogRef}
          aria-labelledby={`${id}-dialog-title`}
          onClose={() => {
            setOpen(false);
            triggerRef.current?.focus();
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget) closePicker();
          }}
        >
          <div className="naics-dialog__content">
            <header className="naics-dialog__header">
              <div><p className="page-kicker">2022 NAICS hierarchy</p><h2 id={`${id}-dialog-title`}>Choose NAICS codes</h2></div>
              <button className="naics-dialog__close" type="button" aria-label="Close NAICS picker" onClick={closePicker}>×</button>
            </header>
            <div className="naics-dialog__body">
              <label className="usa-label" htmlFor={`${id}-search`}>Find an industry</label>
              <div className="field-label">
                <span className="usa-hint" id={`${id}-search-hint`}>Search by six-digit code or words in the industry title.</span>
                <InfoTip text="Parent categories organize the catalog but are not sent to SAM.gov. Select individual six-digit industries." />
              </div>
              <input
                className="usa-input maxw-none"
                id={`${id}-search`}
                type="search"
                value={query}
                autoFocus
                aria-describedby={`${id}-search-hint`}
                onChange={(event) => setQuery(event.target.value)}
              />
              {atLimit && <p className="usa-error-message">Selection limit reached ({maxSelections}). Remove a code to choose another.</p>}
              {!data ? (
                <p>Loading the NAICS catalog…</p>
              ) : normalizedQuery ? (
                <div className="naics-picker__matches">
                  <p className="usa-hint">{matches.length ? `${matches.length}${matches.length === 100 ? '+' : ''} matching industries` : 'No matching industries'}</p>
                  {matches.map((record) => (
                    <NaicsChoice key={record.code} id={id} record={record} checked={draftSelectedSet.has(record.code)} disabled={atLimit && !draftSelectedSet.has(record.code)} toggle={toggleDraft} recordByCode={data.recordByCode} />
                  ))}
                </div>
              ) : (
                <div className="naics-picker__tree" role="tree" aria-label="NAICS industry hierarchy">
                  {data.roots.map((node) => (
                    <NaicsTreeNode key={node.code} id={id} node={node} selected={draftSelectedSet} atLimit={atLimit} toggle={toggleDraft} />
                  ))}
                </div>
              )}
            </div>
            <footer className="naics-dialog__footer">
              <span>{draftSelected.length} of {maxSelections} selected</span>
              <div>
                {draftSelected.length > 0 && <button className="usa-button usa-button--unstyled" type="button" onClick={() => setDraftSelected([])}>Clear all</button>}
                <button className="usa-button usa-button--outline" type="button" onClick={closePicker}>Cancel</button>
                <button className="usa-button" type="button" onClick={applySelection}>Apply selection</button>
              </div>
            </footer>
          </div>
        </dialog>
      )}
    </div>
  );
}

function NaicsTreeNode({
  id,
  node,
  selected,
  atLimit,
  toggle,
}: {
  id: string;
  node: NaicsNode;
  selected: Set<string>;
  atLimit: boolean;
  toggle: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (node.code.length === 6) {
    return <NaicsChoice id={id} record={node} checked={selected.has(node.code)} disabled={atLimit && !selected.has(node.code)} toggle={toggle} />;
  }
  return (
    <details open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)} role="treeitem">
      <summary><strong>{node.code}</strong> {node.title} <span>{node.leafCount.toLocaleString()} industries</span></summary>
      {expanded && (
        <div className="naics-picker__children" role="group">
          {node.children.map((child) => (
            <NaicsTreeNode key={child.code} id={id} node={child} selected={selected} atLimit={atLimit} toggle={toggle} />
          ))}
        </div>
      )}
    </details>
  );
}

function NaicsChoice({
  id,
  record,
  checked,
  disabled,
  toggle,
  recordByCode,
}: {
  id: string;
  record: NaicsRecord;
  checked: boolean;
  disabled: boolean;
  toggle: (code: string) => void;
  recordByCode?: Map<string, NaicsRecord>;
}) {
  const inputId = `${id}-naics-${record.code}`;
  return (
    <div className="usa-checkbox naics-picker__choice" role={recordByCode ? undefined : 'treeitem'}>
      <input className="usa-checkbox__input" id={inputId} type="checkbox" checked={checked} disabled={disabled} onChange={() => toggle(record.code)} />
      <label className="usa-checkbox__label" htmlFor={inputId}>
        <strong>{record.code}</strong> {record.title}
        {recordByCode && <span>{breadcrumb(record, recordByCode)}</span>}
      </label>
    </div>
  );
}
