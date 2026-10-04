// State Management
const state = {
  spotify: { configured: false, authenticated: false, profile: null },
  tidal: { authenticated: false, profile: null },
  playlists: [],
  selectedPlaylistIds: new Set(),
  filterQuery: '',
  isTransferring: false,
  eventSource: null,
  tidalPollTimer: null,
  currentTidalUri: null,
};

// DOM Elements
const el = {
  // Status Badges & Profiles
  spotifyStatusBadge: document.getElementById('spotifyStatusBadge'),
  spotifyStatusText: document.getElementById('spotifyStatusText'),
  quickSpotifyUrlInput: document.getElementById('quickSpotifyUrlInput'),
  btnQuickLoadSpotify: document.getElementById('btnQuickLoadSpotify'),
  btnOpenMultiUrlModal: document.getElementById('btnOpenMultiUrlModal'),
  btnSpotifyConfig: document.getElementById('btnSpotifyConfig'),

  tidalStatusBadge: document.getElementById('tidalStatusBadge'),
  tidalStatusText: document.getElementById('tidalStatusText'),
  tidalAvatar: document.getElementById('tidalAvatar'),
  tidalUserName: document.getElementById('tidalUserName'),
  tidalMetaText: document.getElementById('tidalMetaText'),
  btnConnectTidal: document.getElementById('btnConnectTidal'),
  btnTidalLogout: document.getElementById('btnTidalLogout'),

  // Playlists Section
  playlistsSection: document.getElementById('playlistsSection'),
  playlistsSubtitle: document.getElementById('playlistsSubtitle'),
  playlistsGrid: document.getElementById('playlistsGrid'),
  searchInput: document.getElementById('searchInput'),
  btnSelectAll: document.getElementById('btnSelectAll'),
  btnDeselectAll: document.getElementById('btnDeselectAll'),
  selectionCount: document.getElementById('selectionCount'),
  prefixInput: document.getElementById('prefixInput'),

  // Bottom Dock
  bottomDock: document.getElementById('bottomDock'),
  dockCount: document.getElementById('dockCount'),
  btnStartTransfer: document.getElementById('btnStartTransfer'),

  // Modals
  spotifyConfigModal: document.getElementById('spotifyConfigModal'),
  btnCloseSpotifyConfig: document.getElementById('btnCloseSpotifyConfig'),
  btnCancelSpotifyConfig: document.getElementById('btnCancelSpotifyConfig'),
  spotifyConfigForm: document.getElementById('spotifyConfigForm'),
  clientIdInput: document.getElementById('clientIdInput'),
  clientSecretInput: document.getElementById('clientSecretInput'),

  tidalAuthModal: document.getElementById('tidalAuthModal'),
  btnCloseTidalAuth: document.getElementById('btnCloseTidalAuth'),
  tidalCodeDisplay: document.getElementById('tidalCodeDisplay'),
  btnOpenTidalLink: document.getElementById('btnOpenTidalLink'),
  tidalDirectLinkText: document.getElementById('tidalDirectLinkText'),
  btnVerifyTidalNow: document.getElementById('btnVerifyTidalNow'),

  multiUrlModal: document.getElementById('multiUrlModal'),
  btnCloseMultiUrl: document.getElementById('btnCloseMultiUrl'),
  btnCancelMultiUrl: document.getElementById('btnCancelMultiUrl'),
  multiUrlForm: document.getElementById('multiUrlForm'),
  multiUrlTextarea: document.getElementById('multiUrlTextarea'),
  btnSubmitMultiUrl: document.getElementById('btnSubmitMultiUrl'),

  reportModal: document.getElementById('reportModal'),
  btnCloseReport: document.getElementById('btnCloseReport'),
  reportList: document.getElementById('reportList'),
  btnCopyReport: document.getElementById('btnCopyReport'),
  btnDoneReport: document.getElementById('btnDoneReport'),

  // Live Transfer Overlay
  transferOverlay: document.getElementById('transferOverlay'),
  transferModalTitle: document.getElementById('transferModalTitle'),
  btnCancelTransfer: document.getElementById('btnCancelTransfer'),
  plProgressLabel: document.getElementById('plProgressLabel'),
  plPercentLabel: document.getElementById('plPercentLabel'),
  plProgressBar: document.getElementById('plProgressBar'),
  trackProgressLabel: document.getElementById('trackProgressLabel'),
  matchStatsLabel: document.getElementById('matchStatsLabel'),
  trackProgressBar: document.getElementById('trackProgressBar'),
  tickerSong: document.getElementById('tickerSong'),
  tickerArtist: document.getElementById('tickerArtist'),
  eventFeed: document.getElementById('eventFeed'),
  btnViewReport: document.getElementById('btnViewReport'),
  btnCloseTransferModal: document.getElementById('btnCloseTransferModal'),
  eqAnim: document.getElementById('eqAnim'),
};

