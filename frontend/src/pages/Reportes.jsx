import { useApp } from '../context/AppContext';
import { fm, pctTxt } from '../utils/format';
import { PageHead } from '../components/ui';

const REPORTES = [
  { title: 'Reporte de obras', desc: 'Estado, avance y técnico responsable.', roles: ['gerencia'] },
  { title: 'Reporte de rentabilidad', desc: 'Presupuesto vs costo real y margen.', roles: ['gerencia'] },
  { title: 'Reporte de cobranza', desc: 'Estados de pago y monto cobrado.', roles: ['gerencia', 'finanzas'] }
];
const FORMATOS = ['PDF', 'Excel', 'CSV'];

export default function Reportes() {
  const { role, obrasC, flash } = useApp();
  return (
    <section>
      <PageHead title="Reportes" sub={role === 'gerencia' ? 'Reportes ejecutivos.' : 'Reporte de cobranza.'} />
      <div className="row g-3 mb-3">
        {REPORTES.filter((r) => r.roles.includes(role)).map((r) => (
          <div key={r.title} className="col-md-4">
            <div className="card-fyag h-100">
              <h2>{r.title}</h2>
              <p className="note mb-3">{r.desc}</p>
              <div className="d-flex flex-wrap gap-2">
                {FORMATOS.map((f) => <button key={f} className="btn btn-sm btn-outline-secondary" onClick={() => flash(`${r.title} (${f}) generado.`)}>Descargar {f}</button>)}
              </div>
            </div>
          </div>
        ))}
      </div>
      {role === 'gerencia' && (
        <div className="card-fyag">
          <h2>Rentabilidad por obra</h2>
          <div style={{ marginTop: 12 }}>
            {obrasC.filter((o) => o.presupuesto > 0).map((o) => {
              const p = (o.margen / o.presupuesto) * 100;
              return (
                <div key={o.id} className="pg">
                  <div className="pg-l"><span><strong>{o.id}</strong> · {o.cliente}</span><span><strong className={p >= 0 ? 'fyag-pos' : 'fyag-neg'}>{pctTxt(p)}</strong> · {fm(o.margen)}</span></div>
                  <div className="track"><div className="fill green" style={{ width: Math.max(0, Math.min(100, p)) + '%' }} /></div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}