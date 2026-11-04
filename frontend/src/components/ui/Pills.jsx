export default function Pills({ items }) {
  return (
    <div className="pills">
      {items.map((i) => (
        <button key={i.key} type="button" className={`pill${i.on ? ' on' : ''}`} onClick={i.pick}>
          {i.label}
        </button>
      ))}
    </div>
  );
}