// Initial App Boot
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  await refreshAppStatus();

  const params = new URLSearchParams(window.location.search);
  if (params.get('spotify_connected')) {
    showNotification('Spotify conectado exitosamente', 'success');
    window.history.replaceState({}, document.title, window.location.pathname);
  } else if (params.get('spotify_error')) {
    showNotification(`Error: ${params.get('spotify_error')}`, 'error');
    window.history.replaceState({}, document.title, window.location.pathname);
  }
});

// Setup Event Listeners
function setupEventListeners() {
  // Quick Spotify URL Loader
  el.btnQuickLoadSpotify.addEventListener('click', onQuickSpotifyLoad);
  el.quickSpotifyUrlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onQuickSpotifyLoad();
    }
  });

  // File Upload (CSV/TXT)
  const fileInput = document.getElementById('filePlaylistInput');
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      showNotification('Procesando archivo...', 'info');
      try {
        const res = await fetch('/api/spotify/upload-file', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.success && data.playlist) {
          state.playlists.unshift(data.playlist);
          state.selectedPlaylistIds.add(data.playlist.id);
          showNotification(data.message, 'success');
          renderPlaylists();
        } else {
          alert(data.detail || 'Error procesando archivo.');
        }
      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        fileInput.value = '';
      }
    });
  }

  // Multi-URL Modal
  el.btnOpenMultiUrlModal.addEventListener('click', () => el.multiUrlModal.showModal());
  el.btnCloseMultiUrl.addEventListener('click', () => el.multiUrlModal.close());
  el.btnCancelMultiUrl.addEventListener('click', () => el.multiUrlModal.close());
  el.multiUrlForm.addEventListener('submit', onMultiUrlSubmit);


  // Optional Developer Config Modal
  el.btnSpotifyConfig.addEventListener('click', () => el.spotifyConfigModal.showModal());
  el.btnCloseSpotifyConfig.addEventListener('click', () => el.spotifyConfigModal.close());
  el.btnCancelSpotifyConfig.addEventListener('click', () => el.spotifyConfigModal.close());
  el.spotifyConfigForm.addEventListener('submit', onSpotifyConfigSubmit);

  // Tidal Connection
  el.btnConnectTidal.addEventListener('click', onConnectTidalClick);
  el.btnCloseTidalAuth.addEventListener('click', () => {
    clearInterval(state.tidalPollTimer);
    el.tidalAuthModal.close();
  });
  el.btnTidalLogout.addEventListener('click', onTidalLogout);
  el.btnVerifyTidalNow.addEventListener('click', manualCheckTidalLogin);
  el.btnOpenTidalLink.addEventListener('click', (e) => {
    if (state.currentTidalUri) {
      e.preventDefault();
      window.open(state.currentTidalUri, '_blank', 'noopener,noreferrer');
    }
  });


  // Playlists Search & Selection
  el.searchInput.addEventListener('input', (e) => {
    state.filterQuery = e.target.value.toLowerCase().trim();
    renderPlaylists();
  });
  el.btnSelectAll.addEventListener('click', selectAllPlaylists);
  el.btnDeselectAll.addEventListener('click', deselectAllPlaylists);

  // Transfer Actions
  el.btnStartTransfer.addEventListener('click', startTransfer);
  el.btnCancelTransfer.addEventListener('click', cancelTransfer);
  el.btnCloseTransferModal.addEventListener('click', () => {
    el.transferOverlay.classList.add('hidden');
    refreshAppStatus();
  });
  el.btnViewReport.addEventListener('click', openMissingReportModal);

  // Report Modal
  el.btnCloseReport.addEventListener('click', () => el.reportModal.close());
  el.btnDoneReport.addEventListener('click', () => el.reportModal.close());
  el.btnCopyReport.addEventListener('click', copyReportToClipboard);
}

