import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDecimalInput,quantityInput,unitCostInput,financialAmountInput,hourlyCostInput} from '../src/utils/decimalInput.js';
import {validateItem,itemPayload,validDecimal} from '../src/comercial/domain.js';
import {milli,preview} from '../src/bodega/domain.js';
test('entrada de montos y cantidades: coma, punto, enteros, precisión exacta',()=>{
 assert.equal(hourlyCostInput('18500'),'18500.00');
 assert.equal(hourlyCostInput('18500,5'),'18500.50');
 assert.equal(unitCostInput('18500,50'),'18500.50');
 assert.equal(quantityInput(' 2,125 '),'2.125');
 assert.equal(financialAmountInput('999999999999999999999999999999999999,99'),'999999999999999999999999999999999999.99');
 assert.equal(financialAmountInput('0',true),null);
 assert.equal(unitCostInput('0'),'0');
 assert.equal(normalizeDecimalInput('0001,5',9,3,{fixed:true}),'1.500');
 for(const v of ['1.234,50','1,234.50','1e3','-1','+1','1 000','1,2345','1,','',null,2.5])assert.equal(quantityInput(v),null);
 assert.equal(unitCostInput('1.000'),null);
 assert.equal(quantityInput('1.000'),'1.000');
 assert.equal(unitCostInput('99999999999999'),null);
 assert.equal(quantityInput('0,000'),null);
 assert.equal(validDecimal('1,25',9,3,true),false);
});
test('presupuesto: acepta coma al editar y conserva contrato al guardar',()=>{
 const form={descripcion:'Cable',cantidad:'2,5',unidad:'m',precio_unitario:'18500,50',orden:'1'};
 assert.deepEqual(validateItem(form),{});
 assert.deepEqual(itemPayload(form),{descripcion:'Cable',cantidad:'2.5',unidad:'m',precio_unitario:'18500.50',orden:1});
});
test('bodega: cantidades exactas y saldo previsto con coma',()=>{
 assert.equal(milli('2,125'),2125n);
 assert.deepEqual(preview({kind:'ENTREGA',row:{saldo:'10.000',maximo:'6.000'},cantidad:'2,125'}),{cantidad:'2.125',saldo:'7.875'});
});
