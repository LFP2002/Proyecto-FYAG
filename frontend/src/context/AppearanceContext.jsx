import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';

const DEFAULTS={theme:'light',font:'system',scale:'1'};
const FONTS={system:'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',serif:'Georgia, "Times New Roman", serif',humanist:'"Trebuchet MS", Arial, sans-serif'};
const SCALES={'0.9':'12.6px','1':'14px','1.1':'15.4px','1.2':'16.8px'};
const SCALE_LABELS={'0.9':'90%','1':'100%','1.1':'110%','1.2':'120%'};
const NOOP=()=>{};
const FALLBACK={preferences:DEFAULTS,setPreferences:NOOP};
const AppearanceContext=createContext(FALLBACK);
const storageKey=(id)=>`fyag:appearance:${id}`;
function readPreferences(id){
  if(!id||typeof window==='undefined')return DEFAULTS;
  try{const saved=JSON.parse(window.localStorage.getItem(storageKey(id))||'null');return {theme:['light','dark'].includes(saved?.theme)?saved.theme:DEFAULTS.theme,font:Object.hasOwn(FONTS,saved?.font)?saved.font:DEFAULTS.font,scale:Object.hasOwn(SCALES,saved?.scale)?saved.scale:DEFAULTS.scale};}catch{return DEFAULTS;}
}
function AppearanceState({children,userId}){
  const [entry,setEntry]=useState(()=>({userId,preferences:readPreferences(userId)}));
  const preferences=entry.userId===userId?entry.preferences:readPreferences(userId);
  const setPreferences=(update)=>setEntry((current)=>{
    const currentPreferences=current.userId===userId?current.preferences:readPreferences(userId);
    return {userId,preferences:typeof update==='function'?update(currentPreferences):update};
  });
  useEffect(()=>{if(entry.userId!==userId)setEntry({userId,preferences:readPreferences(userId)});},[entry.userId,userId]);
  useEffect(()=>{
    if(typeof document==='undefined')return;
    const root=document.documentElement;root.dataset.theme=preferences.theme;root.style.setProperty('--fyag-font-family',FONTS[preferences.font]);root.style.setProperty('--fyag-font-scale',SCALES[preferences.scale]);root.style.fontSize=SCALES[preferences.scale];root.style.colorScheme=preferences.theme;
    if(entry.userId===userId&&userId)try{window.localStorage.setItem(storageKey(userId),JSON.stringify(preferences));}catch{/* Preferencias opcionales si el almacenamiento no está disponible. */}
  },[preferences,userId,entry.userId]);
  const value=useMemo(()=>({preferences,setPreferences}),[preferences,userId]);
  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}
export function AppearanceProvider({children}){const {user}=useAuth();return <AppearanceState key={user?.id||'anonymous'} userId={user?.id||null}>{children}</AppearanceState>;}
export function useAppearance(){return useContext(AppearanceContext)||FALLBACK;}
export const APPEARANCE_OPTIONS={fonts:FONTS,scales:SCALE_LABELS};
