import React, { useEffect, useRef, useState } from 'react';
import { TopBar, SideNav } from '../Shell';
import { useApp } from '../../context/AppContext';

export const FONT_LEVELS = [100, 112.5, 125, 137.5];
const FONT_KEY='fyag.font-level';
const THEME_KEY='fyag.theme';
const savedFontLevel=()=>{try{const value=globalThis.localStorage?.getItem(FONT_KEY);return /^[0-4]$/.test(value||'')?Math.min(Number(value),FONT_LEVELS.length-1):0;}catch{return 0;}};
const savedTheme=()=>{try{return globalThis.localStorage?.getItem(THEME_KEY)==='dark'?'dark':'light';}catch{return 'light';}};

export default function DesktopLayout({ children }) {
  const { role } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const [fontLevel,setFontLevel]=useState(savedFontLevel);
  const [theme,setTheme]=useState(savedTheme);
  useEffect(()=>{
    const root=globalThis.document?.documentElement;
    root?.setAttribute('data-fyag-font-level',String(fontLevel));
    try{globalThis.localStorage?.setItem(FONT_KEY,String(fontLevel));}catch{/* preferencia opcional */}
    return ()=>root?.removeAttribute('data-fyag-font-level');
  },[fontLevel]);
  useEffect(()=>{
    const root=globalThis.document?.documentElement;
    root?.setAttribute('data-fyag-theme',theme);
    root?.setAttribute('data-fyag-role',role||'');
    try{globalThis.localStorage?.setItem(THEME_KEY,theme);}catch{/* preferencia opcional */}
    return ()=>{root?.removeAttribute('data-fyag-theme');root?.removeAttribute('data-fyag-role');};
  },[theme,role]);
  const selectFont=level=>{if(Number.isInteger(level)&&level>=0&&level<FONT_LEVELS.length)setFontLevel(level);};
  const menuButtonRef = useRef(null);
  const mainRef = useRef(null);

  const closeOnNavigate = () => {
    if (!menuOpen) return;
    setMenuOpen(false);
    mainRef.current?.focus();
  };
  const closeOnEscape = () => {
    setMenuOpen(false);
    menuButtonRef.current?.focus();
  };

  return (
    <>
      <TopBar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} menuButtonRef={menuButtonRef} fontLevel={fontLevel} fontCount={FONT_LEVELS.length} onSelectFont={selectFont} theme={theme} onToggleTheme={()=>setTheme(current=>current==='dark'?'light':'dark')} onNavigate={()=>{setMenuOpen(false);mainRef.current?.focus();}} />
      <div className="fyag-body">
        <SideNav mobileOpen={menuOpen} onNavigate={closeOnNavigate} onEscape={closeOnEscape} />
        <main ref={mainRef} tabIndex={-1} className="fyag-content">{children}</main>
      </div>
    </>
  );
}