// App Status & Services Refresh
async function refreshAppStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    state.spotify = data.spotify;
    state.tidal = data.tidal;

    updateTidalUI();
    await loadPlaylists();

    if (data.transfer && data.transfer.is_running) {
      resumeTransferStream();
    }
  } catch (err) {
    console.error('Error obteniendo estado de la aplicación:', err);
  }
}

// Tidal UI Updates
function updateTidalUI() {
  const isAuth = state.tidal.authenticated;
  el.tidalStatusBadge.className = `status-badge ${isAuth ? 'connected' : 'disconnected'}`;
  el.tidalStatusText.textContent = isAuth ? 'Conectado' : 'Desconectado';

  if (isAuth && state.tidal.profile) {
    const p = state.tidal.profile;
    el.tidalUserName.textContent = p.name || p.username;
    el.tidalMetaText.textContent = p.email ? `${p.email} • HiFi / MAX` : 'Sesión activa en Tidal';
    el.btnConnectTidal.textContent = 'Reconectar TIDAL';
    el.btnTidalLogout.style.display = 'inline-flex';
    el.tidalAvatar.textContent = (p.name || 'T').charAt(0).toUpperCase();
  } else {
    el.tidalUserName.textContent = 'No conectado';
    el.tidalMetaText.textContent = 'Conexión oficial en 1 clic sin claves de desarrollador';
    el.btnConnectTidal.textContent = 'Conectar TIDAL en 1 Clic';
    el.btnTidalLogout.style.display = 'none';
    el.tidalAvatar.textContent = 'TD';
  }

  updateBottomDock();
}

// Tidal Login Handler (Fixed 404 and HTTPS absolute URL)
async function onConnectTidalClick() {
  try {
    el.btnConnectTidal.disabled = true;
    el.btnConnectTidal.textContent = 'Generando enlace...';

    const res = await fetch('/api/tidal/login-link');
    const data = await res.json();

    if (!data.success) {
      alert('No se pudo generar el enlace de conexión con Tidal.');
      return;
    }

    let uri = data.verification_uri;
    if (!uri.startsWith('http://') && !uri.startsWith('https://')) {
      uri = 'https://' + uri;
    }

    state.currentTidalUri = uri;
    el.tidalCodeDisplay.textContent = data.user_code;
    el.btnOpenTidalLink.href = uri;
    el.tidalDirectLinkText.href = uri;
    el.tidalDirectLinkText.textContent = uri;

    el.tidalAuthModal.showModal();

    // Background polling with a gentle 5-second interval
    clearInterval(state.tidalPollTimer);
    state.tidalPollTimer = setInterval(async () => {
      try {
        const checkRes = await fetch('/api/tidal/check-login');
        const checkData = await checkRes.json();
        if (checkData.logged_in) {
          clearInterval(state.tidalPollTimer);
          el.tidalAuthModal.close();
          showNotification('¡TIDAL conectado exitosamente!', 'success');
          await refreshAppStatus();
        }
      } catch (e) {
        console.error('Error comprobando sesión de Tidal:', e);
      }
    }, 5000);

  } catch (err) {
    alert('Error al iniciar login de TIDAL: ' + err.message);
  } finally {
    el.btnConnectTidal.disabled = false;
    updateTidalUI();
  }
}

async function manualCheckTidalLogin() {
  if (!el.btnVerifyTidalNow) return;
  el.btnVerifyTidalNow.disabled = true;
  el.btnVerifyTidalNow.textContent = 'Comprobando...';
  try {
    const checkRes = await fetch('/api/tidal/check-login');
    const checkData = await checkRes.json();
    if (checkData.logged_in) {
      clearInterval(state.tidalPollTimer);
      el.tidalAuthModal.close();
      showNotification('¡TIDAL conectado exitosamente!', 'success');
      await refreshAppStatus();
    } else {
      showNotification('Aún no se ha completado la confirmación en Tidal.', 'info');
    }
  } catch (e) {
    console.error(e);
  } finally {
    el.btnVerifyTidalNow.disabled = false;
    el.btnVerifyTidalNow.textContent = '🔄 Ya confirmé en TIDAL (Comprobar ahora)';
  }
}


async function onTidalLogout() {
  if (!confirm('¿Deseas desconectar tu cuenta de TIDAL?')) return;
  await fetch('/api/tidal/logout', { method: 'POST' });
  await refreshAppStatus();
}

