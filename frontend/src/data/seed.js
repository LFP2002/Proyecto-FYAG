export const SEED_CLIENTES = [
  { nombre: 'Viña Concha y Toro', ciudad: 'Pirque', contacto: 'Marcela Ibáñez' },
  { nombre: 'Packing Frutícola Ñuble', ciudad: 'Chillán', contacto: 'Rodrigo Salinas' },
  { nombre: 'Agrícola del Sur', ciudad: 'Los Ángeles', contacto: 'Paula Vergara' },
  { nombre: 'Viña Santa Rita', ciudad: 'Buin', contacto: 'Tomás Aguirre' },
  { nombre: 'Frigorífico Bío Bío', ciudad: 'Concepción', contacto: 'Daniela Rojas' },
  { nombre: 'Berries del Maule', ciudad: 'Linares', contacto: 'Cristián Leiva' }
];

export const SEED_PRES = [
  { id: 'PRE-001', cliente: 'Viña Concha y Toro', desc: 'Refrigeración industrial, sala de barricas', monto: 4500000, estado: 'APROBADO_CLIENTE', obra: 'OB-001' },
  { id: 'PRE-002', cliente: 'Packing Frutícola Ñuble', desc: 'Climatización de línea de embalaje', monto: 6200000, estado: 'APROBADO_CLIENTE', obra: 'OB-002' },
  { id: 'PRE-003', cliente: 'Agrícola del Sur', desc: 'Mantención de cámaras de frío', monto: 2400000, estado: 'APROBADO_CLIENTE', obra: 'OB-003' },
  { id: 'PRE-004', cliente: 'Berries del Maule', desc: 'Túnel de congelado IQF', monto: 2600000, estado: 'APROBADO_CLIENTE', obra: 'OB-004' },
  { id: 'PRE-005', cliente: 'Viña Santa Rita', desc: 'Refrigeración industrial, bodega de guarda', monto: 5200000, estado: 'APROBADO_CLIENTE', obra: 'OB-005' },
  { id: 'PRE-006', cliente: 'Frigorífico Bío Bío', desc: 'Climatización de sala de proceso', monto: 3800000, estado: 'APROBADO_CLIENTE', obra: 'OB-006' },
  { id: 'PRE-007', cliente: 'Viña Concha y Toro', desc: 'Ampliación cámara de frío, fase 2', monto: 7800000, estado: 'PENDIENTE_GERENCIA', obra: null },
  { id: 'PRE-008', cliente: 'Packing Frutícola Ñuble', desc: 'Mantención preventiva anual', monto: 1150000, estado: 'BORRADOR', obra: null },
  { id: 'PRE-009', cliente: 'Agrícola del Sur', desc: 'Ampliación del sistema de frío, sala de empaque', monto: 4300000, estado: 'APROBADO_CLIENTE', obra: null },
  { id: 'PRE-010', cliente: 'Frigorífico Bío Bío', desc: 'Cámara de congelado, bodega norte', monto: 5600000, estado: 'ENVIADO_CLIENTE', obra: null }
];

export const SEED_OBRAS = [
  { id: 'OB-001', cliente: 'Viña Concha y Toro', servicio: 'Refrigeración Industrial', tecnico: 'Pedro Díaz', estado: 'En proceso', avance: 70, presupuesto: 4500000, preId: 'PRE-001' },
  { id: 'OB-002', cliente: 'Packing Frutícola Ñuble', servicio: 'Climatización', tecnico: 'Luis Torres', estado: 'En proceso', avance: 55, presupuesto: 6200000, preId: 'PRE-002' },
  { id: 'OB-003', cliente: 'Agrícola del Sur', servicio: 'Refrigeración Industrial', tecnico: 'Pedro Díaz', estado: 'Finalizada', avance: 100, presupuesto: 2400000, preId: 'PRE-003' },
  { id: 'OB-004', cliente: 'Berries del Maule', servicio: 'Refrigeración Industrial', tecnico: 'Luis Torres', estado: 'Suspendida', avance: 10, presupuesto: 2600000, preId: 'PRE-004' },
  { id: 'OB-005', cliente: 'Viña Santa Rita', servicio: 'Refrigeración Industrial', tecnico: 'Luis Torres', estado: 'En proceso', avance: 40, presupuesto: 5200000, preId: 'PRE-005' },
  { id: 'OB-006', cliente: 'Frigorífico Bío Bío', servicio: 'Climatización', tecnico: 'Pedro Díaz', estado: 'En proceso', avance: 30, presupuesto: 3800000, preId: 'PRE-006' }
];

