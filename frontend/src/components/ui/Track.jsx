export default function Track({ value, cls = 'blue', small = false }) {
  return (
    <div className={`track${small ? ' sm' : ''}`}>
      <div className={`fill ${cls}`} style={{ width: value + '%' }} />
    </div>
  );
}