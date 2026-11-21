import React from 'react';
import { APPEARANCE_OPTIONS, useAppearance } from '../../context/AppearanceContext.jsx';
import BootstrapIcon from '../ui/BootstrapIcon.jsx';

function Selectors({preferences,setPreferences,suffix}){
  const change=(key)=>(event)=>setPreferences((current)=>({...current,[key]:event.target.value}));
  return <>
    <label htmlFor={`appearance-theme-${suffix}`}><BootstrapIcon name={preferences.theme==='dark'?'moon-stars':'sun'} /> Tema</label>
    <select id={`appearance-theme-${suffix}`} className="form-select form-select-sm" value={preferences.theme} onChange={change('theme')} aria-label="Tema de color"><option value="light">Claro</option><option value="dark">Oscuro</option></select>
    <label htmlFor={`appearance-scale-${suffix}`}><BootstrapIcon name="zoom-in" /> Texto</label>
    <select id={`appearance-scale-${suffix}`} className="form-select form-select-sm" value={preferences.scale} onChange={change('scale')} aria-label="Tamaño del texto">{Object.entries(APPEARANCE_OPTIONS.scales).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select>
    <label htmlFor={`appearance-font-${suffix}`}><BootstrapIcon name="fonts" /> Fuente</label>
    <select id={`appearance-font-${suffix}`} className="form-select form-select-sm" value={preferences.font} onChange={change('font')} aria-label="Fuente"><option value="system">Sistema</option><option value="serif">Serif</option><option value="humanist">Humanista</option></select>
  </>;
}
export default function AppearanceControls({compact=false}){
  const {preferences,setPreferences}=useAppearance();
  if(compact)return <details className="appearance-popover"><summary aria-label="Configuración de apariencia"><BootstrapIcon name="sliders" /> Apariencia</summary><fieldset className="appearance-controls is-compact"><legend>Preferencias visuales</legend><Selectors {...{preferences,setPreferences}} suffix="compact" /></fieldset></details>;
  return <fieldset className="appearance-controls"><legend>Apariencia</legend><Selectors {...{preferences,setPreferences}} suffix="panel" /></fieldset>;
}
