import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { DEFMOD, NAV, ROLES, TEC, UMBRAL, UMBRAL_ALERTA } from '../data/constants';
import { fm, pad, pctTxt, stamp } from '../utils/format';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

const initial = {
  screen: 'login', loginRole: 'gerencia', role: null, mod: 'dashboard',
  
  // DATOS VACÍOS (Listos para conectar a la base de datos)
  pres: [],
  obras: [],
  clientes: [],
  pagos: [],
  costos: {},
  logs: [],
  usuarios: [
    { name: 'Gerencia General', email: 'gerencia@fyag.cl', rol: 'Administrador General / Gerencia', activo: true }
  ],
  bitacora: [],
  atendidas: [],
  
  // Estados de formularios y filtros
  filtroPre: 'all', showPreForm: false, fPreCliente: '', fPreDesc: '', fPreMonto: '',
  showCliForm: false, fCliNombre: '', fCliCiudad: '', fCliContacto: '',
  sel: null, estadoDraft: 'En proceso', fCostoTipo: 'Material', fCostoDesc: '', fCostoMonto: '',
  crearPre: null, fObraTec: '', fObraCat: 'Refrigeración Industrial',
  showPagoForm: false, fPagoObra: '', fPagoMonto: '',
  tecTab: 'obras', tecObra: null, fTecNota: '', toast: null
};

