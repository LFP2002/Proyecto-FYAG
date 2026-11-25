import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui/index.js';
import { API_ORIGIN } from '../auth/config.js';

const BASE = '/api/chat/';
const uuid = () => crypto.randomUUID();
const defaultName = (conversation) => conversation.tipo === 'DIRECTA'
  ? `Conversación #${conversation.id}`
  : conversation.titulo || `Grupo #${conversation.id}`;

const initialsOf = (name) => {
  const number = name.match(/#\d+/);
  return number ? number[0] : name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0]).join('').toUpperCase();
};

export default function Chat() {
  const { user, request } = useAuth();
  const [convs, setConvs] = useState([]);
  const [directory, setDirectory] = useState([]);
  const [convPage, setConvPage] = useState(1);
  const [convInfo, setConvInfo] = useState(null);
  const [directoryPage, setDirectoryPage] = useState(1);
  const [directoryInfo, setDirectoryInfo] = useState(null);
  const [directorySearch, setDirectorySearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [older, setOlder] = useState(null);
  const [text, setText] = useState('');
  const [create, setCreate] = useState(false);
  const [recipient, setRecipient] = useState('');
  const [group, setGroup] = useState(false);
  const [title, setTitle] = useState('');
  const [members, setMembers] = useState([]);
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [socketState, setSocketState] = useState('Conectando…');
  const [aliases, setAliases] = useState({});
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState('');
  const createKey = useRef(uuid());
  const messageKey = useRef(uuid());
  const fileKey = useRef(uuid());
  const socketRef = useRef(null);
  const generation = useRef(0);
  const retryTimer = useRef(null);
  const retryCount = useRef(0);
  const recoverRef = useRef(async () => {});
  const selectedRef = useRef(null);

  async function loadConvs() {
    setError('');
    try {
      const dirQuery = new URLSearchParams({ page: String(directoryPage) });
      if (directorySearch.trim()) dirQuery.set('buscar', directorySearch.trim());
      const [conversations, users] = await Promise.all([
        request(`${BASE}conversaciones/?page=${convPage}`),
        request(`${BASE}usuarios/?${dirQuery}`),
      ]);
      setConvs(conversations.results || []);
      setConvInfo(conversations);
      setDirectory(users.results || []);
      setDirectoryInfo(users);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { void loadConvs(); }, [convPage, directoryPage, directorySearch]);

  async function connectSocket(version) {
    try {
      const issued=await request(`${BASE}conexion/`,{method:'POST',body:{}});
      if (generation.current !== version) return;
      const base = API_ORIGIN || `${location.protocol}//${location.hostname}${location.port === '5173' ? ':8000' : location.port ? `:${location.port}` : ''}`;
      const origin = base.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
      const socket = new WebSocket(`${origin}/ws/chat/`);
      socketRef.current = socket;
      socket.onopen = () => {
        if (generation.current !== version) { socket.close(); return; }
        socket.send(JSON.stringify({tipo:'autenticar',ticket:issued.ticket}));
      };
      socket.onmessage = (event) => {
        if (generation.current !== version) return;
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        if (data.tipo === 'chat.conectado') {
          retryCount.current = 0;
          setSocketState('Conectado');
          void loadConvs();
          if (selectedRef.current) void recoverRef.current();
        } else if (data.tipo === 'chat.mensaje') {
          void loadConvs();
          if (selectedRef.current?.id === data.conversacion_id) void recoverRef.current();
        } else if (data.tipo === 'ping') {
          socket.send(JSON.stringify({ tipo: 'pong' }));
        }
      };
      socket.onerror = () => setSocketState('Avisos en tiempo real no disponibles; actualiza para consultar.');
      socket.onclose = (event) => {
        if (socketRef.current === socket) socketRef.current = null;
        if (generation.current !== version) return;
        setSocketState(event.code === 4401 ? 'Sesión WebSocket revocada' : 'Reconectando avisos…');
        if (event.code === 4401) return;
        if (retryCount.current>=5) {
          setSocketState('Avisos pausados tras varios intentos; puedes reconectar manualmente.');
          return;
        }
        const delay = Math.min(30000, 1000 * 2 ** Math.min(retryCount.current++, 5)) + Math.floor(Math.random() * 500);
        retryTimer.current = setTimeout(() => void connectSocket(version), delay);
      };
    } catch (e) {
      if (generation.current !== version) return;
      setSocketState(e.status === 429 ? 'Límite temporal de avisos; espera antes de reconectar.' : 'Avisos en tiempo real no disponibles; actualiza para consultar.');
      if (e.status === 401 || e.status === 403) return;
      if (retryCount.current >= 5) {
        setSocketState('Avisos pausados tras varios intentos; puedes reconectar manualmente.');
        return;
      }
      const delay = Math.min(30000, 1000 * 2 ** Math.min(retryCount.current++, 5));
      retryTimer.current = setTimeout(() => void connectSocket(version), delay);
    }
  }

  useEffect(() => {
    const version = ++generation.current;
    void connectSocket(version);
    return () => {
      generation.current++;
      clearTimeout(retryTimer.current);
      socketRef.current?.close(1000, 'vista cerrada');
      socketRef.current = null;
    };
  }, [user.id, user.role]);

  async function loadMessages(id, before = null, replace = true) {
    setError('');
    try {
      const suffix = before ? `?antes_id=${before}` : '';
      const result = await request(`${BASE}conversaciones/${id}/mensajes/${suffix}`);
      setMessages((old) => replace ? result.results : [...result.results, ...old]);
      setOlder(result.siguiente_antes_id);
      if (replace && result.results.length) {
        const latest = result.results.reduce((a, b) => a.id > b.id ? a : b);
        if (latest.autor !== user.id) {
          await request(`${BASE}conversaciones/${id}/leido/`, { method: 'POST', body: { ultimo_leido_mensaje_id: latest.id } });
        }
      }
    } catch (e) {
      setError(e.message);
    }
  }

  async function recoverMessages() {
    const active = selectedRef.current;
    if (!active) return;
    const known = messages.reduce((max, message) => Math.max(max, message.id), 0);
    let before = null;
    let combined = [];
    let pages = 0;
    let stop = false;
    while (!stop && pages++ < 100) {
      const result = await request(`${BASE}conversaciones/${active.id}/mensajes/${before ? `?antes_id=${before}` : ''}`);
      combined = [...combined, ...result.results];
      if (known && result.results.some((message) => message.id <= known)) { stop = true; break; }
      before = result.siguiente_antes_id;
      if (!before) stop = true;
    }
    const unique = [...new Map(combined.map((message) => [message.id, message])).values()].sort((a, b) => b.id - a.id);
    setMessages(unique);
    setOlder(combined.length >= 25 && before ? before : null);
    const newest = unique[0];
    if (newest) {
      await request(`${BASE}conversaciones/${active.id}/leido/`, { method: 'POST', body: { ultimo_leido_mensaje_id: newest.id } });
    }
  }
  recoverRef.current = recoverMessages;

  async function open(conversation) {
    selectedRef.current = conversation;
    setSelected(conversation);
    setMessages([]);
    setEditing(false);
    await loadMessages(conversation.id);
  }

  const convName = (conversation) => aliases[conversation.id] || defaultName(conversation);
  function startRename() {
    setDraftName(convName(selected));
    setEditing(true);
  }
  function saveRename(event) {
    event.preventDefault();
    const name = draftName.trim();
    if (!name) return;
    const next = { ...aliases };
    if (name === defaultName(selected)) delete next[selected.id];
    else next[selected.id] = name;
    setAliases(next);
    setEditing(false);
  }

  async function createConv(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const body = group
        ? { tipo: 'GRUPAL', titulo: title.trim(), participantes: members.map(Number), clave_idempotencia: createKey.current }
        : { tipo: 'DIRECTA', destinatario: Number(recipient), clave_idempotencia: createKey.current };
      const conversation = await request(`${BASE}conversaciones/`, { method: 'POST', body });
      setCreate(false);
      createKey.current = uuid();
      setRecipient('');
      setMembers([]);
      await loadConvs();
      await open(conversation);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function send(event) {
    event.preventDefault();
    if (!selected || (!text.trim() && !file)) return;
    setBusy(true);
    try {
      if (file) {
        const body = new FormData();
        body.set('archivo', file);
        if (text.trim()) body.set('texto', text.trim());
        await request(`${BASE}conversaciones/${selected.id}/archivos/`, { method: 'POST', body, headers: { 'Idempotency-Key': fileKey.current } });
      } else {
        await request(`${BASE}conversaciones/${selected.id}/mensajes/`, { method: 'POST', body: { texto: text.trim(), clave_idempotencia: messageKey.current } });
      }
      setText('');
      setFile(null);
      messageKey.current = uuid();
      fileKey.current = uuid();
      await loadMessages(selected.id);
      await loadConvs();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function download(message) {
    try {
      const blob = await request(`${BASE}archivos/${message.archivo.id}/descargar/`, { responseType: 'blob' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = message.archivo.nombre;
      anchor.rel = 'noopener';
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(e.message);
    }
  }

  return <section className="commercial-page">
    <PageHead title="Chat interno" sub="Conversaciones privadas y temporales; los mensajes se muestran como texto plano." />
    <p className={`chat-status${socketState === 'Conectado' ? ' is-ok' : ''}`} role="status" aria-live="polite">{socketState}</p>
    {socketState !== 'Conectado' && <button type="button" className="btn btn-outline-secondary btn-sm mb-2" onClick={() => {
      clearTimeout(retryTimer.current);
      retryCount.current = 0;
      const version = ++generation.current;
      socketRef.current?.close();
      void connectSocket(version);
    }}>Conectar avisos</button>}
    {error && <p className="alert alert-warning" role="alert">{error}</p>}
    <div className="row g-3 chat-layout">
      <aside className="col-12 col-lg-4">
        <div className="card-fyag chat-side">
          <div className="chat-side-block">
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h2>Conversaciones</h2>
              <button className="btn btn-outline-secondary btn-sm" onClick={() => void loadConvs()}>Actualizar</button>
            </div>
            <label className="form-label">Buscar usuarios elegibles<input className="form-control" maxLength="100" value={directorySearch} onChange={(event) => {
              setDirectoryPage(1);
              setDirectorySearch(event.target.value);
            }} /></label>
            <nav className="commercial-pager">
              <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!directoryInfo?.previous} onClick={() => setDirectoryPage((page) => page - 1)}>Usuarios anteriores</button>
              <span>Directorio · página {directoryPage}</span>
              <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!directoryInfo?.next} onClick={() => setDirectoryPage((page) => page + 1)}>Usuarios siguientes</button>
            </nav>
            <button className="btn btn-fyag-primary mt-3" onClick={() => { createKey.current = uuid(); setCreate(true); }}>Nueva conversación</button>
          </div>
          <ul className="chat-conv-list">{convs.map((conversation) => {
            const name = convName(conversation);
            return <li key={conversation.id}><button type="button" className={`chat-conv${selected?.id === conversation.id ? ' on' : ''}`} aria-current={selected?.id === conversation.id ? 'true' : undefined} onClick={() => void open(conversation)}>
              <span className="chat-avatar" aria-hidden="true">{initialsOf(name)}</span>
              <span className="chat-conv-text"><span className="chat-conv-name">{name}</span><span className="chat-conv-meta">{conversation.tipo === 'DIRECTA' ? 'Directa' : 'Grupo'}</span></span>
              {conversation.no_leidos > 0 && <span className="badge text-bg-primary">{conversation.no_leidos}</span>}
            </button></li>;
          })}</ul>
          <div className="chat-side-block">
            <nav className="commercial-pager">
              <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!convInfo?.previous} onClick={() => setConvPage((page) => page - 1)}>Conversaciones anteriores</button>
              <span>Página {convPage}</span>
              <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!convInfo?.next} onClick={() => setConvPage((page) => page + 1)}>Conversaciones siguientes</button>
            </nav>
          </div>
        </div>
      </aside>
      <div className="col-12 col-lg-8">
        <section className="card-fyag flush" aria-label="Mensajes de chat">{selected ? <>
          <div className="chat-head">
            {editing ? <form className="chat-rename" onSubmit={saveRename} onKeyDown={(event) => { if (event.key === 'Escape') setEditing(false); }}>
              <label className="visually-hidden" htmlFor="chat-rename-input">Nombre de la conversación</label>
              <input id="chat-rename-input" className="form-control" required maxLength="100" autoFocus value={draftName} onChange={(event) => setDraftName(event.target.value)} onFocus={(event) => event.target.select()} />
              <button className="btn btn-fyag-primary btn-sm" disabled={!draftName.trim()}>Guardar</button>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setEditing(false)}>Cancelar</button>
              <p className="chat-rename-help">{draftName.length}/100 caracteres · el nombre se guarda solo en este navegador.</p>
            </form> : <div className="chat-title"><div><h2>{convName(selected)}</h2><span className="sub">{selected.tipo === 'GRUPAL' ? 'Conversación grupal' : 'Conversación directa'}</span></div>
              <button type="button" className="chat-edit" aria-label="Editar nombre de la conversación" title="Editar nombre" onClick={startRename}><svg className="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" /></svg></button>
            </div>}
            <button className="btn btn-outline-secondary btn-sm" onClick={() => void loadMessages(selected.id)}>Actualizar mensajes</button>
          </div>
          {older && <button className="btn btn-outline-secondary btn-sm chat-older" onClick={() => void loadMessages(selected.id, older, false)}>Cargar anteriores</button>}
          <ol className="chat-thread" aria-live="polite">{[...messages].reverse().map((message) => <li className={`chat-msg${message.autor === user.id ? ' mine' : ''}`} key={message.id}>
            <div className="chat-msg-top"><strong>{message.autor === user.id ? 'Tú' : `Usuario #${message.autor}`}</strong><time>{new Date(message.creado_en).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })}</time></div>
            {message.texto && <p>{message.texto}</p>}
            {message.archivo && <div className="chat-file"><svg className="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h5" /></svg><span className="chat-file-name">{message.archivo.nombre}</span><span className="chat-file-meta">{message.archivo.mime} · {message.archivo.tamano_bytes} bytes</span><button type="button" className="btn btn-link btn-sm" onClick={() => void download(message)}>Descargar archivo</button></div>}
          </li>)}</ol>
          <form className="chat-composer" onSubmit={send}>
            <label className="form-label" htmlFor="chat-message">Mensaje de texto</label>
            <textarea id="chat-message" className="form-control" maxLength="2000" value={text} onChange={(event) => setText(event.target.value)} />
            <div className="chat-composer-row">
              <label className="form-label">Adjuntar JPEG, PNG o PDF<input type="file" className="form-control" accept="image/jpeg,image/png,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
              <button className="btn btn-fyag-primary" disabled={busy || (!text.trim() && !file)}>Enviar</button>
            </div>
            {file && <p className="chat-file-note">Archivo seleccionado: {file.name} ({file.size} bytes); el servidor valida tipo, tamaño y contenido.</p>}
          </form>
        </> : <p className="chat-empty">Selecciona una conversación para consultar sus mensajes.</p>}</section>
      </div>
    </div>
    {create && <div className="modal d-block" role="dialog" aria-modal="true" aria-labelledby="chat-create-title" style={{ background: 'rgba(0,0,0,.35)' }}><form className="modal-dialog modal-dialog-centered" onSubmit={createConv}><div className="modal-content p-3">
      <h2 id="chat-create-title">Nueva conversación</h2>
      <label className="form-check"><input className="form-check-input" type="checkbox" checked={group} onChange={(event) => setGroup(event.target.checked)} /> Grupo</label>
      {group ? <>
        <label className="form-label">Título<input className="form-control" required maxLength="100" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label className="form-label">Participantes (elige de 2 a 19)<select className="form-select" multiple value={members} onChange={(event) => setMembers([...event.target.selectedOptions].map((option) => option.value))}>{directory.filter((person) => person.id !== user.id).map((person) => <option key={person.id} value={person.id}>{person.nombre} · {person.rol}</option>)}</select></label>
      </> : <label className="form-label">Destinatario<select className="form-select" required value={recipient} onChange={(event) => setRecipient(event.target.value)}><option value="">Selecciona</option>{directory.map((person) => <option key={person.id} value={person.id}>{person.nombre} · {person.rol}</option>)}</select></label>}
      <div className="d-flex gap-2"><button className="btn btn-fyag-primary" disabled={busy || (group && (members.length < 2 || members.length > 19))}>Crear</button><button type="button" className="btn btn-outline-secondary" onClick={() => setCreate(false)}>Cancelar</button></div>
    </div></form></div>}
  </section>;
}
