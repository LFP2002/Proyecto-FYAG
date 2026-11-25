import React, { useEffect, useRef, useState } from 'react';
import { TopBar, SideNav } from '../Shell';

export const FONT_LEVELS = [100, 112.5, 125, 137.5, 150];
const FONT_KEY='fyag.font-level';
const savedFontLevel=()=>{try{const value=globalThis.localStorage?.getItem(FONT_KEY);return /^[0-4]$/.test(value||'')?Number(value):0;}catch{return 0;}};

export default function DesktopLayout({ children }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [fontLevel,setFontLevel]=useState(savedFontLevel);
  useEffect(()=>{
    const root=globalThis.document?.documentElement;
    root?.setAttribute('data-fyag-font-level',String(fontLevel));
    try{globalThis.localStorage?.setItem(FONT_KEY,String(fontLevel));}catch{/* preferencia opcional */}
    return ()=>root?.removeAttribute('data-fyag-font-level');
  },[fontLevel]);
  const adjustFont=delta=>setFontLevel(level=>Math.min(FONT_LEVELS.length-1,Math.max(0,level+delta)));
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
      <TopBar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} menuButtonRef={menuButtonRef} fontLevel={fontLevel} fontPercent={FONT_LEVELS[fontLevel]} maxFontLevel={FONT_LEVELS.length-1} onAdjustFont={adjustFont} />
      <div className="fyag-body">
        <SideNav mobileOpen={menuOpen} onNavigate={closeOnNavigate} onEscape={closeOnEscape} />
        <main ref={mainRef} tabIndex={-1} className="fyag-content">{children}</main>
      </div>
    </>
  );
}
