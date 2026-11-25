import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui/index.js';
import { API_ORIGIN } from '../auth/config.js';
import { ROLES } from '../data/constants.js';

const BASE = '/api/chat/';
const ATTACHMENT_LIMITS='JPEG/PNG: hasta 5 MB y 2048 × 2048 px. PDF: hasta 8 MB.';
export async function validateChatAttachment(file, decode=globalThis.createImageBitmap){
  const extension=file.name.split('.').pop().toLowerCase();
  if(!['jpg','jpeg','png','pdf'].includes(extension))return 'Selecciona un archivo JPEG, PNG o PDF.';
  if(!file.size)return 'El archivo está vacío.';
  if(file.size>(extension==='pdf'?8:5)*1024*1024)return extension==='pdf'?'El PDF supera los 8 MB.':'La imagen supera los 5 MB.';
  if(extension!=='pdf'&&typeof decode==='function'){
    let bitmap;
    try{bitmap=await decode(file);if(bitmap.width>2048||bitmap.height>2048)return 'La imagen supera las dimensiones máximas de 2048 × 2048 píxeles.';}
    catch{return 'No fue posible leer la imagen. Usa un JPEG o PNG válido.';}
    finally{bitmap?.close?.();}
  }
  return '';
}
const uuid = () => crypto.randomUUID();
const nameOf = (person) => person?.nombre || 'Usuario';
const convName = (conversation, details, userId) => conversation.tipo === 'GRUPAL'
  ? conversation.titulo || 'Grupo'
  : details?.participantes?.find(person => person.id !== userId)?.nombre || 'Conversación directa';
