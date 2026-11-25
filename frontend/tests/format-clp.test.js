import test from 'node:test';
import assert from 'node:assert/strict';
import { formatCLP } from '../src/utils/format.js';
test('formato CLP conserva decimales, signo y enteros superiores al rango seguro', () => {
  assert.equal(formatCLP('250000.00'), '$250.000,00 CLP');
  assert.equal(formatCLP('-15415562057.42'), '-$15.415.562.057,42 CLP');
  assert.equal(formatCLP('12345678901234567890.01'), '$12.345.678.901.234.567.890,01 CLP');
  assert.equal(formatCLP('0.00'), '$0,00 CLP');
  assert.equal(formatCLP(null), '—');
});
