export default function Feed({ g }) {
  return (
    <div className="feed">
      <span className={`dot ${g.kind}`} />
      <div>
        <div className="feed-t">{g.title}</div>
        <div className="feed-d">{g.detail}</div>
      </div>
      <span className="feed-w">{g.when}</span>
    </div>
  );
}