export default function Table({ label, columns, min, head, children, style }) {
  return (
    <div className="tbl-wrap">
      <div className="tbl" role="table" aria-label={label} style={{ '--cols': columns, minWidth: min, ...style }}>
        <div className="trow thead" role="row">
          {head.map((h) => (
            <div key={h} role="columnheader">{h}</div>
          ))}
        </div>
        {children}
      </div>
    </div>
  );
}