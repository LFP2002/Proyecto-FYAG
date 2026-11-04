import { useApp } from '../context/AppContext';
import { MATRIX } from '../data/constants';
import { Chip, PageHead, Table } from '../components/ui';

export default function Usuarios() {
  const { usuarios, toggleUser } = useApp();
  return (
    <section>
      <PageHead title="Usuarios y roles" sub="Alta, baja y asignación de perfiles." />
      <div className="card-fyag flush mb-3">
        <Table label="Usuarios" min="780px" columns="1.3fr 1.4fr 1.6fr 120px 130px" head={['Nombre', 'Correo', 'Perfil', 'Estado', 'Acción']}>
          {usuarios.map((u, i) => (
            <div key={u.email} className="trow" role="row">
              <div role="cell"><strong>{u.name}</strong></div>
              <div role="cell">{u.email}</div>
              <div role="cell">{u.rol}</div>
              <div role="cell"><Chip cls={u.activo ? 'green' : 'gray'}>{u.activo ? 'Activo' : 'Desactivado'}</Chip></div>
              <div role="cell"><button className="btn btn-sm btn-outline-secondary" disabled={i === 0} onClick={() => toggleUser(i)}>{u.activo ? 'Desactivar' : 'Activar'}</button></div>
            </div>
          ))}
        </Table>
      </div>
      <div className="card-fyag flush">
        <div className="card-h"><h2>Matriz de permisos</h2></div>
        <Table label="Matriz" min="780px" columns="1.4fr repeat(4, 1fr)" head={['Módulo', 'Gerencia', 'Finanzas', 'Supervisor', 'Técnico']} style={{ marginTop: 14 }}>
          {MATRIX.map((r) => (
            <div key={r[0]} className="trow" role="row">
              <div role="cell"><strong>{r[0]}</strong></div>
              {r.slice(1).map((t, i) => <div key={i} role="cell" className={t === '—' ? 'fyag-muted' : ''}>{t}</div>)}
            </div>
          ))}
        </Table>
      </div>
    </section>
  );
}