// Quick Spotify URL Loader (No developer keys!)
async function onQuickSpotifyLoad() {
  const url = el.quickSpotifyUrlInput.value.trim();
  if (!url) {
    alert('Por favor pega el enlace de tu playlist o perfil de Spotify.');
    return;
  }

  el.btnQuickLoadSpotify.disabled = true;
  el.btnQuickLoadSpotify.textContent = 'Cargando...';

  try {
    const res = await fetch('/api/spotify/load-urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls: url })
    });
    const data = await res.json();

    if (data.success && data.playlists && data.playlists.length > 0) {
      data.playlists.forEach(pl => {
        const existsIndex = state.playlists.findIndex(p => p.id === pl.id);
        if (existsIndex >= 0) {
          state.playlists[existsIndex] = pl;
        } else {
          state.playlists.unshift(pl);
        }
        state.selectedPlaylistIds.add(pl.id);
      });
      el.quickSpotifyUrlInput.value = '';
      showNotification(`¡${data.playlists.length} playlist(s) cargadas correctamente!`, 'success');
      renderPlaylists();
    } else {
      alert(data.message || 'No se pudo cargar la playlist. Verifica que el enlace sea accesible.');
    }
  } catch (err) {
    alert('Error al cargar la playlist: ' + err.message);
  } finally {
    el.btnQuickLoadSpotify.disabled = false;
    el.btnQuickLoadSpotify.textContent = 'Cargar';
  }
}

// Multi-URL Paste Loader
async function onMultiUrlSubmit(e) {
  e.preventDefault();
  const text = el.multiUrlTextarea.value.trim();
  if (!text) return;

  el.btnSubmitMultiUrl.disabled = true;
  el.btnSubmitMultiUrl.textContent = 'Cargando...';

  try {
    const res = await fetch('/api/spotify/load-urls', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls: text })
    });
    const data = await res.json();

    if (data.success && data.playlists && data.playlists.length > 0) {
      data.playlists.forEach(pl => {
        const existsIndex = state.playlists.findIndex(p => p.id === pl.id);
        if (existsIndex >= 0) {
          state.playlists[existsIndex] = pl;
        } else {
          state.playlists.unshift(pl);
        }
        state.selectedPlaylistIds.add(pl.id);
      });
      el.multiUrlModal.close();
      el.multiUrlTextarea.value = '';
      showNotification(`¡${data.playlists.length} playlist(s) añadidas a la lista!`, 'success');
      renderPlaylists();
    } else {
      alert(data.message || 'No se pudieron cargar los enlaces.');
    }
  } catch (err) {
    alert('Error: ' + err.message);
  } finally {
    el.btnSubmitMultiUrl.disabled = false;
    el.btnSubmitMultiUrl.textContent = 'Cargar Playlists';
  }
}

// Optional Developer Config Submission
async function onSpotifyConfigSubmit(e) {
  e.preventDefault();
  const clientId = el.clientIdInput.value.trim();
  const clientSecret = el.clientSecretInput.value.trim();

  if (!clientId || !clientSecret) return;

  try {
    const res = await fetch('/api/spotify/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret })
    });
    if (res.ok) {
      el.spotifyConfigModal.close();
      const authRes = await fetch('/api/spotify/auth-url');
      const authData = await authRes.json();
      if (authData.url) {
        window.location.href = authData.url;
      }
    }
  } catch (err) {
    alert('Error guardando configuración: ' + err.message);
  }
}

// Load Playlists
async function loadPlaylists() {
  try {
    const res = await fetch('/api/spotify/playlists');
    if (res.ok) {
      const data = await res.json();
      if (data.playlists && data.playlists.length > 0) {
        state.playlists = data.playlists;
        // Auto-select all by default if newly loaded
        if (state.selectedPlaylistIds.size === 0) {
          state.playlists.forEach(p => state.selectedPlaylistIds.add(p.id));
        }
      }
      renderPlaylists();
    }
  } catch (err) {
    console.error('Error cargando playlists:', err);
  }
}

