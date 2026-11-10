import React, { useRef, useState } from 'react';
import { TopBar, SideNav } from '../Shell';

export default function DesktopLayout({ children }) {
  const [menuOpen, setMenuOpen] = useState(false);
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
      <TopBar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} menuButtonRef={menuButtonRef} />
      <div className="fyag-body">
        <SideNav mobileOpen={menuOpen} onNavigate={closeOnNavigate} onEscape={closeOnEscape} />
        <main ref={mainRef} tabIndex={-1} className="fyag-content">{children}</main>
      </div>
    </>
  );
}
