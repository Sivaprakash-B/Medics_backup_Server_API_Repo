/* ═══════════════════════════════════════════════════════════════
   SEF Database API — Dynamic MySQL Read-Only Dashboard & SQL Engine
   ═══════════════════════════════════════════════════════════════ */

const API = window.location.origin;
const state = {
  token: localStorage.getItem('sef_token') || null,
  user: JSON.parse(localStorage.getItem('sef_user') || 'null'),
  currentPage: 'overview',
  tablesList: [],       // [{id, column_count, columns}]
  selectedTableId: null, // numeric ID only — no table name stored
  tableData: [],
  tableColumns: [],
  schema: [],
  stats: {},
  codeLang: 'curl',
  sqlData: [],
  sqlColumns: [],
};

/* ── Helpers ──────────────────────────────────────────────── */
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function headers() {
  const h = { 'Content-Type': 'application/json' };
  if (state.token) h['Authorization'] = `Bearer ${state.token}`;
  return h;
}

let isAuthRefreshing = false;

async function api(path, opts = {}) {
  const url = path.startsWith('http') ? path : `${API}${path}`;
  let res = await fetch(url, { headers: headers(), ...opts }).catch(err => {
    console.error('Fetch error:', err);
    return { ok: false, status: 0, json: async () => null };
  });

  if (res.status === 401 && !path.includes('/auth/token') && !path.includes('/auth/guest-token')) {
    if (!isAuthRefreshing) {
      isAuthRefreshing = true;
      console.warn('Auth token expired. Auto-authenticating guest session...');
      const renewed = await autoGuestAuth();
      isAuthRefreshing = false;
      if (renewed) {
        res = await fetch(url, { headers: headers(), ...opts }).catch(() => res);
      }
    }
  }

  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

async function autoGuestAuth() {
  try {
    const res = await fetch(`${API}/auth/guest-token`);
    if (res.ok) {
      const data = await res.json();
      if (data?.access_token) {
        state.token = data.access_token;
        state.user = { username: 'guest', role: 'viewer' };
        localStorage.setItem('sef_token', state.token);
        localStorage.setItem('sef_user', JSON.stringify(state.user));
        renderUserInfo();
        return true;
      }
    }
  } catch (e) {
    console.error('Auto guest auth error:', e);
  }
  return false;
}

function toast(msg, type = 'info') {
  const container = $('#toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

/* ── Auth ─────────────────────────────────────────────────── */
async function login() {
  const username = $('#login-username')?.value?.trim() || 'guest';
  const password = $('#login-password')?.value || 'guest';

  if ($('#login-btn')) {
    $('#login-btn').disabled = true;
    $('#login-btn').innerHTML = '<span class="spinner"></span>';
  }
  if ($('#login-error')) $('#login-error').classList.remove('visible');

  const { ok, data } = await api('/auth/token', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });

  if (ok && data?.access_token) {
    state.token = data.access_token;
    try {
      const payload = JSON.parse(atob(data.access_token.split('.')[1]));
      state.user = { username: payload.sub, role: payload.role };
    } catch { state.user = { username, role: 'viewer' }; }

    localStorage.setItem('sef_token', state.token);
    localStorage.setItem('sef_user', JSON.stringify(state.user));
    await enterDashboard();
  } else {
    if ($('#login-error')) {
      $('#login-error').textContent = data?.detail || 'Login failed';
      $('#login-error').classList.add('visible');
    }
  }
  if ($('#login-btn')) {
    $('#login-btn').disabled = false;
    $('#login-btn').textContent = 'Explore Database & Query Engine';
  }
}

async function quickLogin(username, password) {
  if ($('#login-username')) $('#login-username').value = username;
  if ($('#login-password')) $('#login-password').value = password;
  await login();
}

function logout() {
  state.token = null;
  state.user = null;
  localStorage.removeItem('sef_token');
  localStorage.removeItem('sef_user');
  $('#login-screen')?.classList.remove('hidden');
  updateConnectionBadge(false);
}

async function enterDashboard() {
  $('#login-screen')?.classList.add('hidden');
  renderUserInfo();
  const loaded = await loadTablesList();
  if (!loaded && !state.token) {
    const ok = await autoGuestAuth();
    if (ok) await loadTablesList();
  }
  navigate(state.currentPage || 'overview');
}

function renderUserInfo() {
  if (!state.user) return;
  const initials = state.user.username.slice(0, 2).toUpperCase();
  if ($('#user-avatar')) $('#user-avatar').textContent = initials;
  if ($('#user-name')) $('#user-name').textContent = state.user.username;
  if ($('#user-role')) $('#user-role').textContent = state.user.role;
}

function updateConnectionBadge(connected) {
  const badge = $('#connection-badge');
  if (!badge) return;
  if (connected) {
    badge.className = 'status-badge online';
    badge.textContent = 'Connected';
  } else {
    badge.className = 'status-badge';
    badge.textContent = 'Disconnected';
    badge.style.background = 'var(--danger-subtle)';
    badge.style.color = 'var(--danger)';
  }
}

/* ── Navigation ───────────────────────────────────────────── */
function navigate(page) {
  state.currentPage = page;
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  $$('.page-section').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));

  const titles = {
    overview: 'Overview',
    'table-directory': 'Table Directory & ID Mapping',
    data: 'Table Data Viewer',
    'sql-query': 'SQL Query Console',
    'api-builder': 'REST API Endpoint Generator & Code',
    schema: 'Schema Visualizer',
    users: 'User & Permission Manager',
  };
  if ($('#topbar-title')) $('#topbar-title').textContent = titles[page] || 'Dashboard';

  if (page === 'overview') loadStats();
  if (page === 'table-directory') renderTableDirectory();
  if (page === 'data') loadSelectedTableData();
  if (page === 'sql-query' && $('#sql-editor') && !$('#sql-editor').value) {
    $('#sql-editor').value = 'SELECT * FROM rpt_patient_details LIMIT 20';
  }
  if (page === 'api-builder') updateApiGenerator();
  if (page === 'schema') loadSchema();
  if (page === 'users') loadUsersManagement();
}