const initialsOf = name => name.split(/\s+/).filter(Boolean).slice(0,2).map(word=>word[0]).join('').toUpperCase();
const roleName = role => ROLES[role]?.short || 'Equipo FYAG';
const timeOf = date => new Date(date).toLocaleTimeString('es-CL',{hour:'2-digit',minute:'2-digit'});
const dayOf = date => new Date(date).toLocaleDateString('es-CL',{day:'numeric',month:'long',year:'numeric'});
const validId = id => Number.isSafeInteger(id) && id > 0;
const pageData = value => {
  if (!value || !Number.isSafeInteger(value.count) || value.count<0 || !Array.isArray(value.results) || value.results.length>25 || value.results.some(row=>!validId(row.id))) throw Error('Respuesta de chat inesperada.');
  return value;
};
const messagePage = (value, id) => {
  if (!value || !Array.isArray(value.results) || value.results.length>25 || value.results.some(row=>!validId(row.id)||row.conversacion!==id) || (value.siguiente_antes_id!==null&&!validId(value.siguiente_antes_id))) throw Error('Respuesta de mensajes inesperada.');
  return value;
};
const merged = (...lists) => [...new Map(lists.flat().map(row=>[row.id,row])).values()].sort((a,b)=>a.id-b.id);
const glyphs={plus:'M12 5v14M5 12h14',back:'M15 18l-6-6 6-6',search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM15 15l6 6',paperclip:'M8 13l7-7a3 3 0 0 1 4 4l-9 9a5 5 0 0 1-7-7l9-9',send:'M3 3l18 9-18 9 4-9-4-9zM7 12h14',close:'M6 6l12 12M18 6L6 18',refresh:'M20 11a8 8 0 1 0-2 6M20 4v7h-7',chat:'M3 4h18v13H8l-5 4zM7 9h10M7 13h7',file:'M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h5'};
function Icon({name}) {return <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={glyphs[name]}/></svg>;}
function IconButton({icon,label,...props}) {return <button type="button" className="chat-icon-btn" title={label} aria-label={label} {...props}><Icon name={icon}/></button>;}
function Avatar({name}) {return <span className="chat-avatar" aria-hidden="true">{initialsOf(name)||'?'}</span>;}

export default function Chat() {
  const { user, request } = useAuth();
  const [convs,setConvs]=useState([]),[convPage,setConvPage]=useState(1),[convInfo,setConvInfo]=useState(null);
  const [details,setDetails]=useState({}),[listSearch,setListSearch]=useState('');
  const [directory,setDirectory]=useState([]),[directoryInfo,setDirectoryInfo]=useState(null),[directoryPage,setDirectoryPage]=useState(1),[directorySearch,setDirectorySearch]=useState('');
  const [selected,setSelected]=useState(null),[messages,setMessages]=useState([]),[older,setOlder]=useState(null),[loadingMessages,setLoadingMessages]=useState(false);
  const [text,setText]=useState(''),[file,setFile]=useState(null),[create,setCreate]=useState(false),[group,setGroup]=useState(false),[title,setTitle]=useState(''),[members,setMembers]=useState([]);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[socketState,setSocketState]=useState('Conectando…');
  const [directoryLoading,setDirectoryLoading]=useState(false),[listLoading,setListLoading]=useState(false),[uncertain,setUncertain]=useState(false);
  const createKey=useRef(uuid()),messageKey=useRef(uuid()),fileKey=useRef(uuid()),socketRef=useRef(null),generation=useRef(0),retryTimer=useRef(null),retryCount=useRef(0);
  const recoverRef=useRef(async()=>{}),loadConvsRef=useRef(async()=>{}),selectedRef=useRef(null),detailsRef=useRef({}),detailPending=useRef(new Map()),listVersion=useRef(0),dirVersion=useRef(0),messageVersion=useRef(0),alive=useRef(true),writeLock=useRef(false);
  const thread=useRef(null),fileInput=useRef(null),composeInput=useRef(null),dialogSearch=useRef(null),newButton=useRef(null),scrollIntent=useRef(null),messagesRef=useRef([]),olderRef=useRef(null),readCursor=useRef(new Map());

  useEffect(()=>{alive.current=true;return()=>{alive.current=false;listVersion.current++;dirVersion.current++;messageVersion.current++;};},[]);
  const showError = e => {if(alive.current){const fields=e?.fieldErrors||{};const validation=['archivo','texto','body','detail','clave_idempotencia'].flatMap(key=>Array.isArray(fields[key])?fields[key]:[]);setError(validation.join(' ')||(e?.status===413?'El archivo excede el tamaño permitido.':e?.message)||'No fue posible completar la operación.');}};
  function detailFor(id) {
    if(detailsRef.current[id])return Promise.resolve(detailsRef.current[id]);
    if(detailPending.current.has(id))return detailPending.current.get(id);
    const pending=request(`${BASE}conversaciones/${id}/`).then(value=>{
      if(value.id!==id||!Array.isArray(value.participantes)||!value.participantes.some(p=>p.id===user.id))throw Error('Conversación no disponible.');
      if(alive.current){detailsRef.current={...detailsRef.current,[id]:value};setDetails(detailsRef.current);}
      return value;
    }).finally(()=>detailPending.current.delete(id));
    detailPending.current.set(id,pending);return pending;
  }
  async function loadConvs() {
    const version=++listVersion.current;setListLoading(true);
    try{
      const result=pageData(await request(`${BASE}conversaciones/?page=${convPage}`));
      if(!alive.current||version!==listVersion.current)return;
      setConvs(result.results);setConvInfo(result);
      // Consultar detalles existentes de forma acotada; no pedir toda la agenda ni
      // repetir detalles en cada aviso WebSocket. El servidor verifica membresía.
      const pending=result.results.filter(c=>!detailsRef.current[c.id]);
      for(let start=0;start<pending.length;start+=4){
        if(!alive.current||version!==listVersion.current)break;
        await Promise.allSettled(pending.slice(start,start+4).map(c=>detailFor(c.id)));
      }
    }catch(e){if(version===listVersion.current)showError(e);}
    finally{if(alive.current&&version===listVersion.current)setListLoading(false);}
  }
  loadConvsRef.current=loadConvs;
  useEffect(()=>{void loadConvs();},[convPage]);
  useEffect(()=>{
    if(!create)return;
    const version=++dirVersion.current;
    setDirectoryLoading(true);setDirectory([]);setDirectoryInfo(null);
    const timer=setTimeout(async()=>{
      try{
        const query=new URLSearchParams({page:String(directoryPage)});
        if(directorySearch.trim())query.set('buscar',directorySearch.trim());
        const result=pageData(await request(`${BASE}usuarios/?${query}`));
        if(alive.current&&version===dirVersion.current){setDirectory(result.results);setDirectoryInfo(result);}
      }catch(e){if(version===dirVersion.current)showError(e);}
      finally{if(alive.current&&version===dirVersion.current)setDirectoryLoading(false);}
    },directorySearch?250:0);
    return()=>{clearTimeout(timer);dirVersion.current++;};
  },[create,directoryPage,directorySearch]);
  useEffect(()=>{if(create)dialogSearch.current?.focus();},[create]);

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
          void loadConvsRef.current();
          if (selectedRef.current) void recoverRef.current();
        } else if (data.tipo === 'chat.mensaje') {
          void loadConvsRef.current();
          if (selectedRef.current?.id === data.conversacion_id) void recoverRef.current();
        } else if (data.tipo === 'ping') {
          socket.send(JSON.stringify({ tipo: 'pong' }));
        }
      };
      socket.onerror = () => generation.current === version && setSocketState('Avisos en tiempo real no disponibles; actualiza para consultar.');
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


  function current(id, version){return alive.current&&selectedRef.current?.id===id&&version===messageVersion.current;}
  function applyMessages(rows,cursor,intent){
    scrollIntent.current=intent;messagesRef.current=rows;olderRef.current=cursor;
    setMessages(rows);setOlder(cursor);
  }
  async function markRead(active,rows,version){
    const newest=rows.filter(row=>row.autor!==user.id).at(-1);
    if(!newest||!current(active.id,version)||newest.id<=(readCursor.current.get(active.id)||0))return;
    try{
      const ack=await request(`${BASE}conversaciones/${active.id}/leido/`,{method:'POST',body:{ultimo_mensaje_id:newest.id}});
      if(validId(ack.ultimo_leido_mensaje_id)){
        readCursor.current.set(active.id,Math.max(readCursor.current.get(active.id)||0,ack.ultimo_leido_mensaje_id));
        if(current(active.id,version))void loadConvsRef.current();
      }
    }catch(e){if(current(active.id,version))showError(e);}
  }
  async function loadMessages(id,before=null){
    const version=++messageVersion.current;setLoadingMessages(true);
    const active=selectedRef.current;
    try{
      const result=messagePage(await request(`${BASE}conversaciones/${id}/mensajes/${before?`?antes_id=${before}`:''}`),id);
      if(!current(id,version))return;
      const previous=messagesRef.current;
      const overlaps=result.results.some(row=>previous.some(old=>old.id===row.id));
      const oldest=result.results.at(-1)?.id;
      // Actualización de la última página: preservar historial cargado solo si
      // existe solapamiento; descartar expirados y nunca inventar continuidad.
      const now=Date.now();
      const retained=previous.filter(row=>Date.parse(row.vence_en)>now);
      const rows=before?merged(result.results,retained):overlaps?merged(retained.filter(row=>row.id<oldest),result.results):merged(result.results);
      const cursor=before?result.siguiente_antes_id:overlaps&&previous.some(row=>row.id<oldest)?olderRef.current:result.siguiente_antes_id;
      const element=thread.current;
      const intent=before&&element?{kind:'preserve',height:element.scrollHeight,top:element.scrollTop}:(!previous.length||!element||element.scrollHeight-element.scrollTop-element.clientHeight<100)?{kind:'bottom'}:null;
      applyMessages(rows,cursor,intent);
      if(!before)await markRead(active,rows,version);
    }catch(e){if(current(id,version))showError(e);}
    finally{if(current(id,version))setLoadingMessages(false);}
  }
  recoverRef.current=async()=>{const active=selectedRef.current;if(active)await loadMessages(active.id);};
  useLayoutEffect(()=>{
    const el=thread.current,intent=scrollIntent.current;
    if(el&&intent){if(intent.kind==='bottom')el.scrollTop=el.scrollHeight;else el.scrollTop=intent.top+el.scrollHeight-intent.height;}
    scrollIntent.current=null;
  },[messages]);
  function clearDraft(){setText('');setFile(null);if(fileInput.current)fileInput.current.value='';messageKey.current=uuid();fileKey.current=uuid();setUncertain(false);}
  async function open(conversation){
    if(writeLock.current||uncertain)return;
    if(selectedRef.current?.id===conversation.id)return;
    selectedRef.current=conversation;setSelected(conversation);setError('');clearDraft();applyMessages([],null,null);
    void detailFor(conversation.id).catch(e=>{if(selectedRef.current?.id===conversation.id)showError(e);});
    await loadMessages(conversation.id);
  }
  function back(){
    if(writeLock.current||uncertain)return;
    messageVersion.current++;selectedRef.current=null;setSelected(null);applyMessages([],null,null);setLoadingMessages(false);clearDraft();setError('');
  }
  function startCreate(){
    if(writeLock.current||uncertain)return;
    setError('');setGroup(false);setTitle('');setMembers([]);setDirectorySearch('');setDirectoryPage(1);createKey.current=uuid();setCreate(true);
  }
  function closeCreate(){if(writeLock.current||uncertain)return;setCreate(false);newButton.current?.focus();}
  async function createConv(person=null){
    if(writeLock.current||uncertain||(!person&&(!title.trim()||members.length<2||members.length>19)))return;
    writeLock.current=true;setBusy(true);setError('');
    try{
      const body=person?{tipo:'DIRECTA',destinatario:person.id,clave_idempotencia:createKey.current}:{tipo:'GRUPAL',titulo:title.trim(),participantes:members.map(p=>p.id),clave_idempotencia:createKey.current};
      const conversation=await request(`${BASE}conversaciones/`,{method:'POST',body});
      if(!alive.current)return;
      setCreate(false);createKey.current=uuid();setMembers([]);setTitle('');
      writeLock.current=false;await open(conversation);void loadConvsRef.current();
    }catch(e){showError(e);}
    finally{writeLock.current=false;if(alive.current)setBusy(false);}
  }
  function toggleMember(person){setMembers(old=>old.some(p=>p.id===person.id)?old.filter(p=>p.id!==person.id):old.length<19?[...old,person]:old);}
  async function send(event){
    event?.preventDefault();const active=selectedRef.current;
    if(!active||writeLock.current||(!text.trim()&&!file))return;
    writeLock.current=true;setBusy(true);setError('');
    try{
      if(file){
        const invalid=await validateChatAttachment(file);if(invalid){setError(invalid);return;}
        const body=new FormData();body.set('archivo',file);if(text.trim())body.set('texto',text.trim());
        await request(`${BASE}conversaciones/${active.id}/archivos/`,{method:'POST',body,headers:{'Idempotency-Key':fileKey.current}});
      }else await request(`${BASE}conversaciones/${active.id}/mensajes/`,{method:'POST',body:{texto:text.trim(),clave_idempotencia:messageKey.current}});
      if(alive.current&&selectedRef.current?.id===active.id){clearDraft();await loadMessages(active.id);if(thread.current)thread.current.scrollTop=thread.current.scrollHeight;composeInput.current?.focus();}
      void loadConvsRef.current();
    }catch(e){if(alive.current){setUncertain(e.status===0||e.status===409||e.status>=500||typeof e.status!=='number');showError(e);}}
    finally{writeLock.current=false;if(alive.current)setBusy(false);}
  }
  async function download(message){
    try{
      const blob=await request(`${BASE}archivos/${message.archivo.id}/descargar/`,{responseType:'blob'});
      const url=URL.createObjectURL(blob),anchor=document.createElement('a');
      anchor.href=url;anchor.download=message.archivo.nombre.replace(/[\\/]/g,'_');anchor.rel='noopener';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){showError(e);}
  }
  function reconnect(){
    clearTimeout(retryTimer.current);retryCount.current=0;const version=++generation.current;socketRef.current?.close();setSocketState('Conectando…');void connectSocket(version);
  }
  const selectedDetail=selected?details[selected.id]:null;
  const visibleConvs=convs.filter(c=>!listSearch.trim()||convName(c,details[c.id],user.id).toLowerCase().includes(listSearch.trim().toLowerCase()));
  const authorName=id=>id===user.id?'Tú':nameOf(selectedDetail?.participantes?.find(person=>person.id===id));
  const blocked=busy||uncertain;
  return <section className="commercial-page chat-page">
    <PageHead title="Chat interno"/>
    <div className="chat-topbar"><span className={`chat-status${socketState==='Conectado'?' is-ok':''}`} role="status" aria-live="polite">{socketState}</span>{socketState!=='Conectado'&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={reconnect}>Reconectar</button>}</div>
    {error&&<div className="alert alert-warning" role="alert">{error} <button type="button" className="btn btn-link btn-sm" onClick={()=>setError('')}>Cerrar aviso</button></div>}
    <div className={`chat-workspace${selected?' has-selection':''}`}>
      <aside className="chat-sidebar" aria-label="Conversaciones">
        <header className="chat-sidebar-head"><h2>Conversaciones</h2><div className="chat-head-actions"><IconButton icon="refresh" label="Actualizar conversaciones" onClick={()=>void loadConvs()} disabled={listLoading}/><button ref={newButton} type="button" className="chat-new" onClick={startCreate} disabled={blocked}><Icon name="plus"/> Nuevo chat</button></div></header>
        <label className="chat-search"><Icon name="search"/><input aria-label="Buscar conversaciones de esta página" placeholder="Buscar conversación" value={listSearch} onChange={e=>setListSearch(e.target.value)}/></label>
        <ul className="chat-conv-list">{visibleConvs.map(c=>{const name=convName(c,details[c.id],user.id);return <li key={c.id}><button type="button" className={`chat-conv${selected?.id===c.id?' on':''}`} aria-current={selected?.id===c.id?'true':undefined} disabled={blocked} onClick={()=>void open(c)}><Avatar name={name}/><span className="chat-conv-text"><span className="chat-conv-name">{name}</span><span className="chat-conv-meta">{c.tipo==='GRUPAL'?'Grupo':roleName(details[c.id]?.participantes?.find(p=>p.id!==user.id)?.rol)}</span></span>{c.no_leidos>0&&<span className="chat-unread" aria-label={c.no_leidos+' mensajes sin leer'}>{c.no_leidos}</span>}</button></li>;})}</ul>
        {!visibleConvs.length&&<p className="chat-list-empty">{listLoading?'Cargando conversaciones…':listSearch?'No hay coincidencias en esta página.':'Todavía no tienes conversaciones. Inicia un nuevo chat.'}</p>}
        {convInfo&&(convInfo.next||convInfo.previous)&&<nav className="chat-pagination" aria-label="Páginas de conversaciones"><button type="button" disabled={!convInfo.previous||listLoading} onClick={()=>setConvPage(p=>p-1)}>Anterior</button><span>{convPage}</span><button type="button" disabled={!convInfo.next||listLoading} onClick={()=>setConvPage(p=>p+1)}>Siguiente</button></nav>}
      </aside>
      <section className="chat-main" aria-label="Mensajes de chat">{selected?<>
        <header className="chat-head"><IconButton icon="back" label="Volver a conversaciones" onClick={back} disabled={blocked}/><Avatar name={convName(selected,selectedDetail,user.id)}/><div className="chat-title"><h2>{convName(selected,selectedDetail,user.id)}</h2><span className="sub">{selected.tipo==='GRUPAL'?(selectedDetail?selectedDetail.participantes.length+' participantes':'Grupo'):roleName(selectedDetail?.participantes?.find(p=>p.id!==user.id)?.rol)}</span></div><IconButton icon="refresh" label="Actualizar mensajes" disabled={loadingMessages} onClick={()=>void loadMessages(selected.id)}/></header>
        <div className="chat-thread" ref={thread} role="log" aria-label="Historial de mensajes" aria-live="polite">
          {older&&<button type="button" className="chat-load-older" disabled={loadingMessages} onClick={()=>void loadMessages(selected.id,older)}>Ver mensajes anteriores</button>}
          {loadingMessages&&!messages.length&&<p className="chat-thread-empty">Cargando mensajes…</p>}
          {!loadingMessages&&!messages.length&&<p className="chat-thread-empty">Aún no hay mensajes. ¡Inicia la conversación!</p>}
          {messages.map((message,index)=>{const mine=message.autor===user.id,day=dayOf(message.creado_en),previous=messages[index-1];return <React.Fragment key={message.id}>{(!previous||dayOf(previous.creado_en)!==day)&&<div className="chat-day">{day}</div>}<article className={`chat-msg${mine?' mine':''}`}>{!mine&&selected.tipo==='GRUPAL'&&<strong className="chat-author">{authorName(message.autor)}</strong>}{message.texto&&<p>{message.texto}</p>}{message.archivo&&<button type="button" className="chat-file" onClick={()=>void download(message)}><Icon name="file"/><span><strong>{message.archivo.nombre}</strong><small>{message.archivo.mime==='application/pdf'?'PDF':'Imagen'} · {Math.ceil(message.archivo.tamano_bytes/1024)} KB · Descargar</small></span></button>}<time dateTime={message.creado_en}>{timeOf(message.creado_en)}</time></article></React.Fragment>;})}
        </div>
        <form className="chat-composer" onSubmit={send}>
          {file&&<div className="chat-attachment"><Icon name="file"/><span>{file.name}</span><IconButton icon="close" label="Quitar archivo" disabled={blocked} onClick={()=>{setFile(null);if(fileInput.current)fileInput.current.value='';}}/></div>}
          {uncertain&&<p className="chat-uncertain" role="alert">No se confirmó el envío. Puedes reintentar exactamente el mismo mensaje sin duplicarlo.</p>}
          <div className="chat-composer-row"><input ref={fileInput} type="file" className="visually-hidden" accept="image/jpeg,image/png,application/pdf" aria-label="Archivo adjunto" disabled={blocked} onChange={e=>setFile(e.target.files?.[0]||null)}/><IconButton icon="paperclip" label="Adjuntar archivo" aria-describedby="chat-attachment-limits" disabled={blocked} onClick={()=>fileInput.current?.click()}/><textarea ref={composeInput} aria-label="Mensaje" placeholder="Escribe un mensaje…" rows={1} maxLength={2000} value={text} disabled={blocked} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent?.isComposing){e.preventDefault();void send();}}}/><button type="submit" className="chat-send" aria-label={uncertain?'Reintentar envío':'Enviar mensaje'} title="Enviar" disabled={busy||(!text.trim()&&!file)}><Icon name="send"/></button></div>
          <p id="chat-attachment-limits" className="chat-attachment-limits">{ATTACHMENT_LIMITS}</p>
        </form>
      </>:<div className="chat-welcome"><Icon name="chat"/><h2>Chat interno FYAG</h2><p>Selecciona una conversación o inicia un nuevo chat con tu equipo.</p><button type="button" className="chat-new" onClick={startCreate}><Icon name="plus"/> Nuevo chat</button></div>}</section>
    </div>
    {create&&<div className="chat-modal-backdrop" role="presentation"><section className="chat-modal" role="dialog" aria-modal="true" aria-labelledby="chat-create-title" onKeyDown={e=>{if(e.key==='Escape')closeCreate();if(e.key==='Tab'){const nodes=[...e.currentTarget.querySelectorAll('button:not(:disabled),input:not(:disabled)')];if(nodes.length){const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}}}>
      <header><h2 id="chat-create-title">{group?'Nuevo grupo':'Nuevo chat'}</h2><IconButton icon="close" label="Cerrar nuevo chat" disabled={busy} onClick={closeCreate}/></header>
      <div className="chat-modal-mode"><button type="button" aria-pressed={!group} disabled={busy} onClick={()=>{setGroup(false);setMembers([]);}}>Mensaje directo</button><button type="button" aria-pressed={group} disabled={busy} onClick={()=>setGroup(true)}>Crear grupo</button></div>
      {group&&<><label className="form-label">Nombre del grupo<input className="form-control" value={title} maxLength={100} disabled={busy} onChange={e=>setTitle(e.target.value)}/></label><div className="chat-member-chips">{members.map(p=><button type="button" key={p.id} disabled={busy} onClick={()=>toggleMember(p)}>{nameOf(p)} ×</button>)}</div><p className="commercial-help">{members.length}/19 participantes · mínimo 2</p></>}
      <label className="chat-search"><Icon name="search"/><input ref={dialogSearch} aria-label="Buscar contacto" placeholder="Buscar personas" maxLength={100} value={directorySearch} disabled={busy} onChange={e=>{setDirectoryPage(1);setDirectorySearch(e.target.value);}}/></label>
      <div className="chat-directory">{directory.map(p=><button type="button" className="chat-contact" key={p.id} disabled={busy||(group&&members.length===19&&!members.some(m=>m.id===p.id))} aria-pressed={group?members.some(m=>m.id===p.id):undefined} onClick={()=>group?toggleMember(p):void createConv(p)}><Avatar name={nameOf(p)}/><span><strong>{nameOf(p)}</strong><small>{roleName(p.rol)}</small></span>{group&&<span aria-hidden="true">{members.some(m=>m.id===p.id)?'✓':'+'}</span>}</button>)}{!directory.length&&<p className="chat-list-empty">{directoryLoading?'Buscando…':'No hay contactos disponibles.'}</p>}</div>
      {directoryInfo&&(directoryInfo.next||directoryInfo.previous)&&<nav className="chat-pagination" aria-label="Páginas de contactos"><button type="button" disabled={busy||!directoryInfo.previous} onClick={()=>setDirectoryPage(p=>p-1)}>Anterior</button><span>{directoryPage}</span><button type="button" disabled={busy||!directoryInfo.next} onClick={()=>setDirectoryPage(p=>p+1)}>Siguiente</button></nav>}
      {error&&<p role="alert" className="chat-uncertain">{error}</p>}
      {group&&<button type="button" className="chat-new" disabled={busy||!title.trim()||members.length<2||members.length>19} onClick={()=>void createConv()}>Crear grupo</button>}
    </section></div>}
  </section>;
}
