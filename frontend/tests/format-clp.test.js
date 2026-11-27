import test from 'node:test';
import assert from 'node:assert/strict';
import { formatCLP, formatCompactCLP, formatCivilDate } from '../src/utils/format.js';
test('formato CLP conserva decimales, signo y enteros superiores al rango seguro', () => {
  assert.equal(formatCLP('250000.00'), '$250.000,00 CLP');
  assert.equal(formatCLP('-15415562057.42'), '-$15.415.562.057,42 CLP');
  assert.equal(formatCLP('12345678901234567890.01'), '$12.345.678.901.234.567.890,01 CLP');
  assert.equal(formatCLP('0.00'), '$0,00 CLP');
  assert.equal(formatCLP(null), '—');
});

test('formato compacto de cobranzas conserva fracciones y fechas civiles', () => {
  assert.equal(formatCompactCLP('250000.00'), '$250.000');
  assert.equal(formatCompactCLP('0.00'), '$0');
  assert.equal(formatCompactCLP('12345678901234567890.01'), '$12.345.678.901.234.567.890,01');
  assert.equal(formatCompactCLP('-1.20'), '-$1,20');
  assert.equal(formatCompactCLP(null), '—');
  assert.equal(formatCivilDate('2026-11-13'), '13/11/2026');
});
