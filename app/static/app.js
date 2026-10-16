const $ = (id) => document.getElementById(id);
const pageLabels = {overview:'Resumen',records:'Registros',backups:'Respaldos',events:'Historial'};
let cachedRecords = [];
let restoreConfigured = false;
let toastTimer;

function safe(value) { return String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function formatDate(value) {
  if (!value) return 'Sin registros';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString('es-PE',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
}
function bytes(value) { return value < 1024 ? `${value} B` : `${(value / 1024).toFixed(1)} KB`; }
function token() { return $('token').value.trim(); }
function notice(message, isError=false) {
  const box = $('toast');
  box.textContent = message;
  box.className = `toast visible${isError ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.className = 'toast'; }, 5800);
}
function adminHeaders() {
  if (!token()) throw new Error('Ingresa tu token de administrador en el menu lateral.');
  return {'X-Admin-Token': token()};
}
async function request(url, options={}) {
  const headers = {...(options.headers || {})};
  if (options.method && options.method !== 'GET') Object.assign(headers,adminHeaders());
  if (options.body) headers['Content-Type'] = 'application/json';
  const response = await fetch(url,{...options,headers});
  if (!response.ok) {
    let msg = `Error ${response.status}`;
    try { const data = await response.json(); if (typeof data.detail === 'string') msg = data.detail; } catch (_) {}
    throw new Error(msg);
  }
  return response.json();
}
function changePage(page) {
  document.querySelectorAll('.page').forEach((item) => item.classList.toggle('active', item.id === `page-${page}`));
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('selected',item.dataset.page === page));
  $('location-title').textContent = pageLabels[page];
}
async function run(task) {
  try { await task(); await refresh(); }
  catch (err) { notice(err.message,true); }
}
async function refresh() {
  try {
    const [health,summary,pgStatus,records,fullCopies,jsonCopies,events] = await Promise.all([
      request('/health'),request('/api/summary'),request('/api/postgres/status'),
      request('/api/records'),request('/api/postgres/backups'),request('/api/backups'),request('/api/events')
    ]);
    $('db-state').textContent = health.database === 'postgresql' ? 'Conectado a PostgreSQL' : 'SQLite local (sin PostgreSQL)';
    $('db-state').classList.remove('error');
    $('metric-records').textContent = summary.records;
    $('metric-backups').textContent = summary.full_backups;
    $('metric-engine').textContent = summary.database;
    $('metric-last').textContent = fullCopies.length ? formatDate(fullCopies[0].created_at) : 'Aun no hay';
    ['pg-status','pg-status-home'].forEach((id) => {
      $(id).textContent = pgStatus.message;
      $(id).classList.toggle('warning',!pgStatus.ready);
    });
    ['full-backup-btn','full-backup-home'].forEach((id) => { $(id).disabled = !pgStatus.ready; });
    restoreConfigured = pgStatus.restore_ready;
    $('pg-restore-note').textContent = restoreConfigured
      ? 'Prueba de restauracion: habilitada en otra base PostgreSQL. Esta operacion reemplaza su contenido.'
      : 'Para probar una restauracion completa sin riesgo, ejecuta el workflow de backup de GitHub Actions. Opcional: configura RESTORE_DATABASE_URL con una base separada.';
    cachedRecords = records;
    showRecords(records);
    showFullBackups(fullCopies);
    showJsonBackups(jsonCopies);
    showEvents(events);
  } catch (err) {
    $('db-state').textContent = 'Sin conexion';
    $('db-state').classList.add('error');
    notice(`No se pudieron cargar los datos: ${err.message}`,true);
  }
}
function showRecords(rows) {
  $('records-count').textContent = `${rows.length} visibles`;
  $('records-body').innerHTML = rows.length ? rows.map((r) => `<tr><td>${r.id}</td><td>${safe(r.name)}</td><td>${safe(r.category)}</td><td>${r.quantity}</td><td>${formatDate(r.created_at)}</td><td><button type="button" data-edit="${r.id}">Editar</button><button class="delete" type="button" data-delete="${r.id}">Eliminar</button></td></tr>`).join('') : '<tr><td colspan="6">No hay registros. Usa el formulario para agregar uno.</td></tr>';
}
function showFullBackups(copies) {
  $('full-backups-count').textContent = `${copies.length} copias en el historial`;
  $('full-backups-body').innerHTML = copies.length ? copies.map((b) => `<tr><td>${safe(b.id)}</td><td>${formatDate(b.created_at)}</td><td>${bytes(b.size_bytes)}</td><td>${b.available ? 'En servidor' : 'No disponible'}</td><td><button type="button" data-pg-download="${safe(b.id)}" ${b.available ? '' : 'disabled'}>Descargar</button><button type="button" data-pg-verify="${safe(b.id)}" ${b.available ? '' : 'disabled'}>Verificar</button>${restoreConfigured ? `<button type="button" data-pg-restore="${safe(b.id)}" ${b.available ? '' : 'disabled'}>Probar restore</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="5">Todavia no hay copias completas. Conecta Neon y crea la primera.</td></tr>';
}
function showJsonBackups(copies) {
  $('backups-count').textContent = `${copies.length} copias parciales`;
  $('backups-body').innerHTML = copies.length ? copies.map((b) => `<tr><td>${safe(b.id)}</td><td>${formatDate(b.created_at)}</td><td>${b.record_count === null ? '-' : b.record_count}</td><td>${b.verified ? 'SHA-256 correcto' : 'Archivo alterado'}</td><td><button type="button" data-json-download="${safe(b.id)}" ${b.verified ? '' : 'disabled'}>Descargar</button><button type="button" data-json-restore="${safe(b.id)}" ${b.verified ? '' : 'disabled'}>Restaurar tabla</button></td></tr>`).join('') : '<tr><td colspan="5">No existen exportaciones JSON.</td></tr>';
}
function showEvents(events) {
  $('events-body').innerHTML = events.length ? events.map((e) => `<tr><td>${formatDate(e.created_at)}</td><td>${safe(e.action)}</td><td>${safe(e.detail)}</td></tr>`).join('') : '<tr><td colspan="3">Aun no hay operaciones registradas.</td></tr>';
}
async function download(url, filename) {
  const response = await fetch(url,{headers: adminHeaders()});
  if (!response.ok) {
    let msg = 'No se pudo descargar el archivo';
    try { const body = await response.json(); if (body.detail) msg = body.detail; } catch (_) {}
    throw new Error(msg);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 15000);
}
function clearForm() {
  $('record-form').reset();
  $('record-id').value = '';
  $('record-form-title').textContent = 'Nuevo registro';
  $('save-record-btn').textContent = 'Guardar';
  $('cancel-edit-btn').classList.add('hidden');
}
async function createPgBackup() {
  await run(async () => {
    const buttons = [$('full-backup-btn'),$('full-backup-home')];
    buttons.forEach((button) => { button.disabled = true; button.textContent = 'Generando copia...'; });
    try {
      const result = await request('/api/postgres/backups',{method:'POST'});
      notice('Copia PostgreSQL creada. Preparando descarga...');
      await download(`/api/postgres/backups/${encodeURIComponent(result.id)}/download`,`${result.id}.dump`);
      notice('Backup completo creado y descargado. Guardalo en un lugar seguro.');
      changePage('backups');
    } finally {
      $('full-backup-btn').textContent = 'Crear backup .dump';
      $('full-backup-home').textContent = 'Crear copia PostgreSQL';
    }
  });
}

// Navigation and global operations.
document.querySelectorAll('.nav-item').forEach((btn) => btn.addEventListener('click', () => changePage(btn.dataset.page)));
$('refresh-btn').addEventListener('click',refresh);
$('open-backups').addEventListener('click',() => changePage('backups'));
$('full-backup-home').addEventListener('click',createPgBackup);
$('full-backup-btn').addEventListener('click',createPgBackup);
$('json-backup-btn').addEventListener('click',() => run(async () => {
  const result = await request('/api/backups',{method:'POST'});
  notice(`Exportacion JSON creada (${result.record_count} registros).`);
}));
$('seed-btn').addEventListener('click',() => run(async () => {
  await request('/api/seed',{method:'POST'});
  notice('Se agregaron 4 registros de ejemplo.');
}));
$('cancel-edit-btn').addEventListener('click',clearForm);
$('record-form').addEventListener('submit',(event) => {
  event.preventDefault();
  const id = $('record-id').value;
  const payload = {name:$('record-name').value.trim(),category:$('record-category').value.trim(),quantity:Number($('record-quantity').value)};
  run(async () => {
    await request(id ? `/api/records/${encodeURIComponent(id)}` : '/api/records', {method:id ? 'PUT' : 'POST',body:JSON.stringify(payload)});
    clearForm(); notice(id ? 'Registro actualizado.' : 'Registro guardado.');
  });
});
$('records-body').addEventListener('click',(event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.edit) {
    const row = cachedRecords.find((record) => String(record.id) === button.dataset.edit);
    if (!row) return;
    $('record-id').value = row.id;
    $('record-name').value = row.name;
    $('record-category').value = row.category;
    $('record-quantity').value = row.quantity;
    $('record-form-title').textContent = `Editar registro #${row.id}`;
    $('save-record-btn').textContent = 'Guardar cambios';
    $('cancel-edit-btn').classList.remove('hidden');
    $('record-form').scrollIntoView({behavior:'smooth'});
  }
  if (button.dataset.delete && confirm(`Eliminar el registro #${button.dataset.delete}?`)) {
    run(async () => {
      await request(`/api/records/${encodeURIComponent(button.dataset.delete)}`,{method:'DELETE'});
      notice('Registro eliminado.');
    });
  }
});
$('full-backups-body').addEventListener('click',(event) => {
  const button = event.target.closest('button'); if (!button) return;
  const id = button.dataset.pgDownload || button.dataset.pgVerify || button.dataset.pgRestore;
  if (!id) return;
  if (button.dataset.pgDownload) return run(async () => { await download(`/api/postgres/backups/${encodeURIComponent(id)}/download`,`${id}.dump`); notice('Archivo descargado.'); });
  if (button.dataset.pgVerify) return run(async () => {
    await request(`/api/postgres/backups/${encodeURIComponent(id)}/verify`,{method:'POST'});
    notice('Integridad SHA-256 y estructura del dump verificadas.');
  });
  if (button.dataset.pgRestore && confirm('Restaurar esta copia en la BASE DE PRUEBA separada? Se reemplazara su contenido. La base principal no se modificara.')) {
    return run(async () => {
      const output = await request(`/api/postgres/backups/${encodeURIComponent(id)}/restore-test`,{method:'POST'});
      notice(`Restauracion de prueba correcta: ${output.restored_rows} registros en la base separada.`);
    });
  }
});
$('backups-body').addEventListener('click',(event) => {
  const button = event.target.closest('button'); if (!button) return;
  const id = button.dataset.jsonDownload || button.dataset.jsonRestore;
  if (!id) return;
  if (button.dataset.jsonDownload) return run(async () => { await download(`/api/backups/${encodeURIComponent(id)}/download`,`${id}.json`); notice('Archivo JSON descargado.'); });
  if (button.dataset.jsonRestore && confirm('Esta operacion REEMPLAZA la tabla records por el contenido del JSON. Continuar?')) {
    return run(async () => {
      const result = await request(`/api/backups/${encodeURIComponent(id)}/restore`,{method:'POST'});
      notice(`Tabla restaurada: ${result.restored} registros.`);
      changePage('records');
    });
  }
});
refresh();
