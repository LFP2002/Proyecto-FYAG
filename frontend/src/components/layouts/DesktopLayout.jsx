import React, { useEffect, useRef, useState } from 'react';
import { TopBar, SideNav } from '../Shell';

export const FONT_LEVELS = [100, 112.5, 125, 137.5];
const FONT_KEY='fyag.font-level';
const savedFontLevel=()=>{try{const value=globalThis.localStorage?.getItem(FONT_KEY);return /^[0-4]$/.test(value||'')?Math.min(Number(value),FONT_LEVELS.length-1):0;}catch{return 0;}};

export default function DesktopLayout({ children }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [fontLevel,setFontLevel]=useState(savedFontLevel);
  useEffect(()=>{
    const root=globalThis.document?.documentElement;
    root?.setAttribute('data-fyag-font-level',String(fontLevel));
    try{globalThis.localStorage?.setItem(FONT_KEY,String(fontLevel));}catch{/* preferencia opcional */}
    return ()=>root?.removeAttribute('data-fyag-font-level');
  },[fontLevel]);
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
      <TopBar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} menuButtonRef={menuButtonRef} fontLevel={fontLevel} fontCount={FONT_LEVELS.length} onSelectFont={selectFont} onNavigate={()=>{setMenuOpen(false);mainRef.current?.focus();}} />
      <div className="fyag-body">
        <SideNav mobileOpen={menuOpen} onNavigate={closeOnNavigate} onEscape={closeOnEscape} />
        <main ref={mainRef} tabIndex={-1} className="fyag-content">{children}</main>
      </div>
    </>
  );
}