/* ── Tables & Stats ───────────────────────────────────────── */
async function loadTablesList() {
  const { ok, data } = await api('/api/v1/tables');
  if (ok && data?.tables && data.tables.length > 0) {
    state.tablesList = data.tables;  // [{id, name, column_count, columns}]
    populateAllTableSelects();
    renderTableDirectory();
    updateConnectionBadge(true);

    if (!state.selectedTableId || !state.tablesList.some(t => t.id === state.selectedTableId)) {
      state.selectedTableId = state.tablesList[0].id;
    }
    syncTableSelectors(state.selectedTableId);

    if (state.currentPage === 'data') {
      loadSelectedTableData();
    } else if (state.currentPage === 'api-builder') {
      updateApiGenerator();
    }
    return true;
  } else {
    updateConnectionBadge(false);
    return false;
  }
}

function populateAllTableSelects() {
  if (!state.tablesList || state.tablesList.length === 0) return;

  // Options for Select by Table Name
  const nameOptions = state.tablesList.map(t =>
    `<option value="${escapeHtml(t.name)}">🗄️ ${escapeHtml(t.name)}  (ID: #${t.id})</option>`
  ).join('');

  // Options for Select by Table ID
  const idOptions = state.tablesList.map(t =>
    `<option value="${t.id}">🏷️ Table #${t.id} — ${escapeHtml(t.name)} (${t.column_count || 0} cols)</option>`
  ).join('');

  // Table Viewer Selects
  const dataSelectName = $('#table-select-name');
  if (dataSelectName) dataSelectName.innerHTML = nameOptions;

  const dataSelectId = $('#table-select-id');
  if (dataSelectId) dataSelectId.innerHTML = idOptions;

  // API Generator Selects
  const apiSelectName = $('#api-table-select-name');
  if (apiSelectName) apiSelectName.innerHTML = nameOptions;

  const apiSelectId = $('#api-table-select-id');
  if (apiSelectId) apiSelectId.innerHTML = idOptions;

  if (state.selectedTableId) {
    syncTableSelectors(state.selectedTableId);
  }
}

/* ── Synchronize Dual Selectors (Table Name ⇄ Table ID) ───── */
function syncTableSelectors(tableId) {
  const numId = parseInt(tableId, 10);
  const table = state.tablesList.find(t => t.id === numId);
  if (!table) return;

  state.selectedTableId = numId;

  // Sync Table Viewer selectors
  if ($('#table-select-name')) $('#table-select-name').value = table.name;
  if ($('#table-select-id')) $('#table-select-id').value = table.id;

  // Sync Table Viewer Badge
  const dataBadge = $('#table-viewer-sync-badge');
  if (dataBadge) {
    dataBadge.innerHTML = `Active: <strong style="color:#fff;">${escapeHtml(table.name)}</strong> ⇄ <strong style="color:#818cf8;">Table #${table.id}</strong> (${table.column_count || 0} cols)`;
  }

  // Sync API Generator selectors
  if ($('#api-table-select-name')) $('#api-table-select-name').value = table.name;
  if ($('#api-table-select-id')) $('#api-table-select-id').value = table.id;

  // Sync API Generator Info Pill
  if ($('#api-indicator-name')) $('#api-indicator-name').textContent = table.name;
  if ($('#api-indicator-id')) $('#api-indicator-id').textContent = `Table #${table.id}`;
  if ($('#api-indicator-cols')) $('#api-indicator-cols').textContent = `${table.column_count || 0} columns`;
}

