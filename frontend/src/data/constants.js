export const UMBRAL = 5000000;
export const UMBRAL_ALERTA = 10;
// Los prototipos de negocio no se montan hasta integrar sus API.
export const TEC = '';

export const ROLES = {
  GERENCIA: { short: 'Gerencia' },
  ADMINISTRATIVO_FINANZAS: { short: 'Administrativo / Finanzas' },
  SUPERVISOR_OBRAS: { short: 'Supervisor de Obras' },
  TECNICO: { short: 'Técnico' }
};

export const ROLE_NOTE = {
  GERENCIA: 'Los módulos de negocio están pendientes de integración con sus API.',
  ADMINISTRATIVO_FINANZAS: 'Los módulos de negocio están pendientes de integración con sus API.',
  SUPERVISOR_OBRAS: 'Los módulos de negocio están pendientes de integración con sus API.'
};

export const NAV = {
  GERENCIA: ['dashboard', 'presupuestos', 'obras', 'cobranzas', 'alertas', 'reportes', 'usuarios'],
  ADMINISTRATIVO_FINANZAS: ['clientes', 'presupuestos', 'obras', 'cobranzas', 'reportes'],
  SUPERVISOR_OBRAS: ['obras', 'alertas'],
  TECNICO: ['obras']
};

export const DEFMOD = { GERENCIA: 'dashboard', ADMINISTRATIVO_FINANZAS: 'presupuestos', SUPERVISOR_OBRAS: 'obras', TECNICO: 'obras' };

export const MODS = {
  dashboard: { label: 'Dashboard', icon: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z' },
  clientes: { label: 'Clientes', icon: 'M16 20v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 20v-1a4 4 0 0 0-3-3.9M15 4.2a3.5 3.5 0 0 1 0 6.6' },
  presupuestos: { label: 'Presupuestos', icon: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6' },
  obras: { label: 'Obras', icon: 'M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6' },
  cobranzas: { label: 'Cobranzas', icon: 'M3 6h18v12H3zM3 10h18M7 15h3' },
  alertas: { label: 'Alertas', icon: 'M12 3l10 18H2zM12 10v5M12 18h.01' },
  reportes: { label: 'Reportes', icon: 'M5 20V10M12 20V4M19 20v-7M3 20h18' },
  usuarios: { label: 'Usuarios y roles', icon: 'M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6zM9.5 12l2 2 3.5-4' }
};

export const PRE_E = {
  BORRADOR: ['Borrador', 'gray'],
  PENDIENTE_GERENCIA: ['Pendiente de Gerencia', 'amber'],
  APROBADO_GERENCIA: ['Aprobado por Gerencia', 'blue'],
  RECHAZADO_GERENCIA: ['Rechazado por Gerencia', 'red'],
  ENVIADO_CLIENTE: ['Enviado al cliente', 'blue'],
  APROBADO_CLIENTE: ['Aceptado por el cliente', 'green'],
  RECHAZADO_CLIENTE: ['Rechazado por el cliente', 'red'],
  ANULADO: ['Anulado', 'gray']
};

export const OBRA_CHIP = { 'En proceso': 'green', Finalizada: 'amber', Suspendida: 'red', Cancelada: 'gray' };
export const PAGO_CHIP = { Facturado: 'amber', Pagado: 'green', Anulado: 'gray' };

export const MATRIX = [
  ['Dashboard e indicadores', 'Total', '—', '—', '—'],
  ['Clientes', '—', 'Total', '—', '—'],
  ['Presupuestos', 'Aprueba o rechaza', 'Crea y edita', '—', '—'],
  ['Obras', 'Lectura', '—', 'Crea y edita', 'Solo asignadas'],
  ['Costos y horas', 'Lectura', '—', 'Registra', '—'],
  ['Cobranzas y pagos', 'Lectura', 'Total', '—', '—'],
  ['Alertas', 'Lectura', '—', 'Lectura', '—'],
  ['Reportes', 'Total', 'Cobranza', '—', '—'],
  ['Usuarios y roles', 'Total', '—', '—', '—'],
  ['Registro de avances', '—', '—', 'Lectura', 'Registra']
];
