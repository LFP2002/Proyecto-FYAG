import { useApp } from '../context/AppContext';
import { Chip, Icon, PageHead } from '../components/ui';

export default function Alertas() {
  const { alertasAll, obrasC, markAtendida } = useApp();
  return (
    <section>
      <PageHead title="Alertas de desviación" sub="Se genera cuando el costo acumulado supera el avance en más de 10 puntos." />
      <div className="card-fyag">
        {alertasAll.length === 0 && <p className="fyag-empty">No hay alertas activas.</p>}
        {alertasAll.map((a) => (
          <div key={a.id} className="li">
            <div className="d-flex gap-2">
              <Icon d="M12 3l10 18H2zM12 10v5M12 18h.01" className="text-danger mt-1" />
              <div><strong>{a.id} · {a.cliente}</strong><div className="feed-d">{a.msg}</div></div>
            </div>
            <div className="acts">
              <Chip cls={a.atendida ? 'green' : 'red'}>{a.atendida ? 'Atendida' : 'Pendiente'}</Chip>
              {!a.atendida && <button className="btn btn-sm btn-outline-secondary" onClick={() => markAtendida(obrasC.find((o) => o.id === a.id))}>Marcar atendida</button>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}