function onTableNameChanged(tableName, context) {
  const table = state.tablesList.find(t => t.name === tableName);
  if (!table) return;
  syncTableSelectors(table.id);
  if (context === 'data') {
    loadSelectedTableData();
  } else if (context === 'api') {
    updateApiGenerator();
  }
}

function onTableIdChanged(tableId, context) {
  const numId = parseInt(tableId, 10);
  const table = state.tablesList.find(t => t.id === numId);
  if (!table) return;
  syncTableSelectors(numId);
  if (context === 'data') {
    loadSelectedTableData();
  } else if (context === 'api') {
    updateApiGenerator();
  }
}

/* ── Table Directory & ID Mapping Table ───────────────────── */
let currentDirectoryCategory = 'all';

function renderTableDirectory() {
  const tbody = $('#directory-tbody');
  if (!tbody) return;

  if (!state.tablesList || state.tablesList.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><p>No tables loaded</p></div></td></tr>';
    return;
  }

  const search = ($('#directory-search')?.value || '').toLowerCase().trim();

  let filtered = state.tablesList.filter(t => {
    // Search filter
    const matchesSearch = !search ||
      t.name.toLowerCase().includes(search) ||
      `#${t.id}`.includes(search) ||
      `table #${t.id}`.includes(search) ||
      String(t.id) === search;

    // Category filter
    let matchesCat = true;
    if (currentDirectoryCategory === 'rpt') {
      matchesCat = t.name.startsWith('rpt_');
    } else if (currentDirectoryCategory === 'master') {
      matchesCat = t.name.startsWith('u_') || !t.name.startsWith('rpt_');
    }

    return matchesSearch && matchesCat;
  });

  if ($('#directory-total-badge')) {
    $('#directory-total-badge').textContent = `${filtered.length} of ${state.tablesList.length} Tables`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">🔍</div><p>No tables matching "${escapeHtml(search)}"</p></div></td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(t => {
    const isReport = t.name.startsWith('rpt_');
    const categoryBadge = isReport
      ? '<span class="badge" style="background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(245,158,11,0.3);">📊 Report Table</span>'
      : '<span class="badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.3);">🗂️ Master Table</span>';

    const apiEndpoint = `/api/v1/${t.id}`;

    return `
      <tr>
        <td>
          <span class="badge status-2xx" style="font-family:var(--font-mono); font-size:0.85rem; font-weight:700;">
            #${t.id}
          </span>
        </td>
        <td>
          <strong style="font-family:var(--font-mono); color:var(--text-primary); font-size:0.9rem;">
            ${escapeHtml(t.name)}
          </strong>
        </td>
        <td>${categoryBadge}</td>
        <td>
          <span class="text-muted" style="font-family:var(--font-mono); font-size:0.82rem;">
            ${t.column_count || 0} cols
          </span>
        </td>
        <td>
          <code style="background:#070b18; color:#818cf8; padding:3px 8px; border-radius:4px; font-size:0.8rem; border:1px solid var(--border-medium);">
            ${apiEndpoint}
          </code>
        </td>
        <td style="text-align:right;">
          <div style="display:inline-flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="openTableInDataViewer(${t.id})" title="View table records">
              📂 View Data
            </button>
            <button class="btn btn-primary btn-sm" onclick="openTableInApiBuilder(${t.id})" title="Generate REST API Endpoint">
              ⚡ Build API
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterTableDirectory() {
  renderTableDirectory();
}

function filterDirectoryCategory(cat) {
  currentDirectoryCategory = cat;
  renderTableDirectory();
}

function openTableInDataViewer(tableId) {
  syncTableSelectors(tableId);
  navigate('data');
}

function openTableInApiBuilder(tableId) {
  syncTableSelectors(tableId);
  navigate('api-builder');
}

async function loadStats() {
  const { ok, data } = await api('/api/v1/system/stats');
  if (!ok || !data) {
    updateConnectionBadge(false);
    return;
  }
  state.stats = data;
  const tableCount = data.table_count ?? state.tablesList.length ?? 0;
  if ($('#stat-tables')) $('#stat-tables').textContent = tableCount;
  if ($('#stat-users')) $('#stat-users').textContent = data.user_count ?? 0;
  if ($('#stat-reports')) $('#stat-reports').textContent = data.report_count ?? 0;
  if ($('#stat-engine')) $('#stat-engine').textContent = data.database_engine ?? 'MySQL';
  if ($('#stat-db-info')) $('#stat-db-info').textContent = data.database_url_masked ?? '';
  if ($('#overview-db-name')) $('#overview-db-name').textContent = data.database_name || 'medics_report_db';
  updateConnectionBadge(true);
}

/* ── Dynamic Table Viewer ─────────────────────────────────── */
async function loadSelectedTableData() {
  if (!state.tablesList || state.tablesList.length === 0) {
    await loadTablesList();
  }

  if (!state.selectedTableId && state.tablesList && state.tablesList.length > 0) {
    state.selectedTableId = state.tablesList[0].id;
  }

  if (!state.selectedTableId) {
    if ($('#data-tbody')) {
      $('#data-tbody').innerHTML = '<tr><td colspan="100%"><div class="empty-state"><p>No table selected</p></div></td></tr>';
    }
    return;
  }

  syncTableSelectors(state.selectedTableId);

  if ($('#data-tbody')) {
    $('#data-tbody').innerHTML = `<tr><td colspan="100%"><div class="empty-state"><span class="spinner" style="width:24px;height:24px;border-width:3px;margin-bottom:8px;"></span><p>Loading records for Table #${state.selectedTableId}…</p></div></td></tr>`;
  }

  const search = $('#data-search')?.value || '';
  const url = `/api/v1/tables/${state.selectedTableId}/data?limit=50${search ? '&search=' + encodeURIComponent(search) : ''}`;

  const { ok, data } = await api(url);
  if (!ok) {
    if ($('#data-tbody')) {
      $('#data-tbody').innerHTML = `<tr><td colspan="100%"><div class="empty-state" style="color:var(--danger);"><div class="empty-icon">⚠️</div><p>Failed to load records for Table #${state.selectedTableId}</p></div></td></tr>`;
    }
    toast(`Failed to load Table #${state.selectedTableId}`, 'error');
    return;
  }

  state.tableData = data.data || [];
  state.tableColumns = data.columns || [];
  renderDynamicTable(data.total, data.table_name);
}

