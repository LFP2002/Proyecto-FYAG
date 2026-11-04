import { TopBar, SideNav } from '../Shell';
import React from 'react';

export default function DesktopLayout({ children }) {
  return (
    <>
      <TopBar />
      <div className="fyag-body">
        <SideNav />
        <main className="fyag-content">{children}</main>
      </div>
    </>
  );
}