// Referencia informativa, no autorización. Revisada contra permissions*.py de los
// módulos comercial, obras, finanzas, inventario, alertas, reportes, auditoria,
// dashboard, chat y usuarios; los servicios verifican alcance y estado.
export const permissionRoles=[
 ['GERENCIA','Gerencia'],['ADMINISTRATIVO_FINANZAS','Finanzas'],['SUPERVISOR_OBRAS','Supervisor'],
 ['TECNICO','Técnico'],['BODEGUERO','Bodega'],['ADMINISTRADOR_TI','TI']
];
export const permissionLevels={manage:'Gestión',read:'Consulta',limited:'Restringido',none:'Sin acceso'};
const [G,F,S,T,B,I]=permissionRoles.map(([role])=>role);
const manage=(detail='')=>['manage',detail],read=(detail='')=>['read',detail],limited=detail=>['limited',detail];
export const permissionRows=[
 {label:'Dashboard',access:{[G]:read('Indicadores')}},
 {label:'Clientes',access:{[G]:read(),[F]:manage()}},
 {label:'Presupuestos',access:{[G]:read(),[F]:manage('Revisión y decisión comercial'),[S]:limited('Propios: elaborar y enviar a Finanzas')}},
 {label:'Obras y participantes',access:{[G]:read(),[F]:read('Vista financiera'),[S]:manage('Planificación y ejecución'),[T]:limited('Obras asignadas')}},
 {label:'Turnos y evidencias',access:{[G]:read(),[S]:manage('Revisión y corrección'),[T]:limited('Registro de turnos propios')}},
 {label:'Costos de obra',access:{[G]:read(),[F]:limited('Resumen financiero'),[S]:manage('Registro y validación')}},
 {label:'Cobranzas y pagos',access:{[G]:read(),[F]:manage()}},
 {label:'Egresos',access:{[G]:read(),[F]:manage()}},
 {label:'Inventario',access:{[G]:read(),[F]:read(),[S]:read(),[B]:manage('Catálogo y stock')}},
 {label:'Solicitudes de materiales',access:{[G]:read(),[S]:manage('Decidir solicitudes'),[T]:limited('Solicitudes propias')}},
 {label:'Entregas y devoluciones',access:{[G]:read(),[S]:limited('Autorizar'),[B]:limited('Ejecutar autorizaciones')}},
 {label:'Valorización y regularización',access:{[G]:read(),[F]:manage()}},
 {label:'Mermas de bodega',access:{[G]:read(),[F]:manage('Decidir'),[B]:limited('Declarar')}},
 {label:'Mermas de obra',access:{[G]:read(),[S]:manage('Decidir'),[T]:limited('Declarar en obra asignada')}},
 {label:'Alertas',access:{[G]:read(),[F]:limited('Atender las autorizadas'),[S]:limited('Atender las autorizadas')}},
 {label:'Reportes',access:{[G]:read('Obras, rentabilidad y cobranzas'),[F]:limited('Cobranzas')}},
 {label:'Usuarios y roles',access:{[I]:manage('Cuentas y asignación de roles')}},
 {label:'Auditoría',access:{[G]:limited('Comercial, obras y finanzas'),[F]:limited('Eventos de finanzas'),[S]:limited('Obras, excepto categorías'),[I]:limited('Eventos de usuarios')}},
 {label:'Chat interno',access:Object.fromEntries(permissionRoles.map(([role])=>[role,limited('Conversaciones propias')]))}
];