function renderDynamicTable(totalCount, tableName) {
  const columns = state.tableColumns;
  const rows = state.tableData;

  const thead = $('#data-thead');
  const tbody = $('#data-tbody');

  const currentTable = state.tablesList.find(t => t.id === state.selectedTableId);
  const nameToDisplay = tableName || currentTable?.name || `Table #${state.selectedTableId}`;

  if (columns.length === 0) {
    thead.innerHTML = '';
    tbody.innerHTML = `<tr><td><div class="empty-state"><p>No columns found</p></div></td></tr>`;
    return;
  }

  const displayCols = columns.slice(0, 7);

  thead.innerHTML = `<tr>
    ${displayCols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}
    <th>Details</th>
  </tr>`;

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${displayCols.length + 1}"><div class="empty-state"><div class="empty-icon">📭</div><p>No records in ${escapeHtml(nameToDisplay)} (Table #${state.selectedTableId})</p></div></td></tr>`;
  } else {
    tbody.innerHTML = rows.map((row, idx) => `<tr>
      ${displayCols.map(c => {
        const val = row[c];
        const valStr = val === null ? '<span class="text-muted">NULL</span>' : escapeHtml(String(val));
        return `<td class="truncate" style="max-width:200px;">${valStr}</td>`;
      }).join('')}
      <td><button class="btn-icon" onclick="viewRowDetail(${idx})" title="View Full Record Details">👁️</button></td>
    </tr>`).join('');
  }

  $('#data-count').textContent = `${totalCount ?? rows.length} record(s) in ${nameToDisplay}`;
}

/* ── SQL Query Console ────────────────────────────────────── */
async function runSqlQuery() {
  const sql = $('#sql-editor')?.value?.trim();
  if (!sql) { toast('Please enter an SQL query', 'warning'); return; }

  $('#run-sql-btn').disabled = true;
  $('#run-sql-btn').innerHTML = '<span class="spinner"></span> Running...';

  const { ok, data } = await api('/api/v1/query', {
    method: 'POST',
    body: JSON.stringify({ sql }),
  });

  if (ok && data) {
    state.sqlColumns = data.columns || [];
    state.sqlData = data.data || [];
    renderSqlResults(data.row_count);
    toast(`Query executed successfully (${data.row_count} rows)`, 'success');
  } else {
    const errorMsg = data?.detail || 'Query execution error';
    $('#sql-tbody').innerHTML = `<tr><td colspan="100%"><div class="empty-state" style="color:var(--danger);"><div class="empty-icon">⚠️</div><p>${escapeHtml(errorMsg)}</p></div></td></tr>`;
    $('#sql-result-count').textContent = '0 rows';
    toast(errorMsg, 'error');
  }

  $('#run-sql-btn').disabled = false;
  $('#run-sql-btn').innerHTML = '▶ Run SQL Query';
}

