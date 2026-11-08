// Valores enviados a Django, sin convertir ni normalizar unidades históricas.
export const UNIT_GROUPS = [
  { label: 'Materiales y cantidades', options: [
    ['u', 'Unidad (u)'], ['par', 'Par (par)'], ['juego', 'Juego (juego)'],
    ['kit', 'Kit (kit)'], ['caja', 'Caja (caja)'], ['rollo', 'Rollo (rollo)'],
    ['saco', 'Saco (saco)'], ['plancha', 'Plancha (plancha)'],
  ] },
  { label: 'Longitud, superficie y volumen', options: [
    ['mm', 'Milímetro (mm)'], ['cm', 'Centímetro (cm)'], ['m', 'Metro lineal (m)'],
    ['m²', 'Metro cuadrado (m²)'], ['m³', 'Metro cúbico (m³)'],
    ['L', 'Litro (L)'], ['mL', 'Mililitro (mL)'],
  ] },
  { label: 'Masa', options: [
    ['g', 'Gramo (g)'], ['kg', 'Kilogramo (kg)'], ['t', 'Tonelada (t)'],
  ] },
  { label: 'Instalaciones y servicios', options: [
    ['h', 'Hora (h)'], ['día', 'Día (día)'], ['jornada', 'Jornada (jornada)'],
    ['punto', 'Punto de instalación (punto)'], ['instalación', 'Instalación (instalación)'],
    ['servicio', 'Servicio (servicio)'], ['global', 'Global / suma alzada (global)'],
  ] },
];
export const OTHER_UNIT = '__otra__';
export const isCatalogUnit = (value) => UNIT_GROUPS.some((group) => group.options.some(([unit]) => unit === value));
