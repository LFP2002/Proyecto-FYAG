export const UMBRAL = 5000000;
export const UMBRAL_ALERTA = 10;
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
  GERENCIA: 'Consulta y supervisión de información autorizada.',
  ADMINISTRATIVO_FINANZAS: 'Gestión comercial y financiera según permisos.',
  SUPERVISOR_OBRAS: 'Gestión operativa de Obras y revisión de materiales.',
  ADMINISTRADOR_TI: 'Administración de cuentas y auditoría de usuarios, sin acceso de negocio.',
  BODEGUERO: 'Gestión de existencias, movimientos y entregas de materiales.'
};

export const NAV = {
  GERENCIA: ['dashboard', 'clientes', 'presupuestos', 'obras', 'cobranzas', 'alertas', 'reportes', 'auditoria', 'inventario'],
  ADMINISTRATIVO_FINANZAS: ['clientes', 'presupuestos', 'obras', 'cobranzas', 'reportes', 'auditoria', 'inventario'],
  SUPERVISOR_OBRAS: ['obras', 'alertas', 'auditoria', 'inventario'],
  TECNICO: ['obras'],
  ADMINISTRADOR_TI: ['usuarios', 'auditoria'],
  BODEGUERO: ['inventario']
};

export const DEFMOD = { GERENCIA: 'dashboard', ADMINISTRATIVO_FINANZAS: 'presupuestos', SUPERVISOR_OBRAS: 'obras', TECNICO: 'obras', ADMINISTRADOR_TI: 'usuarios', BODEGUERO: 'inventario' };

export const MODS = {
  dashboard: { label: 'Dashboard', icon: 'speedometer2' },
  clientes: { label: 'Clientes', icon: 'people' },
  presupuestos: { label: 'Presupuestos', icon: 'file-earmark-text' },
  obras: { label: 'Obras', icon: 'building' },
  cobranzas: { label: 'Cobranzas', icon: 'cash-coin' },
  alertas: { label: 'Alertas', icon: 'bell' },
  reportes: { label: 'Reportes', icon: 'bar-chart-line' },
  usuarios: { label: 'Usuarios y roles', icon: 'person-gear' },
  auditoria: { label: 'Auditoría', icon: 'clipboard-data' },
  inventario: { label: 'Bodega e inventario', icon: 'boxes' }
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
  ['Clientes', 'Total', 'Total', '—', '—'],
  ['Presupuestos', 'Aprueba o rechaza', 'Crea y edita', '—', '—'],
  ['Obras', 'Lectura', '—', 'Crea y edita', 'Solo asignadas'],
  ['Costos y horas', 'Lectura', '—', 'Registra', '—'],
  ['Cobranzas y pagos', 'Lectura', 'Total', '—', '—'],
  ['Alertas', 'Lectura', '—', 'Lectura', '—'],
  ['Reportes', 'Total', 'Cobranza', '—', '—'],
  ['Usuarios y roles', '—', '—', '—', '—'],
  ['Registro de avances', '—', '—', 'Lectura', 'Registra']
].map((row) => [...row, row[0] === 'Usuarios y roles' ? 'Total' : '—']);