function renderSqlResults(rowCount) {
  const columns = state.sqlColumns;
  const rows = state.sqlData;

  const thead = $('#sql-thead');
  const tbody = $('#sql-tbody');

  $('#sql-result-count').textContent = `${rowCount ?? rows.length} row(s)`;

  if (columns.length === 0) {
    thead.innerHTML = '';
    tbody.innerHTML = '<tr><td colspan="100%"><div class="empty-state"><p>No return columns</p></div></td></tr>';
    return;
  }

  const displayCols = columns.slice(0, 8);

  thead.innerHTML = `<tr>${displayCols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>`;

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="${displayCols.length}"><div class="empty-state"><div class="empty-icon">📭</div><p>Query returned 0 rows</p></div></td></tr>`;
  } else {
    tbody.innerHTML = rows.map(row => `<tr>
      ${displayCols.map(c => {
        const val = row[c];
        const valStr = val === null ? '<span class="text-muted">NULL</span>' : escapeHtml(String(val));
        return `<td class="truncate" style="max-width:220px;">${valStr}</td>`;
      }).join('')}
    </tr>`).join('');
  }
}

/* ── API Generator & Code Snippet Studio ──────────────────── */
function updateApiGenerator() {
  const tableId = parseInt($('#api-table-select-id')?.value, 10) || state.selectedTableId || state.tablesList[0]?.id;
  if (!tableId) return;

  syncTableSelectors(tableId);

  const search = $('#api-search')?.value?.trim();
  const where  = $('#api-where')?.value?.trim();
  const limit  = $('#api-limit')?.value?.trim();
  const skip   = $('#api-skip')?.value?.trim();

  let params = [];
  if (search) params.push(`search=${encodeURIComponent(search)}`);
  if (where)  params.push(`where=${encodeURIComponent(where)}`);   // encode SQL conditions properly
  if (limit)  params.push(`limit=${encodeURIComponent(limit)}`);
  if (skip)   params.push(`skip=${encodeURIComponent(skip)}`);

  const queryString = params.length > 0 ? `?${params.join('&')}` : '';
  // ✅ Fixed: correct path is /api/v1/tables/{id}/data
  const endpointPath = `/api/v1/tables/${tableId}/data${queryString}`;
  const fullUrl = `${API}${endpointPath}`;

  if ($('#generated-api-url')) $('#generated-api-url').value = fullUrl;
  generateCodeSnippet(fullUrl, endpointPath);
}


function generateCodeSnippet(fullUrl, endpointPath) {
  const tokenHeader = state.token ? `Authorization: Bearer ${state.token}` : '';
  const lang = state.codeLang;

  let code = '';
  if (lang === 'curl') {
    code = `curl -X GET "${fullUrl}" \\
  -H "Accept: application/json"${tokenHeader ? ` \\\n  -H "${tokenHeader}"` : ''}`;
  } else if (lang === 'python') {
    code = `import requests

url = "${fullUrl}"
headers = {
    "Accept": "application/json",
${tokenHeader ? `    "Authorization": "Bearer ${state.token}"\n` : ''}}

response = requests.get(url, headers=headers)
data = response.json()
print("Total records:", data.get("total"))
print("Rows:", data.get("data"))`;
  } else if (lang === 'js') {
    code = `const url = "${fullUrl}";

fetch(url, {
  method: "GET",
  headers: {
    "Accept": "application/json",
${tokenHeader ? `    "Authorization": "Bearer ${state.token}"\n` : ''}  }
})
  .then(res => res.json())
  .then(data => {
    console.log("Table records:", data.data);
  });`;
  } else if (lang === 'php') {
    code = `<?php
$url = "${fullUrl}";
$opts = [
    "http" => [
        "method" => "GET",
        "header" => "Accept: application/json\\r\\n"${tokenHeader ? ` . "Authorization: Bearer ${state.token}\\r\\n"` : ''}
    ]
];
$context = stream_context_create($opts);
$response = file_get_contents($url, false, $context);
$data = json_decode($response, true);

print_r($data["data"]);
?>`;
  }

  if ($('#code-snippet-box')) $('#code-snippet-box').value = code;
}

async function testGeneratedApi() {
  const url = $('#generated-api-url')?.value;
  if (!url) return;

  $('#test-api-btn').disabled = true;
  $('#test-api-btn').innerHTML = '<span class="spinner"></span> Testing...';

  const start = performance.now();
  const { ok, status, data } = await api(url);
  const ms = Math.round(performance.now() - start);

  const statusBadge = $('#api-response-status');
  if (statusBadge) {
    statusBadge.textContent = `${status} ${ok ? 'OK' : 'Error'} (${ms}ms)`;
    statusBadge.className = `badge ${ok ? 'status-2xx' : 'status-4xx'}`;
  }

  if ($('#api-test-response')) {
    $('#api-test-response').textContent = JSON.stringify(data, null, 2);
  }

  $('#test-api-btn').disabled = false;
  $('#test-api-btn').innerHTML = '▶ Test Endpoint';
}

/* ── View Row Detail Modal ────────────────────────────────── */
function viewRowDetail(index) {
  const row = state.tableData[index];
  if (!row) return;

  $('#modal-title').textContent = `Record Detail — Table #${state.selectedTableId}`;
  $('#modal-body').innerHTML = `
    <div class="detail-grid" style="max-height:60vh; overflow-y:auto; padding-right:8px;">
      ${Object.entries(row).map(([k, v]) => `
        <div class="detail-row" style="align-items:flex-start;">
          <span class="detail-label" style="min-width:160px; font-family:var(--font-mono);">${escapeHtml(k)}</span>
          <span class="detail-value" style="font-family:var(--font-mono); word-break:break-all;">
            ${v === null ? '<em class="text-muted">NULL</em>' : escapeHtml(String(v))}
          </span>
        </div>
      `).join('')}
    </div>
  `;
  $('#modal-footer').innerHTML = '<button class="btn btn-secondary" onclick="closeModal()">Close</button>';
  openModal();
}

