export const fm = (n) => '$' + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
export const pctTxt = (n) => (Math.round(n * 10) / 10).toFixed(1).replace('.', ',') + '%';
export const devTxt = (d) => (d > 0 ? '+' : d < 0 ? '-' : '') + String(Math.abs(d)).replace('.', ',') + ' pts';
export const pad = (n) => String(n).padStart(3, '0');
export const stamp = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
// Formato visual exacto: no convertir importes de la API a Number.
export function formatCLP(value) {
  if (typeof value !== 'string' || !/^-?\d+(?:\.\d{1,2})?$/.test(value)) return '—';
  const negative = value.startsWith('-');
  const [integer, fraction = ''] = (negative ? value.slice(1) : value).split('.');
  return `${negative ? '-' : ''}$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')} CLP`;
}

// Para listados en CLP: omitir solo la fracción cero, sin redondear ni perder precisión.
export function formatCompactCLP(value) {
  return formatCLP(value).replace(/,00 CLP$/, '').replace(/ CLP$/, '');
}
export function formatCivilDate(value) {
  return typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value.split('-').reverse().join('/') : value;
}
