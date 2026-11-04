import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { Icon } from './ui';

// Usuarios de prueba mientras se conecta el backend
const DEMO_USERS = {
  gerencia: { email: 'gerencia@fyag.cl', pass: 'demo1234', hint: 'Dashboard, rentabilidad, aprobación de presupuestos y reportes ejecutivos.' },
  finanzas: { email: 'finanzas@fyag.cl', pass: 'demo1234', hint: 'Clientes, presupuestos, estados de pago y cobranza. No aprueba presupuestos.' },
  supervisor: { email: 'supervisor@fyag.cl', pass: 'demo1234', hint: 'Crea obras, asigna técnicos, registra costos y actualiza estados.' },
  tecnico: { email: 'ltorres@fyag.cl', pass: 'demo1234', hint: 'Solo sus obras asignadas y el registro de avances en terreno (vista móvil).' },
};

export default function Login() {
  const { login } = useApp();
  
  // Estado local para el formulario
  const [role, setRole] = useState('gerencia');
  const [email, setEmail] = useState(DEMO_USERS['gerencia'].email);
  const [password, setPassword] = useState(DEMO_USERS['gerencia'].pass);

  // Cuando cambia el selector de perfil, autocompletamos los datos de prueba
  const handleRoleChange = (e) => {
    const newRole = e.target.value;
    setRole(newRole);
    setEmail(DEMO_USERS[newRole].email);
    setPassword(DEMO_USERS[newRole].pass);
  };

  // Al enviar el formulario
  const handleSubmit = (e) => {
    e.preventDefault();
    // Aquí a futuro irá la llamada a la API (api.login)
    // Por ahora, solo le decimos al AppContext que inicie sesión con el rol elegido
    login(role); 
  };

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" className="logo-l" />
        <h1 className="login-title">FYAG</h1>
        <p className="login-sub">Sistema de Gestión de Obras y Presupuestos</p>
        
        <label htmlFor="f-role">Perfil de prueba</label>
        <select id="f-role" className="form-select" value={role} onChange={handleRoleChange}>
          <option value="gerencia">Administrador General / Gerencia</option>
          <option value="finanzas">Administrativo / Finanzas</option>
          <option value="supervisor">Supervisor de Obras</option>
          <option value="tecnico">Técnico</option>
        </select>

        <label htmlFor="f-user">Usuario</label>
        <input id="f-user" className="form-control" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        
        <label htmlFor="f-pass">Contraseña</label>
        <input id="f-pass" className="form-control" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        
        <p className="hint mt-2">{DEMO_USERS[role].hint}</p>
        
        <button type="submit" className="btn btn-fyag-primary w-100 mt-3">Ingresar</button>
        <p className="login-foot">Demo Mockup · Proyecto Beta FYAG</p>
      </form>
    </main>
  );
}