/* ── Schema Visualizer ────────────────────────────────────── */
async function loadSchema() {
  const container = $('#schema-container');
  if (container) {
    container.innerHTML = '<div class="empty-state"><span class="spinner" style="width:28px;height:28px;border-width:3px;margin-bottom:12px;"></span><p>Loading schema inspection…</p></div>';
  }
  const { ok, data } = await api('/api/v1/system/schema');
  if (!ok) {
    if (container) container.innerHTML = '<div class="empty-state" style="color:var(--danger);"><div class="empty-icon">⚠️</div><p>Failed to load schema</p></div>';
    return;
  }
  state.schema = data.tables || [];
  renderSchema();
}

function renderSchema() {
  const container = $('#schema-container');
  if (state.schema.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">🗄️</div><p>No tables found</p></div>';
    return;
  }
  container.innerHTML = state.schema.map(t => `
    <div class="schema-table-card">
      <div class="table-name">🗃️ ${escapeHtml(t.name)}</div>
      <div class="col-list">
        ${t.columns.map(c => `
          <div class="schema-col">
            <span class="col-name">${escapeHtml(c.name)}</span>
            <span class="col-type">${escapeHtml(c.type)}</span>
            ${c.primary_key ? '<span class="col-pk">PK</span>' : ''}
            <span class="col-nullable">${c.nullable ? 'nullable' : 'NOT NULL'}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

/* ── User & Permission Management ─────────────────────────── */
async function loadUsersManagement() {
  const { ok, data } = await api('/auth/users-list');
  if (!ok) return;
  renderUsersTable(data.users || []);
}

function renderUsersTable(users) {
  const tbody = $('#user-mgmt-tbody');
  if (!tbody) return;

  if (users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><p>No user accounts configured</p></div></td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => {
    const isAll = u.allowed_tables.includes('*');
    const tableBadges = isAll
      ? '<span class="badge status-2xx">All Tables (*)</span>'
      : u.allowed_tables.map(t => `<span class="badge" style="background:var(--bg-card); color:var(--text-primary); border:1px solid var(--border-medium); margin-right:4px; font-family:var(--font-mono);">${escapeHtml(t)}</span>`).join('');

    const isSystem = (u.username === 'admin' || u.username === 'guest');
    const editBtn = `<button class="btn btn-secondary btn-sm" onclick="openEditUserModal('${escapeHtml(u.username)}')">✏️ Edit</button>`;
    const deleteBtn = isSystem
      ? '<span class="text-muted" style="font-size:0.75rem; margin-left:6px;">(System Account)</span>'
      : `<button class="btn btn-secondary btn-sm" style="color:var(--danger); margin-left:4px;" onclick="deleteUserAccount('${escapeHtml(u.username)}')">🗑 Delete</button>`;

    return `
      <tr>
        <td style="font-weight:600; font-family:var(--font-mono);">${escapeHtml(u.username)}</td>
        <td><span class="badge ${u.role === 'admin' ? 'status-2xx' : ''}">${escapeHtml(u.role)}</span></td>
        <td>${tableBadges}</td>
        <td>${editBtn} ${deleteBtn}</td>
      </tr>
    `;
  }).join('');
}

async function getAllDatabaseTableIds() {
  // Returns numeric IDs only — never real table names
  if (state.tablesList && state.tablesList.length > 0) {
    return state.tablesList.map(t => t.id);
  }
  const { ok, data } = await api('/api/v1/tables');
  if (ok && data?.tables) {
    state.tablesList = data.tables;
    return state.tablesList.map(t => t.id);
  }
  return [];
}

async function openAddUserModal() {
  $('#modal-title').textContent = '➕ Add New User with Table Permissions';
  const allTableIds = await getAllDatabaseTableIds();

  $('#modal-body').innerHTML = `
    <div style="display:flex; flex-direction:column; gap:var(--space-md);">
      <div class="form-group">
        <label>Username:</label>
        <input class="form-input" id="new-username" placeholder="e.g. user3" />
      </div>
      <div class="form-group">
        <label>Password:</label>
        <input class="form-input" id="new-password" type="password" placeholder="Set password for account" />
      </div>
      <div class="form-group">
        <label>Allowed Tables (comma-separated numeric IDs or * for all):</label>
        <input class="form-input" id="new-tables" value="*" placeholder="e.g. 1, 3, 7" style="font-family:var(--font-mono);" />
        <span class="text-muted" style="font-size:0.75rem; margin-top:4px; display:block;">Enter Table IDs separated by commas, or click the buttons below. Use * to allow all.</span>
      </div>
      <div class="form-group">
        <label>Quick Select Available Tables (${state.tablesList.length} total):</label>
        <div style="display:flex; flex-wrap:wrap; gap:6px; max-height:140px; overflow-y:auto; padding:8px; background:#070b18; border-radius:var(--radius-sm); border:1px solid var(--border-medium);">
          <button class="btn btn-secondary btn-sm" onclick="setTablesInputValue('new-tables', '*')" style="font-size:0.75rem;">🌟 All Tables (*)</button>
          ${state.tablesList.map(t => `<button class="btn btn-secondary btn-sm" onclick="appendTablesInputValue('new-tables', '${t.id}')" style="font-size:0.75rem; font-family:var(--font-mono);">${escapeHtml(t.name)} (#${t.id})</button>`).join('')}
        </div>
      </div>
    </div>
  `;
  $('#modal-footer').innerHTML = `
    <button class="btn btn-primary" onclick="saveNewUser()">💾 Save User Account</button>
    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
  `;
  openModal();
}

async function openEditUserModal(username) {
  const { ok, data } = await api('/auth/users-list');
  if (!ok) return;
  const userObj = (data.users || []).find(u => u.username === username);
  if (!userObj) {
    toast(`User '${username}' not found`, 'error');
    return;
  }

  await loadTablesList();
  const currentTablesStr = userObj.allowed_tables.join(', ');

  $('#modal-title').textContent = `✏️ Edit User Permissions: ${userObj.username}`;
  $('#modal-body').innerHTML = `
    <div style="display:flex; flex-direction:column; gap:var(--space-md);">
      <div class="form-group">
        <label>Username:</label>
        <input class="form-input" id="edit-username" value="${escapeHtml(userObj.username)}" readonly style="opacity:0.7; font-family:var(--font-mono);" />
      </div>
      <div class="form-group">
        <label>New Password (optional):</label>
        <input class="form-input" id="edit-password" type="password" placeholder="Leave blank to keep existing password" />
      </div>
      <div class="form-group">
        <label>Allowed Tables (comma-separated numeric IDs or * for all):</label>
        <input class="form-input" id="edit-tables" value="${escapeHtml(currentTablesStr)}" placeholder="e.g. 1, 3, 7" style="font-family:var(--font-mono);" />
        <span class="text-muted" style="font-size:0.75rem; margin-top:4px; display:block;">Enter Table IDs separated by commas, or <code>*</code> for all tables.</span>
      </div>
      <div class="form-group">
        <label>Quick Select Available Tables (${state.tablesList.length} total):</label>
        <div style="display:flex; flex-wrap:wrap; gap:6px; max-height:140px; overflow-y:auto; padding:8px; background:#070b18; border-radius:var(--radius-sm); border:1px solid var(--border-medium);">
          <button class="btn btn-secondary btn-sm" onclick="setTablesInputValue('edit-tables', '*')" style="font-size:0.75rem;">🌟 All Tables (*)</button>
          ${state.tablesList.map(t => `<button class="btn btn-secondary btn-sm" onclick="appendTablesInputValue('edit-tables', '${t.id}')" style="font-size:0.75rem; font-family:var(--font-mono);">${escapeHtml(t.name)} (#${t.id})</button>`).join('')}
        </div>
      </div>
    </div>
  `;

  $('#modal-footer').innerHTML = `
    <button class="btn btn-primary" onclick="saveEditedUser()">💾 Update User Account</button>
    <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
  `;
  openModal();
}

function setTablesInputValue(inputId, val) {
  const input = $(`#${inputId}`);
  if (input) input.value = val;
}

function appendTablesInputValue(inputId, tableName) {
  const input = $(`#${inputId}`);
  if (!input) return;
  const current = input.value.trim();
  if (current === '*' || current === '') {
    input.value = tableName;
  } else {
    const list = current.split(',').map(s => s.trim());
    if (!list.includes(tableName)) {
      list.push(tableName);
      input.value = list.join(', ');
    }
  }
}

async function saveNewUser() {
  const username = $('#new-username')?.value?.trim();
  const password = $('#new-password')?.value?.trim();
  const rawTables = $('#new-tables')?.value?.trim() || '*';

  if (!username || !password) {
    toast('Please enter a username and password', 'error');
    return;
  }

  const allowed_tables = rawTables === '*'
    ? ['*']
    : rawTables.split(',').map(t => t.trim()).filter(Boolean);

  const { ok, data } = await api('/auth/add-user', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password,
      role: 'viewer',
      allowed_tables,
    })
  });

  if (ok) {
    toast(`User '${username}' saved successfully!`, 'success');
    closeModal();
    loadUsersManagement();
  } else {
    toast(data?.detail || 'Failed to save user', 'error');
  }
}

