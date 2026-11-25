export const UMBRAL = 5000000;
export const UMBRAL_ALERTA = 10;
// Los prototipos de negocio no se montan hasta integrar sus API.
export const TEC = '';

export const ROLES = {
  GERENCIA: { short: 'Gerencia' },
  ADMINISTRATIVO_FINANZAS: { short: 'Administrativo / Finanzas' },
  SUPERVISOR_OBRAS: { short: 'Supervisor de Obras' },
  TECNICO: { short: 'Técnico' },
  ADMINISTRADOR_TI: { short: 'Administrador de TI' },
  BODEGUERO: { short: 'Bodeguero' }
};

export const ROLE_NOTE = {
  GERENCIA: 'Consulta operativa de Obras y administración de categorías.',
  ADMINISTRATIVO_FINANZAS: 'Clientes, Presupuestos y consulta mínima de Obras.',
  SUPERVISOR_OBRAS: 'Gestión operativa de Obras, presupuestos propios y técnicos participantes.',
  ADMINISTRADOR_TI: 'Administración de cuentas y auditoría de usuarios, sin acceso de negocio.',
  BODEGUERO: 'Operación de inventario, despachos y devoluciones autorizadas.'
};

export const NAV = {
  GERENCIA: ['dashboard', 'presupuestos', 'obras', 'cobranzas', 'alertas', 'reportes', 'egresos', 'auditoria', 'inventario', 'solicitudes', 'mermas', 'chat'],
  ADMINISTRATIVO_FINANZAS: ['clientes', 'presupuestos', 'obras', 'cobranzas', 'reportes', 'auditoria', 'mermas', 'egresos', 'chat'],
  SUPERVISOR_OBRAS: ['obras', 'presupuestos', 'alertas', 'auditoria', 'inventario', 'solicitudes', 'mermas', 'chat'],
  TECNICO: ['obras', 'solicitudes', 'mermas', 'chat'],
  ADMINISTRADOR_TI: ['usuarios', 'auditoria', 'chat'],
  BODEGUERO: ['inventario', 'mermas', 'chat']
};

export const DEFMOD = { GERENCIA: 'dashboard', ADMINISTRATIVO_FINANZAS: 'presupuestos', SUPERVISOR_OBRAS: 'obras', TECNICO: 'obras', ADMINISTRADOR_TI: 'usuarios', BODEGUERO: 'inventario' }

export const MODS = {
  dashboard: { label: 'Dashboard', icon: 'M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z' },
  clientes: { label: 'Clientes', icon: 'M16 20v-1a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v1M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 20v-1a4 4 0 0 0-3-3.9M15 4.2a3.5 3.5 0 0 1 0 6.6' },
  presupuestos: { label: 'Presupuestos', icon: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6' },
  obras: { label: 'Obras', icon: 'M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6' },
  cobranzas: { label: 'Cobranzas', icon: 'M3 6h18v12H3zM3 10h18M7 15h3' },
  alertas: { label: 'Alertas', icon: 'M12 3l10 18H2zM12 10v5M12 18h.01' },
  reportes: { label: 'Reportes', icon: 'M5 20V10M12 20V4M19 20v-7M3 20h18' },
  usuarios: { label: 'Usuarios y roles', icon: 'M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6zM9.5 12l2 2 3.5-4' },
  auditoria: { label: 'Auditoría', icon: 'M4 5h16M4 12h16M4 19h16M7 5v.01M7 12v.01M7 19v.01' },
  inventario: { label: 'Inventario y bodega', icon: 'M3 7h18v13H3zM3 7l3-4h12l3 4M8 11v5M16 11v5' },
  solicitudes: { label: 'Solicitudes de materiales', icon: 'M5 3h14v18H5zM8 8h8M8 12h8M8 16h5' },
  mermas: { label: 'Mermas', icon: 'M12 3v18M3 12h18M5 5l14 14M19 5L5 19' },
  egresos: { label: 'Egresos', icon: 'M3 6h18v12H3zM7 10h6M7 14h3M16 10v4' },
  chat: { label: 'Chat interno', icon: 'M3 4h18v13H8l-5 4zM7 9h10M7 13h7' }
};

export const PRE_E = {
  BORRADOR: ['Borrador', 'gray'],
  PENDIENTE_FINANZAS: ['Pendiente de Finanzas', 'amber'],
  APROBADO_FINANZAS: ['Aprobado por Finanzas', 'blue'],
  RECHAZADO_FINANZAS: ['Rechazado por Finanzas', 'red'],
  PENDIENTE_GERENCIA: ['Pendiente de Finanzas (legado)', 'amber'],
  APROBADO_GERENCIA: ['Aprobado por Finanzas (legado)', 'blue'],
  RECHAZADO_GERENCIA: ['Rechazado por Finanzas (legado)', 'red'],
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
  ['Presupuestos', '—', 'Crea y gestiona', 'Elabora y envía sus presupuestos', '—'],
  ['Obras', 'Lectura', '—', 'Crea y edita', 'Solo asignadas'],
  ['Costos y horas', 'Lectura', '—', 'Registra', '—'],
  ['Cobranzas y pagos', 'Lectura', 'Total', '—', '—'],
  ['Alertas', 'Lectura', '—', 'Lectura', '—'],
  ['Reportes', 'Total', 'Cobranza', '—', '—'],
  ['Usuarios y roles', '—', '—', '—', '—'],
  ['Registro de avances', '—', '—', 'Lectura', 'Registra']
].map((row) => [...row, row[0] === 'Usuarios y roles' ? 'Total' : '—']);