export const SEED_COSTOS = {
  'OB-001': [
    { tipo: 'Material', desc: 'Compresores y cañería de cobre', monto: 1850000, fecha: '28/09' },
    { tipo: 'Horas', desc: '75 h técnico de instalación', monto: 1350000, fecha: '10/10' }
  ],
  'OB-002': [
    { tipo: 'Material', desc: 'Equipos split industriales', monto: 2600000, fecha: '25/09' },
    { tipo: 'Material', desc: 'Ductos y aislación', monto: 700000, fecha: '03/10' },
    { tipo: 'Horas', desc: '50 h de montaje', monto: 800000, fecha: '12/10' }
  ],
  'OB-003': [
    { tipo: 'Material', desc: 'Repuestos y gas refrigerante', monto: 1300000, fecha: '12/09' },
    { tipo: 'Horas', desc: '50 h de mantención', monto: 750000, fecha: '20/09' }
  ],
  'OB-004': [{ tipo: 'Material', desc: 'Levantamiento y materiales de prueba', monto: 200000, fecha: '30/09' }],
  'OB-005': [
    { tipo: 'Material', desc: 'Compresor principal y evaporadores', monto: 1400000, fecha: '02/10' },
    { tipo: 'Horas', desc: '35 h de instalación', monto: 700000, fecha: '13/10' }
  ],
  'OB-006': [
    { tipo: 'Material', desc: 'Unidades de climatización', monto: 800000, fecha: '08/10' },
    { tipo: 'Horas', desc: '20 h de montaje', monto: 400000, fecha: '14/10' }
  ]
};

export const SEED_PAGOS = [
  { id: 'PAG-001', obra: 'OB-003', monto: 2400000, estado: 'Pagado', fecha: '02/10' },
  { id: 'PAG-002', obra: 'OB-001', monto: 1500000, estado: 'Pagado', fecha: '05/10' },
  { id: 'PAG-003', obra: 'OB-002', monto: 1000000, estado: 'Pagado', fecha: '08/10' },
  { id: 'PAG-004', obra: 'OB-005', monto: 2600000, estado: 'Facturado', fecha: '15/10' },
  { id: 'PAG-005', obra: 'OB-002', monto: 2250000, estado: 'Facturado', fecha: '12/10' }
];

export const SEED_LOGS = [
  { kind: 'pre', title: 'Presupuesto PRE-006 aprobado', detail: 'Frigorífico Bío Bío · $3.800.000 · Aprobado por Gerencia', when: 'Hace 2 horas' },
  { kind: 'obra', title: 'Obra OB-005 iniciada', detail: 'Viña Santa Rita · Técnico asignado: Luis Torres', when: 'Hace 5 horas' },
  { kind: 'pago', title: 'Pago PAG-004 facturado', detail: 'Obra OB-005 · $2.600.000 · Estado: Facturado', when: 'Ayer' },
  { kind: 'obra', title: 'Técnico asignado a OB-006', detail: 'Pedro Díaz asignado por Supervisor de Obras', when: 'Hace 2 días' },
  { kind: 'obra', title: 'Obra OB-003 finalizada', detail: 'Agrícola del Sur · Margen final $350.000', when: 'Hace 3 días' }
];

export const SEED_USERS = [
  { name: 'Gerencia General', email: 'gerencia@fyag.cl', rol: 'Administrador General / Gerencia', activo: true },
  { name: 'Administración y Finanzas', email: 'finanzas@fyag.cl', rol: 'Administrativo / Finanzas', activo: true },
  { name: 'Supervisor de Obras', email: 'supervisor@fyag.cl', rol: 'Supervisor de Obras', activo: true },
  { name: 'Pedro Díaz', email: 'pdiaz@fyag.cl', rol: 'Técnico', activo: true },
  { name: 'Luis Torres', email: 'ltorres@fyag.cl', rol: 'Técnico', activo: true }
];

export const SEED_BIT = [
  { obra: 'OB-002', texto: 'Montaje de ductos de la línea 1 terminado. Pendiente prueba de presión.', autor: 'Luis Torres', fecha: '14/10 17:40' },
  { obra: 'OB-005', texto: 'Compresor principal instalado y fijado. Falta conexión eléctrica.', autor: 'Luis Torres', fecha: '13/10 16:05' },
  { obra: 'OB-001', texto: 'Aislación de sala de barricas al 80 %.', autor: 'Pedro Díaz', fecha: '12/10 11:20' }
];