// Render Playlists Grid
function renderPlaylists() {
  const container = el.playlistsGrid;
  container.innerHTML = '';

  if (state.playlists.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M8 12h8"></path>
          <path d="M12 8v8"></path>
        </svg>
        <p>Aún no has agregado ninguna playlist. Pega un enlace arriba para cargar tus canciones al instante.</p>
      </div>`;
    el.playlistsSubtitle.textContent = 'Pega el enlace de tus playlists de Spotify arriba para agregarlas a la lista.';
    updateBottomDock();
    return;
  }

  el.playlistsSubtitle.textContent = `${state.playlists.length} playlist(s) lista(s) para transferir a TIDAL`;

  const filtered = state.playlists.filter(p =>
    p.name.toLowerCase().includes(state.filterQuery)
  );

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No se encontraron playlists que coincidan con la búsqueda.</p>
      </div>`;
    updateBottomDock();
    return;
  }

  filtered.forEach(pl => {
    const card = document.createElement('div');
    const isSelected = state.selectedPlaylistIds.has(pl.id);
    card.className = `playlist-card ${isSelected ? 'selected' : ''}`;
    card.dataset.id = pl.id;

    const coverHtml = pl.image
      ? `<img src="${pl.image}" alt="${escapeHtml(pl.name)}" loading="lazy">`
      : `<div style="display:flex;height:100%;align-items:center;justify-content:center;background:#171d2c;color:var(--text-dim);">
           <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3"></circle></svg>
         </div>`;

    card.innerHTML = `
      <div class="playlist-card-cover">
        ${coverHtml}
        <div class="playlist-card-checkbox">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
      </div>
      <h4 class="playlist-card-title" title="${escapeHtml(pl.name)}">${escapeHtml(pl.name)}</h4>
      <div class="playlist-card-meta">
        <span>${pl.tracks_total} canciones</span>
        <span style="color:var(--tidal-cyan)">Listo para transferir</span>
      </div>
    `;

    card.addEventListener('click', () => togglePlaylistSelection(pl.id));
    container.appendChild(card);
  });

  updateSelectionUI();
}

function togglePlaylistSelection(id) {
  if (state.selectedPlaylistIds.has(id)) {
    state.selectedPlaylistIds.delete(id);
  } else {
    state.selectedPlaylistIds.add(id);
  }
  renderPlaylists();
}

function selectAllPlaylists() {
  state.playlists.forEach(p => state.selectedPlaylistIds.add(p.id));
  renderPlaylists();
}

function deselectAllPlaylists() {
  state.selectedPlaylistIds.clear();
  renderPlaylists();
}

function updateSelectionUI() {
  const count = state.selectedPlaylistIds.size;
  let totalTracks = 0;
  state.playlists.forEach(p => {
    if (state.selectedPlaylistIds.has(p.id)) {
      totalTracks += p.tracks_total;
    }
  });

  el.selectionCount.textContent = `${count} seleccionadas (${totalTracks} canciones)`;
  el.dockCount.textContent = `${count} playlist(s) seleccionada(s) • ${totalTracks} canciones`;
  updateBottomDock();
}

function updateBottomDock() {
  const count = state.selectedPlaylistIds.size;
  if (count > 0 && state.tidal.authenticated) {
    el.bottomDock.classList.remove('hidden');
    el.btnStartTransfer.disabled = false;
  } else if (count > 0 && !state.tidal.authenticated) {
    el.bottomDock.classList.remove('hidden');
    el.dockCount.textContent = `${count} playlist(s) lista(s). Conecta TIDAL para iniciar.`;
    el.btnStartTransfer.disabled = true;
  } else {
    el.bottomDock.classList.add('hidden');
  }
}

// Transfer Execution
async function startTransfer() {
  const playlistIds = Array.from(state.selectedPlaylistIds);
  if (playlistIds.length === 0) {
    alert('Selecciona al menos una playlist para transferir.');
    return;
  }

  if (!state.tidal.authenticated) {
    alert('Debes conectar tu cuenta de TIDAL primero.');
    onConnectTidalClick();
    return;
  }

  const prefix = el.prefixInput.value.trim();

  try {
    const res = await fetch('/api/transfer/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        playlist_ids: playlistIds,
        custom_prefix: prefix,
        public_on_tidal: false
      })
    });

    if (!res.ok) {
      const err = await res.json();
      alert('Error iniciando la transferencia: ' + (err.detail || 'Error en el servidor'));
      return;
    }

    openTransferModal();
    connectTransferSSE();
  } catch (err) {
    alert('Error al comunicarse con el servidor: ' + err.message);
  }
}

function openTransferModal() {
  el.transferOverlay.classList.remove('hidden');
  el.transferModalTitle.textContent = 'Migrando Playlists a TIDAL...';
  el.btnCancelTransfer.style.display = 'inline-flex';
  el.btnCancelTransfer.disabled = false;
  el.btnCancelTransfer.textContent = 'Detener';
  el.btnCloseTransferModal.style.display = 'none';
  el.btnViewReport.style.display = 'none';
  el.eqAnim.style.display = 'flex';

  el.plProgressBar.style.width = '0%';
  el.trackProgressBar.style.width = '0%';
  el.eventFeed.innerHTML = '<div class="feed-item" style="color:var(--text-dim)">Iniciando sincronización...</div>';
}