export function AppProvider({ children }) {
  const [s, setS] = useState(initial);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);

  const set = (patch) => setS((p) => ({ ...p, ...patch }));
  const setField = (k, v) => set({ [k]: v });

  const flash = (msg, kind = 'ok') => {
    clearTimeout(timer.current);
    set({ toast: { msg, kind } });
    timer.current = setTimeout(() => set({ toast: null }), 4500);
  };

  const mkLog = (kind, title, detail) => {
    const who = (ROLES[s.role] || {}).user || 'Sistema';
    return { kind, title, detail: `${detail} · ${who} · ${stamp()}`, when: 'Ahora' };
  };

  const costoDe = (id) => (s.costos[id] || []).reduce((a, c) => a + c.monto, 0);
  const obrasC = s.obras.map((o) => {
    const costo = costoDe(o.id);
    const pct = o.presupuesto ? (costo / o.presupuesto) * 100 : 0;
    const dev = Math.round((pct - o.avance) * 10) / 10;
    return { ...o, costo, margen: o.presupuesto - costo, pct, dev, alerta: o.estado === 'En proceso' && dev > UMBRAL_ALERTA };
  });
  const alertasAll = obrasC.filter((o) => o.alerta).map((o) => ({
    id: o.id, cliente: o.cliente, atendida: s.atendidas.includes(o.id),
    msg: `Costo en ${pctTxt(o.pct)} del presupuesto con ${o.avance}% de avance (+${String(o.dev).replace('.', ',')} pts).`
  }));
  const alertasPend = alertasAll.filter((a) => !a.atendida);
  const presPend = s.pres.filter((p) => p.estado === 'PENDIENTE_GERENCIA');
  const sinObra = s.pres.filter((p) => p.estado === 'APROBADO_CLIENTE' && !p.obra);

  // LA FUNCIÓN LOGIN AHORA RECIBE EL ROL
  const login = (selectedRole) => {
    const r = selectedRole || s.loginRole;
    set({ screen: 'app', role: r, mod: DEFMOD[r] || 'dashboard', sel: null, tecObra: null, tecTab: 'obras', crearPre: null });
  };
  
  const logout = () => set({ screen: 'login', role: null, sel: null, tecObra: null, crearPre: null });
  const go = (mod) => set({ mod, sel: null, crearPre: null });
  const mod = (NAV[s.role] || []).includes(s.mod) ? s.mod : DEFMOD[s.role] || 'dashboard';

  const presAction = (p, estado, title) => {
    set({ pres: s.pres.map((x) => (x.id === p.id ? { ...x, estado } : x)), logs: [mkLog('pre', title, `${p.cliente} · ${fm(p.monto)}`), ...s.logs] });
    flash(`${title}.`);
  };
  const savePre = () => {
    const monto = Number(s.fPreMonto);
    if (!s.fPreDesc.trim() || !(monto > 0)) return flash('Completa la descripción y un monto mayor a cero.', 'err');
    const id = 'PRE-' + pad(s.pres.length + 1);
    set({ pres: [...s.pres, { id, cliente: s.fPreCliente || 'Sin cliente', desc: s.fPreDesc.trim(), monto, estado: 'BORRADOR', obra: null }], logs: [mkLog('pre', `Presupuesto ${id} creado`, `${s.fPreCliente} · ${fm(monto)}`), ...s.logs], showPreForm: false, fPreDesc: '', fPreMonto: '' });
    flash(`Presupuesto ${id} guardado como borrador.`);
  };
  const saveCli = () => {
    if (!s.fCliNombre.trim()) return flash('Ingresa el nombre del cliente.', 'err');
    set({ clientes: [...s.clientes, { nombre: s.fCliNombre.trim(), ciudad: s.fCliCiudad.trim() || '—', contacto: s.fCliContacto.trim() }], showCliForm: false, fCliNombre: '', fCliCiudad: '', fCliContacto: '' });
    flash('Cliente registrado.');
  };
  const openObra = (id) => {
    const ob = s.obras.find((x) => x.id === id);
    set({ sel: id, estadoDraft: ob ? ob.estado : 'En proceso', fCostoDesc: '', fCostoMonto: '' });
  };
  const crearObra = () => {
    const p = s.pres.find((x) => x.id === s.crearPre);
    if (!p) return;
    const id = 'OB-' + pad(s.obras.length + 1);
    set({ obras: [...s.obras, { id, cliente: p.cliente, servicio: s.fObraCat, tecnico: s.fObraTec, estado: 'En proceso', avance: 0, presupuesto: p.monto, preId: p.id }], pres: s.pres.map((x) => (x.id === p.id ? { ...x, obra: id } : x)), costos: { ...s.costos, [id]: [] }, logs: [mkLog('obra', `Obra ${id} creada`, `${p.cliente} · ${s.fObraCat}`), ...s.logs], crearPre: null, sel: id, estadoDraft: 'En proceso' });
    flash(`Obra ${id} creada y vinculada a ${p.id}.`);
  };
  const applyEstado = () => {
    const ob = s.obras.find((x) => x.id === s.sel);
    if (!ob) return;
    const nx = s.estadoDraft;
    if (nx === 'Finalizada' && !ob.tecnico) return flash(`No se puede finalizar ${ob.id}: falta asignar un técnico responsable.`, 'err');
    if (nx === 'Cancelada' && s.pagos.some((p) => p.obra === ob.id && p.estado !== 'Anulado')) return flash(`No se puede cancelar ${ob.id}: tiene pagos asociados.`, 'err');
    set({ obras: s.obras.map((x) => (x.id === ob.id ? { ...x, estado: nx } : x)), logs: [mkLog('obra', `Obra ${ob.id} cambió a ${nx}`, ob.cliente), ...s.logs] });
    flash(`Estado de ${ob.id} actualizado a ${nx}.`);
  };
  const assignTec = (name) => {
    const ob = s.obras.find((x) => x.id === s.sel);
    if (!ob) return;
    set({ obras: s.obras.map((x) => (x.id === ob.id ? { ...x, tecnico: name } : x)), logs: [mkLog('obra', name ? `Técnico asignado a ${ob.id}` : `Técnico desasignado de ${ob.id}`, name ? `${name} asignado` : ob.cliente), ...s.logs] });
    flash(name ? `${name} asignado a ${ob.id}.` : `Obra ${ob.id} quedó sin técnico.`);
  };
  const addCosto = () => {
    const ob = obrasC.find((x) => x.id === s.sel);
    const monto = Number(s.fCostoMonto);
    if (!ob) return;
    if (!s.fCostoDesc.trim() || !(monto > 0)) return flash('Completa el detalle y un monto mayor a cero.', 'err');
    const nuevo = ob.costo + monto;
    const pct = ob.presupuesto ? (nuevo / ob.presupuesto) * 100 : 0;
    const dev = Math.round((pct - ob.avance) * 10) / 10;
    const alerta = ob.estado === 'En proceso' && dev > UMBRAL_ALERTA && !ob.alerta;
    const lista = [...(s.costos[ob.id] || []), { tipo: s.fCostoTipo, desc: s.fCostoDesc.trim(), monto, fecha: stamp().slice(0, 5) }];
    let logs = [mkLog('costo', `Costo registrado en ${ob.id}`, `${s.fCostoTipo} · ${fm(monto)}`), ...s.logs];
    if (alerta) logs = [mkLog('alerta', `Alerta de desviación en ${ob.id}`, `Costo ${pctTxt(pct)} con ${ob.avance}% de avance`), ...logs];
    set({ costos: { ...s.costos, [ob.id]: lista }, logs, fCostoDesc: '', fCostoMonto: '' });
    flash(alerta ? `Costo registrado. Se generó una alerta de desviación en ${ob.id}.` : `Costo registrado. Acumulado de ${ob.id}: ${fm(nuevo)}.`, alerta ? 'warn' : 'ok');
  };
  const pagoChange = (p, estado, title) => {
    set({ pagos: s.pagos.map((x) => (x.id === p.id ? { ...x, estado } : x)), logs: [mkLog('pago', title, `Obra ${p.obra} · ${fm(p.monto)}`), ...s.logs] });
    flash(`${title}.`);
  };
  const savePago = () => {
    const monto = Number(s.fPagoMonto);
    if (!(monto > 0)) return flash('Ingresa un monto mayor a cero.', 'err');
    const id = 'PAG-' + pad(s.pagos.length + 1);
    set({ pagos: [...s.pagos, { id, obra: s.fPagoObra || 'Sin obra', monto, estado: 'Facturado', fecha: stamp().slice(0, 5) }], logs: [mkLog('pago', `Pago ${id} facturado`, `Obra ${s.fPagoObra} · ${fm(monto)}`), ...s.logs], showPagoForm: false, fPagoMonto: '' });
    flash(`Estado de pago ${id} registrado.`);
  };
  const markAtendida = (o) => {
    set({ atendidas: [...s.atendidas, o.id], logs: [mkLog('alerta', `Alerta de ${o.id} marcada como atendida`, o.cliente), ...s.logs] });
    flash(`Alerta de ${o.id} marcada como atendida.`);
  };
  const toggleUser = (i) => {
    const u = s.usuarios[i];
    set({ usuarios: s.usuarios.map((x, j) => (j === i ? { ...x, activo: !x.activo } : x)) });
    flash(`Usuario ${u.name}${u.activo ? ' desactivado.' : ' activado.'}`);
  };
  const addAvance = (n) => {
    const ob = s.obras.find((x) => x.id === s.tecObra);
    if (!ob) return;
    const nv = Math.min(100, ob.avance + n);
    set({ obras: s.obras.map((x) => (x.id === ob.id ? { ...x, avance: nv } : x)), logs: [mkLog('obra', `Avance de ${ob.id} actualizado a ${nv}%`, ob.cliente), ...s.logs] });
    flash(nv >= 100 ? 'Avance al 100 %. El Supervisor debe cambiar el estado a Finalizada.' : `Avance de ${ob.id} actualizado a ${nv}%.`);
  };
  const saveNota = () => {
    const txt = s.fTecNota.trim();
    if (!txt) return flash('Escribe el registro antes de guardar.', 'err');
    set({ bitacora: [{ obra: s.tecObra, texto: txt, autor: TEC, fecha: stamp() }, ...s.bitacora], logs: [mkLog('obra', `Avance registrado en ${s.tecObra}`, txt.slice(0, 60)), ...s.logs], fTecNota: '' });
    flash(`Registro guardado en la bitácora de ${s.tecObra}.`);
  };

  const value = {
    ...s, mod, set, setField, flash, UMBRAL, obrasC, alertasAll, alertasPend, presPend, sinObra,
    login, logout, go, presAction, savePre, saveCli, openObra, crearObra, applyEstado, assignTec, addCosto,
    pagoChange, savePago, markAtendida, toggleUser, addAvance, saveNota
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}