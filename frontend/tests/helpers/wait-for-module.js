import assert from 'node:assert/strict';
import {act} from 'react-test-renderer';
import {setTimeout as delay} from 'node:timers/promises';

// Espera el estado observable de Suspense, con plazo acotado.
export async function waitForModule(renderer) {
  const loading=()=>renderer.root.findAllByProps({role:'status'}).some(node=>node.children.includes('Cargando módulo…'));
  const deadline=Date.now()+10000;
  while(loading()&&Date.now()<deadline) await act(async()=>{await delay(5);});
  assert.equal(loading(),false,'El módulo debe completar su carga diferida');
  assert.equal(renderer.root.findAllByType('h2').some(node=>node.children.includes('No fue posible cargar este módulo')),false,'El módulo debe cargarse sin error');
  await act(async()=>{await new Promise(resolve=>setImmediate(resolve));});
}