function resumeTransferStream() {
  openTransferModal();
  connectTransferSSE();
}

function connectTransferSSE() {
  if (state.eventSource) {
    state.eventSource.close();
  }

  state.eventSource = new EventSource('/api/transfer/events');

  state.eventSource.onmessage = (event) => {
    if (!event.data || event.data.trim() === '') return;
    try {
      const payload = JSON.parse(event.data);
      handleTransferEvent(payload);
    } catch (e) {
      console.warn('Error parsing SSE event:', e);
    }
  };

  state.eventSource.onerror = () => {
    console.warn('Conexión SSE interrumpida. Reintentando...');
  };
}

function handleTransferEvent(payload) {
  const ev = payload.event;
  const data = payload.data || {};

  if (ev === 'playlist_start') {
    el.transferModalTitle.textContent = `Migrando: ${data.playlist_name}`;
    el.plProgressLabel.textContent = `Playlist ${data.index} de ${data.total}`;
    const pct = Math.round(((data.index - 1) / data.total) * 100);
    el.plProgressBar.style.width = `${pct}%`;
    el.plPercentLabel.textContent = `${pct}%`;
    appendFeedItem(`Iniciando migración de "${data.playlist_name}" ➔ "${data.tidal_title}"`, 'fuzzy');
  }

  else if (ev === 'track_matched') {
    const prog = data.progress || {};
    el.tickerSong.textContent = data.spotify_track;
    el.tickerArtist.textContent = `${data.spotify_artist} ➔ TIDAL: ${data.tidal_track} (${data.tidal_artist})`;
    
    if (prog.total > 0) {
      const pct = Math.min(100, Math.round((prog.processed / prog.total) * 100));
      el.trackProgressBar.style.width = `${pct}%`;
      el.trackProgressLabel.textContent = `Canciones: ${prog.processed} / ${prog.total}`;
    }
    el.matchStatsLabel.textContent = `✅ ${prog.matched} emparejadas (${prog.missed || 0} no encontradas)`;

    const tagClass = data.match_type === 'ISRC_EXACT' ? 'isrc' : 'fuzzy';
    const tagText = data.match_type === 'ISRC_EXACT' ? 'ISRC 100%' : `${data.confidence}% Match`;
    appendFeedItem(`${data.spotify_artist} - ${data.spotify_track}`, tagClass, tagText);
  }

  else if (ev === 'track_missed') {
    const prog = data.progress || {};
    el.tickerSong.textContent = data.spotify_track;
    el.tickerArtist.textContent = `${data.spotify_artist} (No localizada en TIDAL)`;
    
    if (prog.total > 0) {
      const pct = Math.min(100, Math.round((prog.processed / prog.total) * 100));
      el.trackProgressBar.style.width = `${pct}%`;
      el.trackProgressLabel.textContent = `Canciones: ${prog.processed} / ${prog.total}`;
    }
    el.matchStatsLabel.textContent = `✅ ${prog.matched} emparejadas (${prog.missed || 0} no encontradas)`;
    appendFeedItem(`${data.spotify_artist} - ${data.spotify_track}`, 'missed', 'No encontrada');
  }

  else if (ev === 'playlist_done') {
    appendFeedItem(`✔ Playlist "${data.playlist_name}" completada: ${data.tracks_matched}/${data.tracks_total} canciones añadidas.`, 'isrc');
  }

  else if (ev === 'completed') {
    el.transferModalTitle.textContent = '¡Transferencia Completada!';
    el.plProgressBar.style.width = '100%';
    el.plPercentLabel.textContent = '100%';
    el.trackProgressBar.style.width = '100%';
    el.eqAnim.style.display = 'none';
    el.btnCancelTransfer.style.display = 'none';
    el.btnCloseTransferModal.style.display = 'inline-flex';

    if (data.summary && data.summary.missing_count > 0) {
      el.btnViewReport.style.display = 'inline-flex';
      el.btnViewReport.textContent = `Ver ${data.summary.missing_count} canciones faltantes`;
    }

    el.tickerSong.textContent = '¡Proceso terminado con éxito!';
    el.tickerArtist.textContent = `Se transfirieron ${data.summary?.tracks_matched || 0} canciones a TIDAL.`;
    appendFeedItem('🎉 ¡Proceso finalizado! Revisa tu biblioteca en la app de TIDAL.', 'isrc');

    if (state.eventSource) {
      state.eventSource.close();
    }
  }

  else if (ev === 'status_update' && data.status === 'cancelled') {
    el.transferModalTitle.textContent = 'Transferencia Detenida';
    el.eqAnim.style.display = 'none';
    el.btnCancelTransfer.style.display = 'none';
    el.btnCloseTransferModal.style.display = 'inline-flex';
    el.tickerSong.textContent = 'Proceso cancelado por el usuario';
    appendFeedItem('Operación cancelada.', 'missed');
    if (state.eventSource) {
      state.eventSource.close();
    }
  }

  else if (ev === 'error') {
    el.transferModalTitle.textContent = 'Error en la Transferencia';
    el.tickerSong.textContent = 'Ocurrió un error inesperado';
    el.tickerArtist.textContent = data.message || 'Consulta los detalles en el log';
    appendFeedItem(`Error: ${data.message}`, 'missed');
  }
}

