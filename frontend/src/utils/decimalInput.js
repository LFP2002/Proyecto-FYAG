// User input only. Never use to relax validation of API responses.
export function normalizeDecimalInput(value, integers, scale, {positive=false, fixed=false}={}) {
  if(typeof value!=='string')return null;
  const match=value.trim().match(new RegExp('^([0-9]{1,'+integers+'})(?:[.,]([0-9]{1,'+scale+'}))?$'));
  if(!match)return null;
  const whole=match[1].replace(/^0+(?=\d)/,'');
  const fraction=match[2]||'';
  if(positive&&!/[1-9]/.test(whole+fraction))return null;
  return whole+(fixed?'.'+fraction.padEnd(scale,'0'):fraction?'.'+fraction:'');
}
export const quantityInput=value=>normalizeDecimalInput(value,9,3,{positive:true});
export const unitCostInput=value=>normalizeDecimalInput(value,13,2);
export const financialAmountInput=(value,positive=false)=>normalizeDecimalInput(value,36,2,{positive});
export const hourlyCostInput=value=>normalizeDecimalInput(value,13,2,{fixed:true});
export const quantityHint='Ej.: 2,5 (sin separadores de miles)';
export const moneyHint='Ej.: 18500 o 18500,50 (sin separadores de miles)';
