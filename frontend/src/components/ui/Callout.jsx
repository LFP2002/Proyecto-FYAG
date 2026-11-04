import Icon from './Icon';

export default function Callout({ warn, children }) {
  return (
    <div className={`callout${warn ? ' warn' : ''}`}>
      <Icon d={warn
        ? 'M12 3l10 18H2zM12 10v5M12 18h.01'
        : 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 11v6M12 7.5h.01'} />
      <span>{children}</span>
    </div>
  );
}