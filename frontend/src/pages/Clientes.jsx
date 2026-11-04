import { useApp } from '../context/AppContext';
import { Icon, PageHead, Table } from '../components/ui';

export default function Clientes() {
  const { clientes, pres, obrasC, showCliForm, fCliNombre, fCliCiudad, fCliContacto, setField, saveCli } = useApp();
  return (
    <section>
      <PageHead title="Clientes" sub="Registro de clientes y su relación con presupuestos y obras.">
        <button className="btn btn-fyag-primary" onClick={() => setField('showCliForm', !showCliForm)}>
          <Icon d="M12 5v14M5 12h14" />Nuevo cliente
        </button>
      </PageHead>

      {showCliForm && (
        <div className="card-fyag">
          <h2>Nuevo cliente</h2>
          <div className="fgrid">
            <div><label htmlFor="f-cn">Nombre o razón social</label><input id="f-cn" className="form-control" value={fCliNombre} onChange={(e) => setField('fCliNombre', e.target.value)} /></div>
            <div><label htmlFor="f-cc">Ciudad</label><input id="f-cc" className="form-control" value={fCliCiudad} onChange={(e) => setField('fCliCiudad', e.target.value)} /></div>
            <div><label htmlFor="f-ct">Contacto</label><input id="f-ct" className="form-control" value={fCliContacto} onChange={(e) => setField('fCliContacto', e.target.value)} /></div>
          </div>
          <div className="actions mt-3">
            <button className="btn btn-fyag-primary" onClick={saveCli}>Guardar cliente</button>
            <button className="btn btn-outline-secondary" onClick={() => setField('showCliForm', false)}>Cancelar</button>
          </div>
        </div>
      )}

      <div className="card-fyag flush">
        <Table label="Clientes" min="760px" columns="1.6fr 1fr 1.2fr 110px 90px" head={['Cliente', 'Ciudad', 'Contacto', 'Presupuestos', 'Obras']}>
          {clientes.map((c) => (
            <div key={c.nombre} className="trow" role="row">
              <div role="cell"><strong>{c.nombre}</strong></div>
              <div role="cell">{c.ciudad}</div>
              <div role="cell">{c.contacto || '—'}</div>
              <div role="cell">{pres.filter((p) => p.cliente === c.nombre).length}</div>
              <div role="cell">{obrasC.filter((o) => o.cliente === c.nombre).length}</div>
            </div>
          ))}
        </Table>
      </div>
    </section>
  );
}