import React, { useEffect, useRef, useState } from 'react';
import { authClient } from '../auth/client.js';
import InstalacionInicial from './InstalacionInicial.jsx';

const setupPath = '/configuracion-inicial';
const loginOptions = { restoreSession: false };
const createdOptions = { ...loginOptions, setupCreated: true };
const replaceDocumentPath = (url) => globalThis.history.replaceState(null, '', url);

function initialDark() {
  const fallback = globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
  try {
    const saved = globalThis.localStorage?.getItem('fyag.theme');
    return saved === 'dark' ? true : saved === 'light' ? false : fallback;
  } catch { return fallback; }
}

function initialFont() {
  try {
    const saved = globalThis.localStorage?.getItem('fyag.font-level') ?? '0';
    return /^[0-4]$/.test(saved) ? String(Math.min(Number(saved), 3)) : '0';
  } catch { return '0'; }
}

function saveTheme(dark) {
  try { globalThis.localStorage?.setItem('fyag.theme', dark ? 'dark' : 'light'); }
  catch { /* Preferencia opcional. */ }
}

function saveFont(level) {
  if (!/^[0-3]$/.test(level)) return;
  try { globalThis.localStorage?.setItem('fyag.font-level', level); }
  catch { /* Preferencia opcional. */ }
}

export default function InicioInstalacion({ children }) {
  const [entryPath] = useState(() => globalThis.location.pathname);
  const [phase, setPhase] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  const request = useRef(null);
  const [dark, setDark] = useState(initialDark);
  const [font, setFont] = useState(initialFont);

  useEffect(() => {
    let active = true;
    // React.StrictMode vuelve a suscribirse al mismo intento sin repetir el GET.
    if (request.current?.attempt !== attempt) {
      request.current = { attempt, result: authClient.initialSetupStatus({ signal: AbortSignal.timeout(10000) }) };
    }
    request.current.result.then(data => {
      if (!active) return;
      if (data?.pendiente === true) {
        if (entryPath !== setupPath) replaceDocumentPath(setupPath);
        setPhase('setup');
      } else if (data?.pendiente === false) {
        if (entryPath === setupPath) replaceDocumentPath('/');
        setPhase(entryPath === setupPath ? 'login' : 'normal');
      } else {
        setPhase('unavailable');
      }
    }).catch(() => { if (active) setPhase('unavailable'); });
    return () => { active = false; };
    // Ruta y navegación pertenecen al documento de entrada, no al URL reemplazado.
  }, [attempt, entryPath]);

  const checking = ['loading', 'unavailable', 'setup'].includes(phase);
  useEffect(() => {
    if (!checking) return;
    const root = globalThis.document?.documentElement;
    if (!root) return;
    root.dataset.fyagTheme = dark ? 'dark' : 'light';
    root.dataset.fyagFontLevel = font;
    return () => {
      delete root.dataset.fyagTheme;
      delete root.dataset.fyagFontLevel;
    };
  }, [checking, dark, font]);

  if (!checking) return children(phase === 'created' ? createdOptions : phase === 'login' ? loginOptions : {});
  return <main className="login-page setup-page"><section className="login-card" aria-labelledby="setup-title">
    <h1 id="setup-title" className="login-title">{phase === 'setup' ? 'Configuración inicial de FYAG' : 'FYAG'}</h1>
    {phase === 'loading' && <p role="status" className="mt-3">Comprobando el estado de la instalación…</p>}
    {phase === 'unavailable' && <>
      <p role="alert" className="mt-3">No se pudo comprobar el estado de la instalación.</p>
      <button type="button" className="btn btn-fyag-primary" onClick={() => {
        setPhase('loading');
        setAttempt(attempt + 1);
      }}>Reintentar</button>
    </>}
    {phase === 'setup' && <InstalacionInicial client={authClient} onCreated={() => {
      replaceDocumentPath('/');
      setPhase('created');
    }} />}
    <div className="d-flex flex-wrap align-items-end gap-2 mt-3">
      <button type="button" className="btn btn-outline-secondary" aria-pressed={dark} onClick={() => {
        saveTheme(!dark);
        setDark(!dark);
      }}>Tema oscuro</button>
      <div>
        <label htmlFor="setup-font">Tamaño de letra</label>
        <select id="setup-font" className="form-select" value={font} onChange={event => {
          const level = event.target.value;
          if (!/^[0-3]$/.test(level)) return;
          saveFont(level);
          setFont(level);
        }}>
          {['100%', '112,5%', '125%', '137,5%'].map((label, i) => <option key={i} value={i}>{label}</option>)}
        </select>
      </div>
    </div>
  </section></main>;
}