async function saveEditedUser() {
  const username = $('#edit-username')?.value?.trim();
  const password = $('#edit-password')?.value?.trim();
  const rawTables = $('#edit-tables')?.value?.trim() || '*';

  if (!username) return;

  const allowed_tables = rawTables === '*'
    ? ['*']
    : rawTables.split(',').map(t => t.trim()).filter(Boolean);

  const payload = {
    username,
    role: 'viewer',
    allowed_tables,
  };
  if (password) payload.password = password;

  const { ok, data } = await api('/auth/add-user', {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  if (ok) {
    toast(`User '${username}' updated successfully!`, 'success');
    closeModal();
    loadUsersManagement();
  } else {
    toast(data?.detail || 'Failed to update user', 'error');
  }
}

async function deleteUserAccount(username) {
  if (!confirm(`Are you sure you want to delete user account '${username}'?`)) return;

  const { ok, data } = await api(`/auth/delete-user/${encodeURIComponent(username)}`, {
    method: 'DELETE'
  });

  if (ok) {
    toast(`User '${username}' deleted`, 'info');
    loadUsersManagement();
  } else {
    toast(data?.detail || 'Failed to delete user', 'error');
  }
}

/* ── Modal ────────────────────────────────────────────────── */
function openModal()  { $('#modal-overlay').classList.add('visible'); }
function closeModal() { $('#modal-overlay').classList.remove('visible'); }

/* ── Init ─────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Nav
  $$('.nav-item').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.page));
  });

  // Login
  $('#login-btn').addEventListener('click', login);
  $('#login-password').addEventListener('keydown', e => { if (e.key === 'Enter') login(); });
  $('#login-username').addEventListener('keydown', e => { if (e.key === 'Enter') login(); });

  // Logout
  $('#logout-btn').addEventListener('click', logout);

  // User Management
  $('#open-add-user-btn')?.addEventListener('click', openAddUserModal);

  // Table selector change
  $('#table-select')?.addEventListener('change', () => {
    state.selectedTableId = parseInt($('#table-select').value, 10);
    loadSelectedTableData();
  });

  // Search input
  $('#data-search')?.addEventListener('input', () => loadSelectedTableData());

  // SQL Query Console
  $('#run-sql-btn')?.addEventListener('click', runSqlQuery);
  $('#sql-editor')?.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      runSqlQuery();
    }
  });

  // Sample SQL query buttons
  $$('.sample-sql-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if ($('#sql-editor')) {
        $('#sql-editor').value = btn.dataset.sql;
        runSqlQuery();
      }
    });
  });

  // API Generator inputs
  $('#api-table-select')?.addEventListener('change', updateApiGenerator);
  $('#api-limit')?.addEventListener('input', updateApiGenerator);
  $('#api-skip')?.addEventListener('input', updateApiGenerator);
  $('#api-search')?.addEventListener('input', updateApiGenerator);
  $('#api-where')?.addEventListener('input', updateApiGenerator);
  $('#test-api-btn')?.addEventListener('click', testGeneratedApi);

  // Copy buttons
  $('#copy-api-url-btn')?.addEventListener('click', () => {
    const url = $('#generated-api-url')?.value;
    if (url) {
      navigator.clipboard.writeText(url);
      toast('API URL copied to clipboard!', 'success');
    }
  });
  $('#copy-code-btn')?.addEventListener('click', () => {
    const code = $('#code-snippet-box')?.value;
    if (code) {
      navigator.clipboard.writeText(code);
      toast('Code snippet copied to clipboard!', 'success');
    }
  });

  // Code lang switcher
  $$('.tab-btn[data-lang]').forEach(b => {
    b.addEventListener('click', () => {
      $$('.tab-btn[data-lang]').forEach(el => el.classList.remove('active'));
      b.classList.add('active');
      state.codeLang = b.dataset.lang;
      updateApiGenerator();
    });
  });

  // Modal close on overlay click
  $('#modal-overlay')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Auto-login or guest login if token exists
  if (state.token && state.user) {
    enterDashboard();
  } else {
    login();
  }
});
