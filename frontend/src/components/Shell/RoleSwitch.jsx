import { useApp } from '../../context/AppContext';

export default function RoleSwitch({ id }) {
  const { role, switchRole } = useApp();
  return (
    <>
      <label className="sr" htmlFor={id}>Ver como</label>
      <select id={id} className="form-select bg-transparent text-white border-secondary" style={{ minHeight: 40, width: 'auto' }} value={role} onChange={(e) => switchRole(e.target.value)}>
        <option value="gerencia">Ver como: Gerencia</option>
        <option value="finanzas">Ver como: Finanzas</option>
        <option value="supervisor">Ver como: Supervisor</option>
        <option value="tecnico">Ver como: Técnico</option>
      </select>
    </>
  );
}
