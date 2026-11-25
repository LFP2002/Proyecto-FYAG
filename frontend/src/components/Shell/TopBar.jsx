import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ROLES } from '../../data/constants';
import { Icon } from '../ui';

export default function TopBar({ menuOpen = false, onToggleMenu, menuButtonRef, fontLevel=0, fontCount=4, onSelectFont }) {
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
    globalThis.addEventListener?.('resize',align);
    return ()=>globalThis.removeEventListener?.('resize',align);
  },[fontOpen]);
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
        <div className="fyag-font-picker" ref={fontRef}
          onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setFontOpen(false);}}
          onKeyDown={event=>{if(event.key==='Escape'&&fontOpen){event.preventDefault();closeFont();}}}>
          <button ref={fontButton} type="button" className="fyag-font-trigger" aria-label="Tamaño de letra" title="Tamaño de letra" aria-expanded={fontOpen} aria-controls="fyag-font-options" onClick={()=>setFontOpen(open=>!open)}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d="M3 19 9 5l6 14M5 15h8M17 11l3 8m-6 0 3-8m-2 5h4"/></svg>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" focusable="false"><path d="m2 4 4 4 4-4"/></svg>
          </button>
          {fontOpen&&<div ref={fontPanel} id="fyag-font-options" className="fyag-font-options" role="group" aria-label="Elegir tamaño de letra">
            <div className="fyag-font-heading">Tamaño de letra</div>
            <div className="fyag-font-grid">
              {Array.from({length:fontCount},(_,index)=><button key={index} type="button" className="fyag-font-option" aria-label={['Tamaño normal','Tamaño mediano','Tamaño grande','Tamaño muy grande'][index]} aria-pressed={fontLevel===index} style={{'--font-sample-size':`${15+index*4}px`}} onClick={()=>{onSelectFont?.(index);closeFont();}}>
                <span aria-hidden="true">A</span>{fontLevel===index&&<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>}
              </button>)}
            </div>
            <button type="button" className="fyag-font-reset" onClick={()=>{onSelectFont?.(0);closeFont();}}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5"/></svg> Restablecer
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
