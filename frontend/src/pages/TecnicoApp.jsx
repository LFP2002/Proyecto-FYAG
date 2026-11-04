import React from 'react';
import { useApp } from '../context/AppContext';
import { OBRA_CHIP, ROLES, TEC } from '../data/constants';
import { Chip, Icon, Track } from '../components/ui';

export default function TecnicoApp() {
  const { obrasC, bitacora, tecTab, tecObra, fTecNota, setField, set, logout, addAvance, saveNota } = useApp();
  
  const mias = obrasC.filter((o) => o.tecnico === TEC && o.estado !== 'Finalizada' && o.estado !== 'Cancelada');
  const t = obrasC.find((o) => o.id === tecObra);
  const ids = mias.map((o) => o.id);

  return (
    <div className="tec-bg">
      {/* Barra superior simplificada */}
      <div className="protobar">
        <span className="fw-bold">Panel del Técnico</span>
        <button className="btn btn-sm btn-fyag-white ms-auto" onClick={logout}>Salir</button>
      </div>
      
      <div className="tec-container">
        <header className="tec-top">
          <div className="tec-eyebrow">FYAG · Técnico</div>
          <div className="tec-name">{ROLES.tecnico.user}</div>
        </header>
        
        <div className="tec-note">
          <Icon d="M6 11V8a6 6 0 0 1 12 0v3M5 11h14v10H5zM12 15v2" />
          <span>Solo ves tus obras asignadas. Sin acceso a información financiera.</span>
        </div>
        
        <div className="tec-body">
          {/* LISTA DE OBRAS */}
          {tecTab === 'obras' && !t && (
            <>
              <h2>Mis obras</h2>
              {mias.map((o) => (
                <button key={o.id} className="obra-card" onClick={() => set({ tecObra: o.id, fTecNota: '' })}>
                  <span className="oc-t">{o.id} · {o.cliente}</span>
                  <span className="oc-s">{o.servicio}</span>
                  <span className="mini">
                    <Chip cls={OBRA_CHIP[o.estado]}>{o.estado}</Chip>
                    <Track small value={o.avance} />
                    <strong>{o.avance}%</strong>
                  </span>
                </button>
              ))}
              {mias.length === 0 && <p className="fyag-empty">No tienes obras asignadas.</p>}
            </>
          )}

          {/* DETALLE DE OBRA */}
          {tecTab === 'obras' && t && (
            <>
              <button className="btn btn-sm btn-outline-secondary mb-3" onClick={() => setField('tecObra', null)}>‹ Volver a mis obras</button>
              <h2>{t.id} · {t.cliente}</h2>
              <div className="kv"><span>Servicio</span><strong>{t.servicio}</strong></div>
              <div className="kv"><span>Estado</span><Chip cls={OBRA_CHIP[t.estado]}>{t.estado}</Chip></div>
              <div className="kv"><span>Avance</span><strong>{t.avance}%</strong></div>
              <div className="mb-3"><Track value={t.avance} /></div>
              
              <label>Actualizar avance</label>
              <div className="avrow">
                {[5, 10, 25].map((n) => (
                  <button key={n} className="btn btn-outline-secondary" onClick={() => addAvance(n)}>+{n}%</button>
                ))}
              </div>
              
              <label htmlFor="f-tn" className="mt-3">Registrar en bitácora</label>
              <textarea id="f-tn" className="form-control" value={fTecNota} onChange={(e) => setField('fTecNota', e.target.value)} placeholder="Describe el trabajo realizado..." />
              <button className="btn btn-fyag-primary w-100 mt-2" onClick={saveNota}>Guardar registro</button>
              
              <h2 className="mt-4">Bitácora de esta obra</h2>
              {bitacora.filter((b) => b.obra === t.id).map((b, i) => (
                <div key={i} className="bit">
                  <strong>{b.fecha}</strong>
                  <div className="feed-d">{b.texto}</div>
                </div>
              ))}
              {bitacora.every((b) => b.obra !== t.id) && <p className="fyag-empty">Aún no hay registros.</p>}
            </>
          )}

          {/* PESTAÑA BITÁCORA */}
          {tecTab === 'bit' && (
            <>
              <h2>Bitácora de avances</h2>
              {bitacora.filter((b) => ids.includes(b.obra)).map((b, i) => (
                <div key={i} className="bit">
                  <strong>{b.obra} · {b.fecha}</strong>
                  <div className="feed-d">{b.texto}</div>
                </div>
              ))}
              {bitacora.every((b) => !ids.includes(b.obra)) && <p className="fyag-empty">Aún no hay registros.</p>}
            </>
          )}
        </div>

        {/* NAVEGACIÓN INFERIOR */}
        <nav className="tec-nav" aria-label="Navegación del técnico">
          <button className={tecTab === 'obras' ? 'on' : ''} onClick={() => set({ tecTab: 'obras', tecObra: null })}>
            <Icon d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6" /> Mis obras
          </button>
          <button className={tecTab === 'bit' ? 'on' : ''} onClick={() => setField('tecTab', 'bit')}>
            <Icon d="M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" /> Bitácora
          </button>
        </nav>
      </div>
    </div>
  );
}