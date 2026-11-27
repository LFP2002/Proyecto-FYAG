import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ROLES } from '../../data/constants';
import { Icon } from '../ui';

export default function TopBar({ menuOpen = false, onToggleMenu, menuButtonRef, fontLevel=0, fontCount=4, onSelectFont, theme='light', onToggleTheme, onNavigate }) {
  const { user, logout } = useAuth();
  const [fontOpen,setFontOpen]=useState(false);
  const fontRef=useRef(null), fontButton=useRef(null), fontPanel=useRef(null);
  useLayoutEffect(()=>{
    if(!fontOpen)return;
    const align=()=>{
      const button=fontButton.current, panel=fontPanel.current;
      if(!button||!panel)return;
      const rect=button.getBoundingClientRect();
      const center=rect.left+rect.width/2;
      const width=panel.offsetWidth;
      const viewport=globalThis.document.documentElement.clientWidth;
      const left=Math.max(12,Math.min(center-width/2,viewport-width-12));
      const shift=left-(center-width/2);
      panel.style.setProperty('--font-panel-shift',`${shift}px`);
    };
    align();
    const frame=globalThis.requestAnimationFrame?.(align);
    globalThis.addEventListener?.('resize',align);
    return ()=>{
      globalThis.removeEventListener?.('resize',align);
      if(frame!=null)globalThis.cancelAnimationFrame?.(frame);
    };
  },[fontOpen,fontLevel]);
  useEffect(()=>{
    if(!fontOpen)return;
    const closeOutside=event=>{if(fontRef.current&&!fontRef.current.contains(event.target))setFontOpen(false);};
    globalThis.document?.addEventListener?.('pointerdown',closeOutside);
    return ()=>globalThis.document?.removeEventListener?.('pointerdown',closeOutside);
  },[fontOpen]);
  const closeFont=()=>{setFontOpen(false);fontButton.current?.focus();};
  return (
    <header className="fyag-top">
      <div className="brand">
        <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" />
        <span>FYAG · Sistema de Gestión</span>
      </div>
      <button
        type="button"
        ref={menuButtonRef}
        className="btn btn-sm btn-fyag-white fyag-menu-toggle"
        aria-controls="fyag-modules-nav"
        aria-expanded={menuOpen}
        onClick={onToggleMenu}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" className="bi bi-list" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path fillRule="evenodd" d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5" />
        </svg>
        {menuOpen ? 'Cerrar menú' : 'Menú'}
      </button>
      <div className="top-right">
        <button type="button" className="fyag-theme-toggle" aria-label={theme==='dark'?'Activar modo claro':'Activar modo oscuro'} title={theme==='dark'?'Activar modo claro':'Activar modo oscuro'} aria-pressed={theme==='dark'} onClick={onToggleTheme}>
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            {theme==='dark' ? <path d="M8 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7M8 0a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-1 0v-1A.5.5 0 0 1 8 0m0 14a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-1 0v-1A.5.5 0 0 1 8 14m8-6a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1 0-1h1A.5.5 0 0 1 16 8M2 8a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1 0-1h1A.5.5 0 0 1 2 8m11.657-5.657a.5.5 0 0 1 0 .707l-.707.707a.5.5 0 1 1-.707-.707l.707-.707a.5.5 0 0 1 .707 0m-9.9 9.9a.5.5 0 0 1 0 .707l-.707.707a.5.5 0 1 1-.707-.707l.707-.707a.5.5 0 0 1 .707 0m9.9 1.414a.5.5 0 0 1-.707 0l-.707-.707a.5.5 0 1 1 .707-.707l.707.707a.5.5 0 0 1 0 .707m-9.9-9.9a.5.5 0 0 1-.707 0l-.707-.707a.5.5 0 1 1 .707-.707l.707.707a.5.5 0 0 1 0 .707"/> : <path d="M6 .278a.77.77 0 0 1 .08.858 7.2 7.2 0 0 0-.88 3.43c0 4.01 3.25 7.26 7.26 7.26 1.26 0 2.44-.32 3.47-.88a.77.77 0 0 1 .86.08A.76.76 0 0 1 17 11.7 8.5 8.5 0 0 1 8.5 16 8.5 8.5 0 0 1 0 7.5 8.5 8.5 0 0 1 5.3.02.76.76 0 0 1 6 .278" transform="scale(.9) translate(.7 .5)"/>}
          </svg>
        </button>
        <div className="fyag-font-picker" ref={fontRef}
          onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setFontOpen(false);}}
          onKeyDown={event=>{if(event.key==='Escape'&&fontOpen){event.preventDefault();closeFont();}}}>
          <button ref={fontButton} type="button" className="fyag-font-trigger" aria-label="Tamaño de letra" title="Tamaño de letra" aria-expanded={fontOpen} aria-controls="fyag-font-options" onClick={()=>setFontOpen(open=>!open)}>
            {/* Bootstrap Icons v1.13.1 (MIT), SVG inline sin dependencias externas. */}
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-fonts" viewBox="0 0 16 16"><path d="M12.258 3h-8.51l-.083 2.46h.479c.26-1.544.758-1.783 2.693-1.845l.424-.013v7.827c0 .663-.144.82-1.3.923v.52h4.082v-.52c-1.162-.103-1.306-.26-1.306-.923V3.602l.431.013c1.934.062 2.434.301 2.693 1.846h.479z"/></svg>
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-chevron-down" viewBox="0 0 16 16"><path fillRule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708"/></svg>
          </button>
          {fontOpen&&<div ref={fontPanel} id="fyag-font-options" className="fyag-font-options" role="group" aria-label="Elegir tamaño de letra">
            <div className="fyag-font-heading">Tamaño de letra</div>
            <div className="fyag-font-controls">
              <button type="button" className="fyag-font-adjust" aria-label="Disminuir tamaño" aria-disabled={fontLevel===0} onClick={()=>{if(fontLevel>0)onSelectFont?.(fontLevel-1);}}>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-dash-lg" viewBox="0 0 16 16"><path fillRule="evenodd" d="M2 8a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11A.5.5 0 0 1 2 8"/></svg>
              </button>
              <output className="fyag-font-level" aria-label="Nivel de tamaño de letra" aria-live="polite" aria-atomic="true">{fontLevel+1}</output>
              <button type="button" className="fyag-font-adjust" aria-label="Aumentar tamaño" aria-disabled={fontLevel===fontCount-1} onClick={()=>{if(fontLevel<fontCount-1)onSelectFont?.(fontLevel+1);}}>
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-plus-lg" viewBox="0 0 16 16"><path fillRule="evenodd" d="M8 2a.5.5 0 0 1 .5.5v5h5a.5.5 0 0 1 0 1h-5v5a.5.5 0 0 1-1 0v-5h-5a.5.5 0 0 1 0-1h5v-5A.5.5 0 0 1 8 2"/></svg>
              </button>
            </div>
            <button type="button" className="fyag-font-reset" onClick={()=>onSelectFont?.(0)}>
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg> Restablecer
            </button>
          </div>}
        </div>
        <span className="d-inline-flex align-items-center gap-2">
          <Icon d="M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" />
          {user.username} · {ROLES[user.role].short}
        </span>
        <button className="btn btn-sm btn-fyag-white" onClick={() => void logout()}>
          <Icon d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9" /> Salir
        </button>
      </div>
    </header>
  );
}
