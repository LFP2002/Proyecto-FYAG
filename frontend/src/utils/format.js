export const fm = (n) => '$' + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
export const pctTxt = (n) => (Math.round(n * 10) / 10).toFixed(1).replace('.', ',') + '%';
export const devTxt = (d) => (d > 0 ? '+' : d < 0 ? '-' : '') + String(Math.abs(d)).replace('.', ',') + ' pts';
export const pad = (n) => String(n).padStart(3, '0');
export const stamp = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
};