function appendFeedItem(text, tagClass = '', tagText = '') {
  const item = document.createElement('div');
  item.className = 'feed-item';
  const tagHtml = tagClass ? `<span class="tag ${tagClass}">${tagText || tagClass.toUpperCase()}</span>` : '';
  item.innerHTML = `<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-right:1rem;">${escapeHtml(text)}</span>${tagHtml}`;
  el.eventFeed.appendChild(item);
  el.eventFeed.scrollTop = el.eventFeed.scrollHeight;
}

async function cancelTransfer() {
  if (!confirm('¿Deseas detener la transferencia en curso?')) return;
  el.btnCancelTransfer.disabled = true;
  el.btnCancelTransfer.textContent = 'Deteniendo...';
  await fetch('/api/transfer/stop', { method: 'POST' });
}

// Missing Tracks Report
async function openMissingReportModal() {
  try {
    const res = await fetch('/api/transfer/missing-report');
    const data = await res.json();
    const tracks = data.tracks || [];

    el.reportList.innerHTML = '';
    if (tracks.length === 0) {
      el.reportList.innerHTML = '<div class="feed-item">¡Todas las canciones fueron encontradas en Tidal!</div>';
    } else {
      tracks.forEach(t => {
        const item = document.createElement('div');
        item.className = 'feed-item';
        item.innerHTML = `<span><strong>${escapeHtml(t.artist)}</strong> - ${escapeHtml(t.name)}</span> <span style="color:var(--text-dim)">(${escapeHtml(t.playlist)})</span>`;
        el.reportList.appendChild(item);
      });
    }

    el.reportModal.showModal();
  } catch (err) {
    alert('Error cargando el reporte: ' + err.message);
  }
}

async function copyReportToClipboard() {
  const res = await fetch('/api/transfer/missing-report');
  const data = await res.json();
  const tracks = data.tracks || [];

  if (tracks.length === 0) {
    alert('No hay canciones faltantes.');
    return;
  }

  const textLines = tracks.map(t => `${t.artist} - ${t.name} (Playlist: ${t.playlist})`);
  await navigator.clipboard.writeText(textLines.join('\n'));
  showNotification('Lista copiada al portapapeles', 'success');
}

// Helper Utilities
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
}

function showNotification(msg, type = 'info') {
  const notif = document.createElement('div');
  notif.style.position = 'fixed';
  notif.style.top = '1.5rem';
  notif.style.right = '1.5rem';
  notif.style.background = type === 'success' ? 'rgba(34, 197, 94, 0.9)' : 'rgba(239, 68, 68, 0.9)';
  notif.style.color = '#fff';
  notif.style.padding = '0.75rem 1.25rem';
  notif.style.borderRadius = '8px';
  notif.style.fontSize = '0.9rem';
  notif.style.fontWeight = '600';
  notif.style.boxShadow = '0 10px 25px rgba(0,0,0,0.5)';
  notif.style.backdropFilter = 'blur(10px)';
  notif.style.zIndex = '9999';
  notif.textContent = msg;

  document.body.appendChild(notif);
  setTimeout(() => {
    notif.style.opacity = '0';
    notif.style.transition = 'opacity 0.4s ease';
    setTimeout(() => notif.remove(), 400);
  }, 3500);
}
