import { useApp } from '../../context/AppContext';

export default function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div className={`fyag-toast${toast.kind !== 'ok' ? ' ' + toast.kind : ''}`} role="status">
      {toast.msg}
    </div>
  );
}