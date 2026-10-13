/*
 * CyberDeck Remote Dashboard Client Application
 * Author: Daen
 * Platform: CachyOS Linux | KDE Plasma 6 (Wayland) | Tailscale
 */

(function () {
  'use strict';

  // Enforce HTTPS (Let's Encrypt) on network connections
  if (window.location.protocol === 'http:' &&
      !['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    const targetPort = '8765';
    window.location.href = `https://${window.location.hostname}:${targetPort}${window.location.pathname}${window.location.search}${window.location.hash}`;
    return;
  }

  let ws = null;
  let authToken = (new URLSearchParams(window.location.search)).get('token') ||
                  localStorage.getItem('cyberdeck_token') || '';

  if (authToken) {
    localStorage.setItem('cyberdeck_token', authToken);
    if (new URLSearchParams(window.location.search).has('token')) {
      // Drop the token from the address bar, but only the token.
      //
      // This used to rebuild the URL from pathname + hash, which threw
      // away every other parameter with it -- including ?tab=, and that
      // made the deep link dead. It also ran before the tab was read
      // further down, so the tab could never have seen it. Deleting one
      // key keeps the intent (no secret in the visible URL) without
      // touching anything else.
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      const rest = url.searchParams.toString();
      window.history.replaceState({}, document.title,
        url.pathname + (rest ? '?' + rest : '') + url.hash);
    }
  }

  let currentState = {
    audio: { sources: {}, sinks: {} },
    players: [],
    telemetry: null,
    deck_buttons: [],
    macros: [],
    launchers: []
  };

  let reconnectTimer = null;
  let activeTab = 'audio';
  let modalCallback = null;

  // DOM Elements
  const cyberdeckApp = document.querySelector('.cyberdeck-app');
  const viewportContent = document.getElementById('viewport-content');
  const fullscreenBtn = document.getElementById('fullscreen-btn');
  const connectionDot = document.getElementById('connection-dot');
  const connectionLabel = document.getElementById('connection-label');
  const panicMuteBtn = document.getElementById('panic-mute-btn');
  const masterMicBtn = document.getElementById('master-mic-btn');
  const masterStatusText = document.getElementById('master-status-text');
  const masterSubText = document.getElementById('master-sub-text');
  const fadersContainer = document.getElementById('faders-container');
  const macroGrid = document.getElementById('macro-grid');
  const mediaContainer = document.getElementById('media-container');

  // Telemetry DOM Elements
  const sysOsEl = document.getElementById('sys-os');
  const sysUptimeEl = document.getElementById('sys-uptime');
  const sysProcsEl = document.getElementById('sys-procs');
  const cpuLoadEl = document.getElementById('cpu-load');
  const sysProfileEl = document.getElementById('sys-profile');

  // CPU
  const cpuPercentEl = document.getElementById('cpu-percent');
  const cpuFreqEl = document.getElementById('cpu-freq');
  const cpuTempTctlEl = document.getElementById('cpu-temp-tctl');
  const cpuTempTccd1El = document.getElementById('cpu-temp-tccd1');
  const cpuGovernorEl = document.getElementById('cpu-governor');
  const cpuGovernorBadge = document.getElementById('cpu-governor-badge');
  const cpuBarEl = document.getElementById('cpu-bar');
  const cpuCoresList = document.getElementById('cpu-cores-list');

  // GPU (RX 6600 XT)
  const gpuPercentEl = document.getElementById('gpu-percent');
  const gpuTempEdgeEl = document.getElementById('gpu-temp-edge');
  const gpuTempHotEl = document.getElementById('gpu-temp-hot');
  const gpuTempMemEl = document.getElementById('gpu-temp-mem');
  const vramTextEl = document.getElementById('vram-text');
  const vramBarEl = document.getElementById('vram-bar');
  const gpuPowerEl = document.getElementById('gpu-power');
  const gpuFanEl = document.getElementById('gpu-fan');
  const gpuClocksEl = document.getElementById('gpu-clocks');
  const gpuVoltageEl = document.getElementById('gpu-voltage');

  // Motherboard (MSI B450 / NCT6797)
  const mbTempSocketEl = document.getElementById('mb-temp-socket');
  const mbTempSystemEl = document.getElementById('mb-temp-system');
  const mbTempVrmEl = document.getElementById('mb-temp-vrm');
  const mbTempChipsetEl = document.getElementById('mb-temp-chipset');
  const mbTempSmbusEl = document.getElementById('mb-temp-smbus');
  const mbTempTsi0El = document.getElementById('mb-temp-tsi0');

  const mbVVcoreEl = document.getElementById('mb-v-vcore');
  const mbVVsocEl = document.getElementById('mb-v-vsoc');
  const mbVDramEl = document.getElementById('mb-v-dram');
  const mbV12vEl = document.getElementById('mb-v-12v');
  const mbV5vEl = document.getElementById('mb-v-5v');
  const mbV3v3El = document.getElementById('mb-v-3v3');
  const mbVPllEl = document.getElementById('mb-v-pll');
  const mbVCmosEl = document.getElementById('mb-v-cmos');

  // Cooling & Fans
  const fanCpuEl = document.getElementById('fan-cpu');
  const fanCase1El = document.getElementById('fan-case1');
  const fanCase2El = document.getElementById('fan-case2');
  const fanGpuEl = document.getElementById('fan-gpu');

  // Storage
  const nvme1TempEl = document.getElementById('nvme1-temp');
  const nvme1SubtempsEl = document.getElementById('nvme1-subtemps');
  const nvme2TempEl = document.getElementById('nvme2-temp');
  const diskRootTextEl = document.getElementById('disk-root-text');
  const diskBarEl = document.getElementById('disk-bar');
  const diskRatesEl = document.getElementById('disk-rates');

  // Network & Wireless
  const wifiTempEl = document.getElementById('wifi-temp');
  const netRatesEl = document.getElementById('net-rates');

  // RAM & Swap
  const ramPercentEl = document.getElementById('ram-percent');
  const ramTextEl = document.getElementById('ram-text');
  const ramSubtextEl = document.getElementById('ram-subtext');
  const ramBarEl = document.getElementById('ram-bar');
  const swapTextEl = document.getElementById('swap-text');
  const swapBarEl = document.getElementById('swap-bar');

  // Command Deck DOM
  // Scoped to the buttons that carry a profile. The performance mode
  // reuses the same class for the look, and a bare '.profile-btn' picked
  // those up too: `null === 'balanced'` is false, so the loop below
  // stripped 'active' from them on every render and neither FULL nor
  // YIELD could ever light up. Both the loop and the click handler want
  // the power profiles specifically, so that is what they ask for.
  const profileBtns = document.querySelectorAll('.profile-btn[data-profile]');
  const perfStateEl = document.getElementById('perf-state');
  const perfSourceEl = document.getElementById('perf-source');
  const perfScreensEl = document.getElementById('perf-screens');
  const perfBtnFull = document.getElementById('perf-btn-full');
  const perfBtnYield = document.getElementById('perf-btn-yield');
  const perfBtnAuto = document.getElementById('perf-btn-auto');
  // The same three states, in the header, so they are one tap away on a
  // phone. The card is the explanation; these are the switches.
  const perfQuickBtn = document.getElementById('perf-quick-btn');
  const perfQuickLabel = document.getElementById('perf-quick-label');
  const perfQuickAutoBtn = document.getElementById('perf-quick-auto-btn');
  const perfErrorEl = document.getElementById('perf-error');
  const customLaunchersGrid = document.getElementById('custom-launchers-grid');

  // Modal DOM
  const confirmModal = document.getElementById('confirm-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalDesc = document.getElementById('modal-desc');
  const modalBtnCancel = document.getElementById('modal-btn-cancel');
  const modalBtnConfirm = document.getElementById('modal-btn-confirm');

  // Haptic Feedback
  function triggerHaptic(duration = 35) {
    if (navigator.vibrate) {
      try { navigator.vibrate(duration); } catch (e) { /* haptics are best-effort */ }
    }
  }

  // Format Helpers
  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B/s';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB/s';
    return (bytes / 1048576).toFixed(1) + ' MB/s';
  }

  function formatSeconds(sec) {
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (d > 0) return `${d}d ${h}h ${m}m`;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  // View Mode & Desktop Layout
  function setViewMode(mode) {
    localStorage.setItem('cyberdeck_view_mode', mode);
    if (mode === 'desktop') {
      if (cyberdeckApp) {
        cyberdeckApp.classList.add('view-desktop');
        cyberdeckApp.classList.remove('view-mobile');
      }
    } else {
      if (cyberdeckApp) {
        cyberdeckApp.classList.add('view-mobile');
        cyberdeckApp.classList.remove('view-desktop');
      }
      if (activeTab === 'workstation') {
        switchTab('audio');
      }
    }
  }

  // Navigation Click Listeners (Bottom Dock & Top Desktop Nav)
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      triggerHaptic();
      const tabKey = btn.getAttribute('data-tab');
      switchTab(tabKey);
    });
  });

  document.querySelectorAll('.header-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      triggerHaptic();
      const tabKey = btn.getAttribute('data-tab');
      switchTab(tabKey);
    });
  });

  function switchTab(tabKey) {
    activeTab = tabKey;
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabKey);
    });
    document.querySelectorAll('.header-nav-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabKey);
    });

    if (tabKey === 'workstation') {
      if (viewportContent) viewportContent.classList.add('desktop-all-active');
      document.querySelectorAll('.tab-view').forEach(view => {
        view.classList.add('active');
      });
    } else {
      if (viewportContent) viewportContent.classList.remove('desktop-all-active');
      document.querySelectorAll('.tab-view').forEach(view => {
        view.classList.toggle('active', view.id === 'tab-' + tabKey);
      });
    }
    if (viewportContent) {
      // Reset the scroller that actually scrolls. That used to be
      // `viewportContent.scrollTop = 0`, which moves nothing: the parent
      // is overflow:hidden and each tab scrolls inside its own box, so
      // switching tabs kept the old tab's scroll depth on the new one.
      const scroller = tabKey === 'workstation'
        ? viewportContent
        : viewportContent.querySelector('.tab-view.active');
      if (scroller) scroller.scrollTop = 0;
    }
  }

  // Automatic Responsive View Mode Adaptation on Screen Resize
  window.addEventListener('resize', () => {
    const isDesktop = window.innerWidth >= 1024;
    const currentIsDesktop = cyberdeckApp && cyberdeckApp.classList.contains('view-desktop');
    if (isDesktop && !currentIsDesktop) {
      setViewMode('desktop');
    } else if (!isDesktop && currentIsDesktop) {
      setViewMode('mobile');
    }
  });

  // Fullscreen Button Listener
  if (fullscreenBtn) {
    fullscreenBtn.addEventListener('click', () => {
      triggerHaptic();
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });

    document.addEventListener('fullscreenchange', () => {
      if (document.fullscreenElement) {
        fullscreenBtn.textContent = '[❐ EXIT]';
        fullscreenBtn.classList.add('active');
      } else {
        fullscreenBtn.textContent = '[⛶ FULL]';
        fullscreenBtn.classList.remove('active');
      }
    });
  }

  // Desktop Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) ||
        (confirmModal && confirmModal.classList.contains('active'))) {
      return;
    }

    const key = e.key.toLowerCase();
    if (key === '0') {
      e.preventDefault();
      triggerHaptic(15);
      switchTab('workstation');
    } else if (key === '1') {
      e.preventDefault();
      triggerHaptic(15);
      switchTab('audio');
    } else if (key === '2') {
      e.preventDefault();
      triggerHaptic(15);
      switchTab('telemetry');
    } else if (key === '3') {
      e.preventDefault();
      triggerHaptic(15);
      switchTab('commands');
    } else if (key === 'm') {
      e.preventDefault();
      if (panicMuteBtn) panicMuteBtn.click();
    } else if (key === 'f') {
      e.preventDefault();
      if (fullscreenBtn) fullscreenBtn.click();
    }
  });

  // WebSocket Connection
  function connectWebSocket() {
    if (ws) {
      try { ws.close(); } catch (e) { /* already closing or closed */ }
    }

    if (connectionDot) {
      connectionDot.className = 'connection-dot';
      connectionLabel.textContent = '[LINK::CONNECTING]';
    }

    const loc = window.location;
    const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${loc.host}/ws?token=${encodeURIComponent(authToken)}`;

    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (connectionDot) {
        connectionDot.className = 'connection-dot connected';
        connectionLabel.textContent = '[LINK::WSS ONLINE]';
      }
    };

    ws.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'state_update') {
          currentState = payload;
          renderState();
        }
      } catch (e) {
        // Never silent. An empty catch here is what turned a missing
        // function into "the sensors stopped working": the render threw,
        // the error was discarded, and the page kept showing the values
        // the HTML shipped with, which look like a hardware fault.
        console.warn('[CyberDeck] state_update non reso:', e && e.message, e && e.stack);
      }
    };

    ws.onclose = () => {
      if (connectionDot) {
        connectionDot.className = 'connection-dot disconnected';
        connectionLabel.textContent = '[LINK::OFFLINE]';
      }
      scheduleReconnect();
    };

    ws.onerror = () => {};
  }

  function scheduleReconnect() {
    if (!reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
      }, 2000);
    }
  }

  // Action Dispatcher with Immediate Optimistic Haptics
  async function sendAction(actionObj) {
    triggerHaptic(40);
    const payload = {
      type: 'action',
      data: actionObj,
      ...actionObj
    };
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify(payload));
        return;
      } catch (e) {
        console.warn('WebSocket send failed, falling back to HTTP:', e);
      }
    }

    // Fallback to HTTP POST
    try {
      const url = authToken ? `/api/action?token=${encodeURIComponent(authToken)}` : '/api/action';
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) {
        headers['Authorization'] = 'Bearer ' + authToken;
      }
      await fetch(url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(payload)
      });
    } catch (e) {
      console.error('Failed to dispatch action:', e);
    }
  }

  // Master Panic Mute
  if (panicMuteBtn) {
    panicMuteBtn.addEventListener('click', () => {
      const sinks = currentState.audio.sinks || {};
      const anyUnmuted = Object.values(sinks).some(s => !s.mute);
      Object.values(sinks).forEach(s => {
        sendAction({
          type: 'sink_mute_set',
          target: s.name,
          mute: anyUnmuted
        });
      });
    });
  }

  // Master Broadcast Mic Button
  if (masterMicBtn) {
    masterMicBtn.addEventListener('click', () => {
      const isMuted = masterMicBtn.classList.contains('is-muted');
      updateMasterBtn(!isMuted);
      sendAction({ type: 'mute_all_mics' });
    });
  }

  function updateMasterBtn(allMuted) {
    if (!masterMicBtn) return;
    if (allMuted) {
      masterMicBtn.className = 'master-mic-hero is-muted';
      masterStatusText.textContent = '[MICROPHONES MUTED]';
      masterSubText.textContent = 'STATE: MUTING ACTIVE';
    } else {
      masterMicBtn.className = 'master-mic-hero is-live';
      masterStatusText.textContent = '[MICROPHONES LIVE]';
      masterSubText.textContent = 'STATE: STREAMING ACTIVE';
    }
  }

  // Render Dispatcher
  function renderState() {
    renderAudio();
    renderMedia();
    renderMacros();
    renderTelemetry();
    renderPerformance();
    renderCommandDeck();
  }

  // -------------------------------------------------------------
  // TAB 1: AUDIODECK RENDER
  // -------------------------------------------------------------
  function renderAudio() {
    const sources = currentState.audio.sources || {};
    const sinks = currentState.audio.sinks || {};

    // Mic Master Status
    const mics = Object.values(sources).filter(s => !s.is_monitor);
    const allMuted = mics.length > 0 && mics.every(m => m.mute);
    updateMasterBtn(allMuted);

    // Panic Mute Button State
    const anySinkUnmuted = Object.values(sinks).some(s => !s.mute);
    if (panicMuteBtn) {
      const allSinksMuted = Object.values(sinks).length > 0 && !anySinkUnmuted;
      panicMuteBtn.classList.toggle('active', allSinksMuted);
      panicMuteBtn.textContent = allSinksMuted ? '[MUTED ALL]' : '[MUTE ALL]';
    }

    if (!fadersContainer) return;

    // Microphone Channel (Unified)
    const anyMicUnmuted = mics.some(m => !m.mute);
    const micMuted = !anyMicUnmuted;
    const micVol = mics.length > 0 ? mics[0].volume : 100;

    let micRow = fadersContainer.querySelector('.mic-fader-strip');
    if (!micRow) {
      micRow = document.createElement('div');
      micRow.className = 'fader-strip mic-fader-strip';
      micRow.innerHTML = `
        <button class="strip-mute-btn ${micMuted ? 'is-muted' : 'is-live'}">
          ${micMuted ? '[MUTED]' : '[LIVE]'}
        </button>
        <div class="strip-info">
          <span class="strip-symbol">🎙️</span>
          <span class="strip-name">Microphone (DJI)</span>
        </div>
        <div class="strip-slider-box">
          <input type="range" min="0" max="150" value="${micVol}" class="fader-range">
          <span class="strip-vol-text">${micVol}%</span>
        </div>
      `;

      micRow.querySelector('.strip-mute-btn').addEventListener('click', () => {
        sendAction({ type: 'mute_all_mics' });
      });

      const micSlider = micRow.querySelector('.fader-range');
      const micText = micRow.querySelector('.strip-vol-text');
      micSlider.addEventListener('input', (e) => { micText.textContent = e.target.value + '%'; });
      micSlider.addEventListener('change', (e) => {
        const val = parseInt(e.target.value, 10);
        mics.forEach(m => {
          sendAction({ type: 'source_volume_set', target: m.name, volume: val });
        });
      });
      fadersContainer.appendChild(micRow);
    } else {
      const muteBtn = micRow.querySelector('.strip-mute-btn');
      muteBtn.className = `strip-mute-btn ${micMuted ? 'is-muted' : 'is-live'}`;
      muteBtn.textContent = micMuted ? '[MUTED]' : '[LIVE]';

      const micSlider = micRow.querySelector('.fader-range');
      const micText = micRow.querySelector('.strip-vol-text');
      if (document.activeElement !== micSlider && !micSlider.matches(':active')) {
        micSlider.value = micVol;
        micText.textContent = micVol + '%';
      }
    }

    // Audio Output Sinks (no hardcoded device names: bluetooth MACs change)
    const preferredOrder = ['Discord', 'Browser', 'Main'];
    const orderedSinks = [];
    preferredOrder.forEach(key => {
      const snk = sinks[key];
      if (snk) orderedSinks.push(snk);
    });
    const btSink = Object.values(sinks).find(s => s.name.startsWith('bluez_output'));
    if (btSink) orderedSinks.push(btSink);
    Object.values(sinks).forEach(snk => {
      if (!orderedSinks.includes(snk) && !snk.name.includes('easyeffects_sink')) {
        orderedSinks.push(snk);
      }
    });

    const activeSinkNames = new Set(orderedSinks.map(s => s.name));

    // Remove obsolete strips
    fadersContainer.querySelectorAll('.sink-fader-strip').forEach(el => {
      const name = el.getAttribute('data-sink-name');
      if (!activeSinkNames.has(name)) {
        el.remove();
      }
    });

    // Update or create sink strips in-place
    orderedSinks.forEach(snk => {
      let row = fadersContainer.querySelector(`.sink-fader-strip[data-sink-name="${CSS.escape(snk.name)}"]`);
      if (!row) {
        row = createSinkStrip(snk);
        fadersContainer.appendChild(row);
      } else {
        const muteBtn = row.querySelector('.strip-mute-btn');
        muteBtn.className = `strip-mute-btn ${snk.mute ? 'is-muted' : 'is-live'}`;
        muteBtn.textContent = snk.mute ? '[MUTED]' : '[LIVE]';

        const slider = row.querySelector('.fader-range');
        const text = row.querySelector('.strip-vol-text');
        if (document.activeElement !== slider && !slider.matches(':active')) {
          slider.value = snk.volume;
          text.textContent = snk.volume + '%';
        }
      }
    });
  }

  function createSinkStrip(snk) {
    const row = document.createElement('div');
    row.className = 'fader-strip sink-fader-strip';
    row.setAttribute('data-sink-name', snk.name);

    let symbol = '🔊';
    let cleanName = snk.description || snk.name;
    const nameLower = snk.name.toLowerCase();
    const descLower = (snk.description || '').toLowerCase();

    if (nameLower.includes('discord')) { cleanName = 'Discord'; symbol = '💬'; }
    else if (nameLower.includes('browser')) { cleanName = 'Browser'; symbol = '🌐'; }
    else if (nameLower.includes('bluez') || descLower.includes('anc')) { cleanName = 'Headphones (ANC Icon)'; symbol = '🎧'; }
    else if (nameLower.includes('hdmi')) { cleanName = 'Audio HDMI'; symbol = '🖥️'; }
    else if (snk.name === 'Main') { cleanName = 'Main Desktop'; symbol = '🔊'; }

    row.innerHTML = `
      <button class="strip-mute-btn ${snk.mute ? 'is-muted' : 'is-live'}">
        ${snk.mute ? '[MUTED]' : '[LIVE]'}
      </button>
      <div class="strip-info">
        <span class="strip-symbol">${symbol}</span>
        <span class="strip-name">${cleanName}</span>
      </div>
      <div class="strip-slider-box">
        <input type="range" min="0" max="150" value="${snk.volume}" class="fader-range">
        <span class="strip-vol-text">${snk.volume}%</span>
      </div>
    `;

    row.querySelector('.strip-mute-btn').addEventListener('click', () => {
      sendAction({ type: 'sink_mute_toggle', target: snk.name });
    });

    const slider = row.querySelector('.fader-range');
    const text = row.querySelector('.strip-vol-text');
    slider.addEventListener('input', (e) => { text.textContent = e.target.value + '%'; });
    slider.addEventListener('change', (e) => {
      sendAction({ type: 'sink_volume_set', target: snk.name, volume: parseInt(e.target.value, 10) });
    });

    return row;
  }

  let lastMediaSignature = '';
  function renderMedia() {
    if (!mediaContainer) return;
    const players = currentState.players || [];
    if (!players.length) {
      if (lastMediaSignature !== '__EMPTY__') {
        mediaContainer.innerHTML = '<div style="font-size:0.75rem; color:var(--text-dim); text-align:center; padding:10px;">No active MPRIS media player</div>';
        lastMediaSignature = '__EMPTY__';
      }
      return;
    }

    const activePlayer = players.find(p => p.is_playing) || players[0];
    const isPlaying = activePlayer.status === 'Playing';
    const sig = `${activePlayer.service}|${activePlayer.title}|${activePlayer.artist}|${isPlaying}|${activePlayer.art_url}`;
    if (sig === lastMediaSignature) {
      return;
    }
    lastMediaSignature = sig;

    mediaContainer.innerHTML = `
      <div class="media-track-info">
        <div class="media-art-box">
          ${activePlayer.art_url ? `<img src="${activePlayer.art_url}">` : '🎵'}
        </div>
        <div class="media-text-box">
          <div class="media-title">${activePlayer.title || 'Inactive'}</div>
          <div class="media-artist">${activePlayer.artist || activePlayer.identity || 'Media player'}</div>
        </div>
      </div>
      <div class="media-controls-row">
        <button class="media-ctrl-btn" id="mpris-prev" title="Precedente">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="19 20 9 12 19 4 19 20"></polygon><line x1="5" y1="19" x2="5" y2="4"></line></svg>
        </button>
        <button class="media-ctrl-btn play-pause" id="mpris-play" title="Play/Pause">
          ${isPlaying ? `
            <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
          ` : `
            <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          `}
        </button>
        <button class="media-ctrl-btn" id="mpris-next" title="Successivo">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 4 15 12 5 20 5 4"></polygon><line x1="19" y1="5" x2="19" y2="19"></line></svg>
        </button>
      </div>
    `;

    mediaContainer.querySelector('#mpris-prev').addEventListener('click', () => {
      sendAction({ type: 'media_control', action: 'Previous', service: activePlayer.service });
    });
    mediaContainer.querySelector('#mpris-play').addEventListener('click', () => {
      sendAction({ type: 'media_control', action: 'PlayPause', service: activePlayer.service });
    });
    mediaContainer.querySelector('#mpris-next').addEventListener('click', () => {
      sendAction({ type: 'media_control', action: 'Next', service: activePlayer.service });
    });
  }

  function renderMacros() {
    if (!macroGrid) return;
    const buttons = currentState.deck_buttons || [];
    const sinks = currentState.audio.sinks || {};

    // If existing tiles match button count, update in-place without clearing DOM
    // (and without losing the click listeners attached at creation).
    // This branch used to be a no-op -- it fetched each tile and returned
    // -- so mute colours froze at first render. Now it refreshes exactly
    // what creation sets: the muted class, the accent and the symbol.
    if (macroGrid.children.length === buttons.length && buttons.length > 0) {
      buttons.forEach((btn, idx) => {
        const tile = macroGrid.children[idx];
        if (!tile) return;
        let isMuted = false;
        if (btn.type === 'sink_mute_toggle') {
          const snk = sinks[btn.target];
          isMuted = snk ? snk.mute : false;
        }
        tile.classList.toggle('is-muted', isMuted);
        tile.style.setProperty('--accent-col', isMuted ? C_ALARM() : C_ACC());
        const iconEl = tile.querySelector('.macro-icon');
        if (iconEl && btn.icon === 'volume-2') {
          iconEl.textContent = isMuted ? '🔈' : '🔊';
        }
      });
      return;
    }

    macroGrid.innerHTML = '';
    buttons.forEach(btn => {
      const tile = document.createElement('div');
      tile.className = 'macro-btn';


      let isMuted = false;
      if (btn.type === 'sink_mute_toggle') {
        const snk = sinks[btn.target];
        isMuted = snk ? snk.mute : false;
      }

      if (isMuted) tile.classList.add('is-muted');
      tile.style.setProperty('--accent-col', isMuted ? C_ALARM() : C_ACC());

      let symbol = '🎛️';
      if (btn.icon === 'globe') symbol = '🌐';
      else if (btn.icon === 'volume-2') symbol = isMuted ? '🔈' : '🔊';

      tile.innerHTML = `
        <div class="macro-icon">${symbol}</div>
        <div class="macro-title">${btn.label}</div>
        ${btn.sublabel ? `<div class="macro-sublabel">${btn.sublabel}</div>` : ''}
      `;

      tile.addEventListener('click', () => {
        sendAction({ type: btn.type, target: btn.target, action: btn.action });
      });

      macroGrid.appendChild(tile);
    });
  }

  // =============================================================
  // DYNAMIC HARDWARE SPECTRUM & THERMAL THROTTLING ENGINE
  // =============================================================
  /**
   * Reads a token from the design system instead of writing the colour
   * by hand.
   *
   * In v1.0 there were 50 hex literals below here -- Matrix green, cyan,
   * amber, three reds -- plus neon text-shadows. Every one of them
   * bypassed the style sheet: changing the palette meant hunting for
   * them one by one in among the functions, and they were never found.
   * Now there is a single source, --accent and --alarm in :root.
   */
  const themeCache = {};
  function token(name, fallback) {
    if (themeCache[name] !== undefined) return themeCache[name];
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
    themeCache[name] = v || fallback;
    return themeCache[name];
  }

  // The three steps of the new spectrum: idle -> accent -> alarm.
  // Three colours, not six: in a grid of sensors, six gradients become
  // noise and the red of danger cannot be told from the red of caution.
  const C_IDLE  = () => token('--idle', '#6b7a6f');
  const C_TEXT  = () => token('--text-2', '#8a857c');
  const C_ACC   = () => token('--accent', '#ff9d2e');
  const C_ALARM = () => token('--alarm', '#d8492f');

  /**
   * Continuous Thermal Spectrum:
   *  <= coolVal      : Electric Cyan (#00f0ff)
   *  cool -> normal  : Cyan -> Matrix Green (#00ff66)
   *  normal -> warm  : Matrix Green -> Tactical Amber (#ffb700)
   *  warm -> throttle: Amber -> Warning Orange (#ff5500)
   *  throttle -> max : Orange -> Alert Red (#ff1744)
   *  > maxVal (TjMax): Critical Deep Red (#ff0033)
   */
    /**
     * Thermal spectrum.
     *
     * v1.0 had six interpolated steps: cyan, Matrix green, amber,
     * orange, red, deep red. On a grid of thirty sensors those
     * gradients produced a rainbow of dots, and moving from one value
     * to the next changed hue rather than intensity.
     *
     * Now the rule of the analog instrument applies: unlit below the
     * threshold, amber beyond it, red only on overload. Three colours,
     * not six, and the colour still says one thing only.
     */    function getSpectrumColor(val, warmVal, throttleVal) {      if (val === null || val === undefined || isNaN(val)) return C_TEXT();      if (val <= warmVal) return C_IDLE();      if (val <= throttleVal) return C_ACC();      return C_ALARM();    }
  /**
   * Bilateral Hardware Voltage Spectrum:
   * Nominal center is optimal Matrix Green (#00ff66).
   * Towards lowWarn/highWarn tolerance borders shifts to Tactical Amber (#ffb700).
   * Approaching out-of-spec limits (lowCrit/highCrit) shifts to Alert Red (#ff2244).
   * Beyond critical limits turns to Flashing Critical Red (#ff0033).
   */
    function getVoltageSpectrum(val, lowWarn, highWarn, lowCrit, highCrit) {      if (val === null || val === undefined || isNaN(val)) return C_TEXT();      if (val >= highCrit || val <= lowCrit) return C_ALARM();      if (val >= highWarn || val <= lowWarn)  return C_ACC();      return C_IDLE();    }
  /**
   * Utilization & Load Spectrum (0 - 100%)
   */
    function getUsageSpectrum(pct, warmVal = 70, maxVal = 88) {      if (pct === null || pct === undefined || isNaN(pct)) return C_TEXT();      if (pct >= maxVal) return C_ALARM();      if (pct >= warmVal) return C_ACC();      return C_IDLE();    }
  /**
   * Cooling & Fan RPM Spectrum
   */
    /**
     * Fans.
     *
     * The body of this function was deleted with the glow and the five
     * call sites were left behind. Nothing failed visibly: the
     * WebSocket handler wraps `renderState` in `catch (e) {}`, so the
     * `ReferenceError` was swallowed and every render stopped at the
     * first call. The GPU block runs up to its fan, which is why the CPU
     * and the GPU showed numbers and everything after them stayed at
     * the value the HTML shipped with -- motherboard, fans, NVMe,
     * network, RAM and swap all read as blank or zero. "Sensors not
     * detected" was never a sensor problem.
     *
     * Two lessons, and they are the same two from the icon work. An
     * empty `catch` turns a hard error into a silent blank, which is
     * worse than no handler at all: it converts a fault you could read
     * into one you have to infer from a screenshot. And a doc comment
     * that survives while its body does not is the record of the
     * deletion, which is why the comment is here as well as the code.
     *
     * RPM on its own is not a severity: a fan at 400 RPM cooling
     * something at 40 degrees is doing its job. The one state worth
     * showing is a stopped fan on something already hot, and that is
     * what the second argument is for.
     */
    function getFanSpectrum(rpm, contextTemp) {
      if (rpm === null || rpm === undefined || isNaN(rpm)) return C_TEXT();
      const known = contextTemp !== null && contextTemp !== undefined && !isNaN(contextTemp);
      if (rpm <= 0 && known && contextTemp > 75) return C_ALARM();
      return C_IDLE();
    }
  /**
   * Paints a reading in the spectrum colour. Colour and nothing else.
   *
   * This used to do two more things, and both were wrong.
   *
   * The first was a text-shadow glow, at 6px and then 14px. On one
   * number that reads as emphasis; on the core list it is sixteen
   * numbers breathing at once, and it was applied to about
   * forty-five elements, so any real load turned the page into a field
   * of shimmering text. The glow carries nothing: the colour already
   * says the value and the number is right beside it.
   *
   * The second was adding `throttle-alert`, which is a *banner* style
   * -- 9px of padding, a 1px border, uppercase, a tinted background. It
   * went onto the percentage span of every core, so at 90% load each of
   * the sixteen grew a small red box beside it. Those are the squares.
   * The same class reached about forty-five elements across the whole
   * page, so it was never only the cores: every sensor over its
   * threshold did the same.
   *
   * The banner style stays in the stylesheet for the case it was
   * written for, but nothing in the markup uses it any more, so
   * nothing here may put it on a number.
   */
  function applyDynamicSpectrum(el, color) {
    if (!el) return;
    el.style.color = color;
  }

  /**
   * Apply dynamic color to hardware progress bars
  /**
   * Fills a hardware bar: a solid run of colour, and no glow.
   *
   * It was a repeating gradient of 6px dashes on a 3px bar plus an 8px
   * box-shadow. The stylesheet already defines these bars as a solid
   * fill with a width transition, so the inline gradient was fighting
   * it. On one bar that reads as a segmented meter; with the hardware
   * list under it, and again on the core list, it is a grid of small
   * lit squares, and the shadow makes them breathe. The width encodes
   * the value and the figure beside it gives the exact number, so the
   * dashes were carrying nothing that was not already there.
   */
  function applyBarSpectrum(barEl, pct, color) {
    if (!barEl) return;
    const clamped = Math.min(100, Math.max(0, pct));
    barEl.style.width = clamped + '%';
    barEl.style.background = color;
    barEl.style.boxShadow = 'none';
  }

  // -------------------------------------------------------------
  // TAB 2: CYBERMATRIX TELEMETRY RENDER
  // -------------------------------------------------------------
  function renderTelemetry() {
    const t = currentState.telemetry;
    if (!t) return;

    // System Header Bar
    if (sysOsEl) sysOsEl.textContent = `${t.system.os || 'CachyOS Linux x86_64'}`;
    if (sysUptimeEl) sysUptimeEl.textContent = formatSeconds(t.system.uptime_seconds || 0);
    if (sysProcsEl) sysProcsEl.textContent = t.system.process_count || 0;
    if (cpuLoadEl && t.cpu && t.cpu.load_avg) cpuLoadEl.textContent = t.cpu.load_avg.join(' ');
    if (sysProfileEl && t.system) {
      const prof = (t.system.power_profile || 'balanced').toUpperCase();
      sysProfileEl.textContent = prof;
      const profCol = prof.includes('PERF') ? C_ACC()
                      : (prof.includes('SAVE') ? C_IDLE() : C_TEXT());
      sysProfileEl.style.color = profCol;
      sysProfileEl.style.textShadow = `0 0 8px ${profCol}80`;
    }

    // 1. CPU (AMD Ryzen 7 3800X - Zen 2 Matisse)
    if (t.cpu) {
      const cpuLoad = Math.min(100, Math.max(0, t.cpu.percent || 0));
      const cpuLoadCol = getUsageSpectrum(cpuLoad, 70, 88);
      if (cpuPercentEl) {
        cpuPercentEl.textContent = cpuLoad;
        applyDynamicSpectrum(cpuPercentEl, cpuLoadCol);
      }
      applyBarSpectrum(cpuBarEl, cpuLoad, cpuLoadCol);

      if (cpuFreqEl) {
        const freqGhz = ((t.cpu.freq_mhz || 0) / 1000);
        cpuFreqEl.textContent = freqGhz.toFixed(2) + ' GHz';
        const freqCol = freqGhz < 4.2 ? C_IDLE()
                        : (freqGhz < 4.4 ? C_ACC() : C_ALARM());
        applyDynamicSpectrum(cpuFreqEl, freqCol);
      }

      // Tctl (Zen 2 Package: PB2 throttle starts at 82-85°C, TjMax 95°C)
      const tctl = t.cpu.temp_tctl_c;
      if (cpuTempTctlEl) {
        cpuTempTctlEl.textContent = tctl !== null && tctl !== undefined ? tctl + '°C' : '--';
        const tctlCol = getSpectrumColor(tctl, 72, 85);
        applyDynamicSpectrum(cpuTempTctlEl, tctlCol);
      }

      // Tccd1 (Core Die 1: throttle starts 85°C, TjMax 95°C)
      const tccd1 = t.cpu.temp_tccd1_c;
      if (cpuTempTccd1El) {
        cpuTempTccd1El.textContent = tccd1 !== null && tccd1 !== undefined ? tccd1 + '°C' : '--';
        const tccd1Col = getSpectrumColor(tccd1, 72, 85);
        applyDynamicSpectrum(cpuTempTccd1El, tccd1Col);
      }

      if (cpuGovernorEl) cpuGovernorEl.textContent = t.cpu.governor || 'powersave';
      if (cpuGovernorBadge) cpuGovernorBadge.textContent = (t.cpu.governor || 'Ryzen').toUpperCase();

      // Multi-Core Detailed List (16 SMT Threads)
      if (cpuCoresList && Array.isArray(t.cpu.cores_detail || t.cpu.cores)) {
        const coresData = t.cpu.cores_detail || t.cpu.cores.map((load, idx) => ({
          thread: idx + 1,
          core: idx % 8,
          load: load,
          freq_mhz: t.cpu.freq_mhz || 0
        }));

        if (cpuCoresList.children.length !== coresData.length) {
          cpuCoresList.innerHTML = '';
          coresData.forEach(item => {
            const row = document.createElement('div');
            row.className = 'core-list-row';
            row.innerHTML = `
              <div class="core-meta">
                <span class="core-thread-badge">T${String(item.thread).padStart(2, '0')}</span>
                <span class="core-phys-tag">Core ${item.core}</span>
              </div>
              <div class="core-bar-wrapper">
                <div class="core-list-bar-bg">
                  <div id="core-bar-${item.thread - 1}" class="core-list-bar-fill"></div>
                </div>
              </div>
              <div class="core-stats">
                <span id="core-freq-${item.thread - 1}" class="core-freq">${(item.freq_mhz / 1000).toFixed(2)} GHz</span>
                <span id="core-pct-${item.thread - 1}" class="core-pct">${Math.round(item.load)}%</span>
              </div>
            `;
            cpuCoresList.appendChild(row);
          });
        }

        coresData.forEach(item => {
          const idx = item.thread - 1;
          const barEl = document.getElementById(`core-bar-${idx}`);
          const freqEl = document.getElementById(`core-freq-${idx}`);
          const pctEl = document.getElementById(`core-pct-${idx}`);

          const load = Math.min(100, Math.max(0, item.load));
          const coreColor = getUsageSpectrum(load, 70, 88);

          if (barEl) {
            barEl.style.width = load + '%';
            // Same as applyBarSpectrum: solid, no glow. Sixteen rows
            // of 5px dashes with a 6px shadow is the flicker.
            barEl.style.background = coreColor;
            barEl.style.boxShadow = 'none';
          }
          if (pctEl) {
            pctEl.textContent = Math.round(load) + '%';
            applyDynamicSpectrum(pctEl, coreColor);
          }
          if (freqEl) {
            const ghz = ((item.freq_mhz || t.cpu.freq_mhz || 0) / 1000);
            freqEl.textContent = ghz.toFixed(2) + ' GHz';
            const fCol = ghz < 4.2 ? C_IDLE() : (ghz < 4.4 ? C_ACC() : C_ALARM());
            freqEl.style.color = fCol;
          }
        });
      }
    }

    // 2. GPU (AMD Radeon RX 6600 XT - Navi 23 RDNA2)
    if (t.gpu) {
      const gpuLoad = Math.min(100, Math.max(0, t.gpu.busy_percent || 0));
      const gpuLoadCol = getUsageSpectrum(gpuLoad, 75, 90);
      if (gpuPercentEl) {
        gpuPercentEl.textContent = gpuLoad;
        applyDynamicSpectrum(gpuPercentEl, gpuLoadCol);
      }

      // Edge Temp (Navi 23: Throttle start 85°C, Max 90°C)
      const edge = t.gpu.temp_edge;
      if (gpuTempEdgeEl) {
        gpuTempEdgeEl.textContent = (edge !== null && edge !== undefined ? edge : 0) + '°C';
        const edgeCol = getSpectrumColor(edge, 72, 85);
        applyDynamicSpectrum(gpuTempEdgeEl, edgeCol);
      }

      // Hotspot / Junction Temp (Navi 23: Throttle start 102°C, TjMax 110°C)
      const hot = t.gpu.temp_hotspot;
      if (gpuTempHotEl) {
        gpuTempHotEl.textContent = (hot !== null && hot !== undefined ? hot : 0) + '°C';
        const hotCol = getSpectrumColor(hot, 88, 102);
        applyDynamicSpectrum(gpuTempHotEl, hotCol);
      }

      // Memory Temp (GDDR6 8GB: Throttle start 95°C, Max 105°C)
      const mem = t.gpu.temp_mem;
      if (gpuTempMemEl) {
        gpuTempMemEl.textContent = (mem !== null && mem !== undefined ? mem : 0) + '°C';
        const memCol = getSpectrumColor(mem, 80, 95);
        applyDynamicSpectrum(gpuTempMemEl, memCol);
      }

      // VRAM Usage
      const vramPct = Math.min(100, Math.max(0, t.gpu.vram_percent || 0));
      const vramCol = getUsageSpectrum(vramPct, 75, 90);
      if (vramTextEl) {
        vramTextEl.textContent = `${t.gpu.vram_used_mb || 0} / ${t.gpu.vram_total_mb || 8176} MB (${vramPct}%)`;
        applyDynamicSpectrum(vramTextEl, vramCol);
      }
      applyBarSpectrum(vramBarEl, vramPct, vramCol);

      // GPU Power (Stock 130W TGP, 135W throttle threshold)
      const pwr = t.gpu.power_watts || 0;
      if (gpuPowerEl) {
        gpuPowerEl.textContent = pwr + ' W';
        const pwrCol = getUsageSpectrum(pwr, 115, 135);
        applyDynamicSpectrum(gpuPowerEl, pwrCol);
      }

      // GPU Fan
      const gFan = t.gpu.fan_rpm || 0;
      if (gpuFanEl) {
        gpuFanEl.textContent = gFan + ' RPM';
        const gFanCol = getFanSpectrum(gFan, edge || 40);
        applyDynamicSpectrum(gpuFanEl, gFanCol);
      }

      // GPU Clocks
      const sclk = t.gpu.sclk_mhz || 0;
      if (gpuClocksEl) {
        gpuClocksEl.textContent = `${sclk} / ${t.gpu.mclk_mhz || 0} MHz`;
        const clkCol = sclk < 2250 ? C_IDLE() : (sclk < 2550 ? C_ACC() : C_ALARM());
        applyDynamicSpectrum(gpuClocksEl, clkCol);
      }

      // GPU Voltage (VDDGFX Navi 23 in mV: nominal 1000mV, max stock 1150mV)
      const vdd = t.gpu.vddgfx_mv || 0;
      if (gpuVoltageEl) {
        gpuVoltageEl.textContent = vdd + ' mV';
        const vddCol = getVoltageSpectrum(vdd, 750, 1125, 650, 1150);
        applyDynamicSpectrum(gpuVoltageEl, vddCol);
      }
    }

    // 3. Motherboard (B450 AORUS M / Nuvoton NCT6797D)
    if (t.motherboard) {
      const mb = t.motherboard;

      // Socket Temp (CPUTIN: 35 cool, 50 normal, 65 warm, 75 throttle, 85 max)
      const sock = mb.socket_temp_c;
      if (mbTempSocketEl) {
        mbTempSocketEl.textContent = sock !== null ? sock + '°C' : '--';
        const sockCol = getSpectrumColor(sock, 65, 75);
        applyDynamicSpectrum(mbTempSocketEl, sockCol);
      }

      // System Temp (SYSTIN: 30 cool, 42 normal, 52 warm, 60 throttle, 70 max)
      const syst = mb.system_temp_c;
      if (mbTempSystemEl) {
        mbTempSystemEl.textContent = syst !== null ? syst + '°C' : '--';
        const systCol = getSpectrumColor(syst, 52, 60);
        applyDynamicSpectrum(mbTempSystemEl, systCol);
      }

      // VRM MOSFETs (35 cool, 55 normal, 75 warm, 90 throttle alert, 105 max OTP)
      const vrm = mb.vrm_temp_c;
      if (mbTempVrmEl) {
        mbTempVrmEl.textContent = vrm !== null ? vrm + '°C' : '--';
        const vrmCol = getSpectrumColor(vrm, 75, 90);
        applyDynamicSpectrum(mbTempVrmEl, vrmCol);
      }

      // Chipset B450 FCH (35 cool, 48 normal, 62 warm, 72 throttle, 85 max)
      const chip = mb.chipset_temp_c;
      if (mbTempChipsetEl) {
        mbTempChipsetEl.textContent = chip !== null ? chip + '°C' : '--';
        const chipCol = getSpectrumColor(chip, 62, 72);
        applyDynamicSpectrum(mbTempChipsetEl, chipCol);
      }

      // SMBus & TSI0 (35 cool, 50 normal, 65 warm, 75 throttle, 85 max)
      const smb = mb.smbus_temp_c;
      if (mbTempSmbusEl) {
        mbTempSmbusEl.textContent = smb !== null ? smb + '°C' : '--';
        const smbCol = getSpectrumColor(smb, 65, 75);
        applyDynamicSpectrum(mbTempSmbusEl, smbCol);
      }

      const tsi = mb.tsi0_temp_c;
      if (mbTempTsi0El) {
        mbTempTsi0El.textContent = tsi !== null ? tsi + '°C' : '--';
        const tsiCol = getSpectrumColor(tsi, 65, 75);
        applyDynamicSpectrum(mbTempTsi0El, tsiCol);
      }

      // VOLTAGES
      const v = mb.voltages || {};

      // CPU Vcore (Zen 2 Matisse: 1.25V nom, 0.85V-1.44V safe, 1.485V max degr)
      const vcore = v.cpu_vcore;
      if (mbVVcoreEl) {
        mbVVcoreEl.textContent = vcore ? vcore.toFixed(3) + ' V' : '--';
        const vcoreCol = getVoltageSpectrum(vcore, 0.85, 1.44, 0.65, 1.485);
        applyDynamicSpectrum(mbVVcoreEl, vcoreCol);
      }

      // CPU Vsoc (Zen 2 Infinity Fabric: 1.05V nom, 0.95V-1.15V safe, 1.20V max degr)
      const vsoc = v.cpu_vsoc;
      if (mbVVsocEl) {
        mbVVsocEl.textContent = vsoc ? vsoc.toFixed(3) + ' V' : '--';
        const vsocCol = getVoltageSpectrum(vsoc, 0.95, 1.15, 0.88, 1.20);
        applyDynamicSpectrum(mbVVsocEl, vsocCol);
      }

      // DRAM Voltage (DDR4: 1.35V nom XMP, 1.20V-1.40V safe, 1.45V max)
      const dram = v.dram;
      if (mbVDramEl) {
        mbVDramEl.textContent = dram ? dram.toFixed(3) + ' V' : '--';
        const dramCol = getVoltageSpectrum(dram, 1.20, 1.40, 1.15, 1.45);
        applyDynamicSpectrum(mbVDramEl, dramCol);
      }

      // ATX +12V Rail (12.00V nom, 11.60V-12.40V tol, 11.40V-12.60V ATX ±5%)
      const v12 = v.atx_12v;
      if (mbV12vEl) {
        mbV12vEl.textContent = v12 ? v12.toFixed(2) + ' V' : '--';
        const v12Col = getVoltageSpectrum(v12, 11.60, 12.40, 11.40, 12.60);
        applyDynamicSpectrum(mbV12vEl, v12Col);
      }

      // ATX +5V Rail (5.00V nom, 4.85V-5.15V tol, 4.75V-5.25V ATX ±5%)
      const v5 = v.atx_5v;
      if (mbV5vEl) {
        mbV5vEl.textContent = v5 ? v5.toFixed(2) + ' V' : '--';
        const v5Col = getVoltageSpectrum(v5, 4.85, 5.15, 4.75, 5.25);
        applyDynamicSpectrum(mbV5vEl, v5Col);
      }

      // ATX +3.3V Rail (3.30V nom, 3.20V-3.40V tol, 3.14V-3.46V ATX ±5%)
      const v33 = v.atx_3v3;
      if (mbV3v3El) {
        mbV3v3El.textContent = v33 ? v33.toFixed(2) + ' V' : '--';
        const v33Col = getVoltageSpectrum(v33, 3.20, 3.40, 3.14, 3.46);
        applyDynamicSpectrum(mbV3v3El, v33Col);
      }

      // 1.8V PLL (1.80V nom, 1.75V-1.85V tol, 1.70V-1.90V crit)
      const pll = v.cpu_pll_1v8;
      if (mbVPllEl) {
        mbVPllEl.textContent = pll ? pll.toFixed(2) + ' V' : '--';
        const pllCol = getVoltageSpectrum(pll, 1.75, 1.85, 1.70, 1.90);
        applyDynamicSpectrum(mbVPllEl, pllCol);
      }

      // CMOS Battery (CR2032 3V: 3.10V nom, 2.80V-3.40V good, 2.60V dead)
      const cmos = v.cmos_battery;
      if (mbVCmosEl) {
        mbVCmosEl.textContent = cmos ? cmos.toFixed(2) + ' V' : '--';
        const cmosCol = getVoltageSpectrum(cmos, 2.80, 3.40, 2.60, 3.50);
        applyDynamicSpectrum(mbVCmosEl, cmosCol);
      }
    }

    // 4. Fans
    if (t.fans) {
      const fCpu = t.fans.cpu_cooler || 0;
      if (fanCpuEl) {
        fanCpuEl.textContent = fCpu + ' RPM';
        const fCol = getFanSpectrum(fCpu, t.cpu ? t.cpu.temp_tctl_c : 40);
        applyDynamicSpectrum(fanCpuEl, fCol);
      }

      const fC1 = t.fans.chassis_fan_1 || 0;
      if (fanCase1El) {
        fanCase1El.textContent = fC1 + ' RPM';
        const fCol = getFanSpectrum(fC1, t.motherboard ? t.motherboard.system_temp_c : 35);
        applyDynamicSpectrum(fanCase1El, fCol);
      }

      const fC2 = t.fans.chassis_fan_2 || 0;
      if (fanCase2El) {
        fanCase2El.textContent = fC2 + ' RPM';
        const fCol = getFanSpectrum(fC2, t.motherboard ? t.motherboard.system_temp_c : 35);
        applyDynamicSpectrum(fanCase2El, fCol);
      }

      const fGpu = t.fans.gpu || (t.gpu && t.gpu.fan_rpm) || 0;
      if (fanGpuEl) {
        fanGpuEl.textContent = fGpu + ' RPM';
        const fCol = getFanSpectrum(fGpu, t.gpu ? t.gpu.temp_edge : 40);
        applyDynamicSpectrum(fanGpuEl, fCol);
      }
    }

    // 5. Storage (NVMe SSDs & Filesystem)
    if (t.storage_nvme) {
      const nv1 = t.storage_nvme.nvme_1;
      const nv2 = t.storage_nvme.nvme_2;

      // NVMe 1 Composite (30 cool, 45 normal, 58 warm, 70 throttle, 80 max)
      if (nvme1TempEl) {
        const c1 = nv1 && nv1.composite_c !== undefined ? nv1.composite_c : null;
        nvme1TempEl.textContent = c1 !== null ? c1 + '°C' : '--';
        const c1Col = getSpectrumColor(c1, 58, 70);
        applyDynamicSpectrum(nvme1TempEl, c1Col);
      }

      if (nvme1SubtempsEl) {
        if (nv1 && nv1.sensor_1_c) {
          nvme1SubtempsEl.textContent = `S1: ${nv1.sensor_1_c}°C` + (nv1.sensor_2_c ? ` | S2: ${nv1.sensor_2_c}°C` : '');
          const sCol = getSpectrumColor(nv1.sensor_1_c, 58, 68);
          applyDynamicSpectrum(nvme1SubtempsEl, sCol);
        } else {
          nvme1SubtempsEl.textContent = '--';
        }
      }

      // NVMe 2 Composite
      if (nvme2TempEl) {
        const c2 = nv2 && nv2.composite_c !== undefined ? nv2.composite_c : null;
        nvme2TempEl.textContent = c2 !== null ? c2 + '°C' : '--';
        const c2Col = getSpectrumColor(c2, 58, 70);
        applyDynamicSpectrum(nvme2TempEl, c2Col);
      }
    }

    if (t.disk) {
      const dPct = Math.min(100, Math.max(0, t.disk.percent || 0));
      const diskCol = getUsageSpectrum(dPct, 75, 90);
      if (diskRootTextEl) {
        diskRootTextEl.textContent = `${t.disk.used_gb} / ${t.disk.total_gb} GB (${dPct}%)`;
        applyDynamicSpectrum(diskRootTextEl, diskCol);
      }
      applyBarSpectrum(diskBarEl, dPct, diskCol);
      if (diskRatesEl) diskRatesEl.textContent = `R: ${formatBytes(t.disk.read_bps || 0)} | W: ${formatBytes(t.disk.write_bps || 0)}`;
    }

    // 6. Network & Wireless
    if (wifiTempEl) {
      const wTemp = t.wifi_temp_c;
      wifiTempEl.textContent = wTemp !== null && wTemp !== undefined ? wTemp + '°C' : '--';
      const wCol = getSpectrumColor(wTemp, 58, 70);
      applyDynamicSpectrum(wifiTempEl, wCol);
    }
    if (netRatesEl && t.network) netRatesEl.textContent = `↓ ${formatBytes(t.network.rx_bps || 0)} | ↑ ${formatBytes(t.network.tx_bps || 0)}`;

    // 7. RAM & Swap
    if (t.ram) {
      const rPct = Math.min(100, Math.max(0, t.ram.percent || 0));
      const ramCol = getUsageSpectrum(rPct, 70, 85);
      if (ramPercentEl) {
        ramPercentEl.textContent = rPct;
        applyDynamicSpectrum(ramPercentEl, ramCol);
      }
      if (ramTextEl) {
        ramTextEl.textContent = `${(t.ram.used_mb / 1024).toFixed(1)} / ${(t.ram.total_mb / 1024).toFixed(1)} GB`;
        applyDynamicSpectrum(ramTextEl, ramCol);
      }
      if (ramSubtextEl) ramSubtextEl.textContent = `Disp: ${(t.ram.available_mb / 1024).toFixed(1)} GB | Cache: ${(t.ram.cached_mb / 1024).toFixed(1)} GB`;
      applyBarSpectrum(ramBarEl, rPct, ramCol);
    }

    if (t.swap) {
      const sPct = Math.min(100, Math.max(0, t.swap.percent || 0));
      const swapCol = getUsageSpectrum(sPct, 35, 60);
      if (swapTextEl) {
        swapTextEl.textContent = `${(t.swap.used_mb / 1024).toFixed(1)} / ${(t.swap.total_mb / 1024).toFixed(1)} GB (${sPct}%)`;
        applyDynamicSpectrum(swapTextEl, swapCol);
      }
      applyBarSpectrum(swapBarEl, sPct, swapCol);
    }
  }

  // -------------------------------------------------------------
  // PERFORMANCE MODE
  // -------------------------------------------------------------
  // Called from the render sequence, not from renderTelemetry, and for a
  // reason that was a bug rather than a preference: it used to be the last
  // statement of renderTelemetry, so `if (!t) return` at its top meant the
  // performance card, the header switch and the error banner never rendered
  // at all when telemetry was absent. The state it reads is a decision, not
  // a reading, and it does not come from the telemetry block.
  function renderPerformance() {
    const p = currentState && currentState.performance;
    if (!p) return;
  
    if (perfStateEl) {
      perfStateEl.textContent = p.yielding ? 'YIELD' : 'FULL';
      applyDynamicSpectrum(perfStateEl, p.yielding ? C_ACC() : C_IDLE());
    }
    if (perfSourceEl) {
      // Who is in charge, stated plainly. Nothing automatic is: the
      // detector reports what is animating and stops there, so "the
      // detector has the mode" would be a lie, and a user who believed it
      // would be waiting for a switch that nobody throws.
      perfSourceEl.textContent = p.manual ? 'you' : 'hands off';
      applyDynamicSpectrum(perfSourceEl, p.manual ? C_ACC() : C_TEXT());
    }
    if (perfScreensEl) {
      const presi = new Set(p.gpu_free || []);
      const righe = Object.entries(p.screens || {}).map(([cid, wp]) => {
        let testo = wp === 'cyberdeck.instrument.field' ? 'ours' : wp;
        if (presi.has(String(cid))) testo += ' (held back)';
        return `${cid}: ${testo}`;
      });
      const anima = p.animating_elsewhere || [];
      if (anima.length) righe.push(`animating: ${anima.join(', ')}`);
      perfScreensEl.textContent = righe.length ? righe.join('  ') : 'none';
    }
    if (perfBtnFull) perfBtnFull.classList.toggle('active', !p.yielding && !p.manual);
    if (perfBtnYield) perfBtnYield.classList.toggle('active', p.yielding && p.manual);
    if (perfBtnAuto) perfBtnAuto.classList.toggle('active', !p.manual);

    // The header switches show the same three states. The quick one is a
    // toggle rather than a cycle, so one tap always means the opposite of
    // what is on screen, and never a third thing.
    if (perfQuickLabel) {
      perfQuickLabel.textContent = p.yielding ? '[GPU YIELD]' : '[GPU FULL]';
    }
    if (perfQuickBtn) {
      perfQuickBtn.classList.toggle('yielding', !!p.yielding);
      perfQuickBtn.setAttribute('aria-pressed', p.yielding ? 'true' : 'false');
    }
    if (perfQuickAutoBtn) {
      perfQuickAutoBtn.classList.toggle('active', !p.manual);
    }

    // A command that failed says so here. Without it the page re-renders
    // from state a second later, unchanged, and a switch that did nothing
    // is indistinguishable from a switch that is not connected to
    // anything -- which is exactly what happened for as long as the
    // server could not find `cyberhud` on its PATH.
    if (perfErrorEl) {
      if (p.error) {
        perfErrorEl.textContent = p.error;
        perfErrorEl.style.display = 'block';
      } else {
        perfErrorEl.style.display = 'none';
        perfErrorEl.textContent = '';
      }
    }
  }

  // -------------------------------------------------------------
  // TAB 3: COMMANDDECK WORKSTATION CONTROLS
  // -------------------------------------------------------------
  let lastLaunchersSignature = '';
  function renderCommandDeck() {
    const t = currentState.telemetry;
    if (!t) return;


    // Power Profiles
    const currentProfile = t.system.power_profile || 'balanced';
    profileBtns.forEach(btn => {
      const p = btn.getAttribute('data-profile');
      btn.classList.toggle('active', p === currentProfile);
    });

    // Custom App Launchers
    if (customLaunchersGrid) {
      const launchers = currentState.launchers || [];
      const sig = JSON.stringify(launchers);
      if (sig !== lastLaunchersSignature) {
        lastLaunchersSignature = sig;
        customLaunchersGrid.innerHTML = '';
        if (!launchers.length) {
          customLaunchersGrid.innerHTML = `
            <div style="grid-column:1/-1; padding:12px; background:rgba(255,255,255,0.02); border:1px dashed var(--rule-soft); border-radius:0; font-size:0.75rem; color:var(--text-dim); text-align:center;">
              No launcher configured. Add your own commands in the <code>launchers</code> section of <code>~/.config/cyberdeck/config.yaml</code>.
            </div>
          `;
        } else {
          launchers.forEach(l => {
            const tile = document.createElement('div');
            tile.className = 'action-tile';
            tile.innerHTML = `
              <div style="font-size:1.4rem;">🚀</div>
              <span>${l.label || l.id}</span>
              ${l.sublabel ? `<small style="font-size:0.65rem; color:var(--text-dim);">${l.sublabel}</small>` : ''}
            `;
            tile.addEventListener('click', () => {
              sendAction({ type: 'launch_app', app_id: l.id });
            });
            customLaunchersGrid.appendChild(tile);
          });
        }
      }
    }
  }


  // Power Profiles Buttons
  profileBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const profile = btn.getAttribute('data-profile');
      profileBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sendAction({ type: 'power_profile_set', profile: profile });
    });
  });

  // Performance mode
  //
  // Three states, three buttons. FULL and YIELD are the user's choice and
  // stop the detector; AUTO hands it back. The third one existed on the
  // command line from the start and was never wired here, which made a
  // manual choice permanent from inside this deck: the page offered no way
  // out of a choice it offered a way into.
  const impostaPerformance = (on) => {
    sendAction({ type: 'performance_mode_set', on: on });
  };
  const impostaPerformanceAuto = () => {
    sendAction({ type: 'performance_mode_auto' });
  };
  if (perfBtnFull) {
    perfBtnFull.addEventListener('click', () => impostaPerformance(false));
  }
  if (perfBtnYield) {
    perfBtnBtnGuard(perfBtnYield, () => impostaPerformance(true));
  }
  if (perfBtnAuto) {
    perfBtnAuto.addEventListener('click', impostaPerformanceAuto);
  }
  if (perfQuickBtn) {
    // A toggle, not a cycle: one tap always means the opposite of the
    // state on screen, never a third thing nobody asked for.
    perfQuickBtn.addEventListener('click', () => {
      const yielding = !!(currentState && currentState.performance
                          && currentState.performance.yielding);
      impostaPerformance(yielding ? false : true);
    });
  }
  if (perfQuickAutoBtn) {
    perfQuickAutoBtn.addEventListener('click', impostaPerformanceAuto);
  }

  // YIELD stops animated wallpapers, so it is the one worth confirming
  // before it happens. Not FULL and not AUTO: those put things back.
  function perfBtnBtnGuard(btn, action) {
    btn.addEventListener('click', () => {
      openConfirmModal(
        'Free the whole GPU?',
        'The audio spectrum stops, and any animated wallpaper is swapped for the static one. It comes back when you set FULL or AUTO.',
        action
      );
    });
  }

  // Session & Workspace Buttons
  const btnLockSession = document.getElementById('btn-lock-session');
  if (btnLockSession) {
    btnLockSession.addEventListener('click', () => {
      sendAction({ type: 'session_lock' });
    });
  }

  const btnDisplayDpms = document.getElementById('btn-display-dpms');
  if (btnDisplayDpms) {
    btnDisplayDpms.addEventListener('click', () => {
      sendAction({ type: 'display_dpms', state: 'off' });
    });
  }

  const btnPrevDesktop = document.getElementById('btn-prev-desktop');
  if (btnPrevDesktop) {
    btnPrevDesktop.addEventListener('click', () => {
      sendAction({ type: 'desktop_nav', direction: 'prev' });
    });
  }

  const btnNextDesktop = document.getElementById('btn-next-desktop');
  if (btnNextDesktop) {
    btnNextDesktop.addEventListener('click', () => {
      sendAction({ type: 'desktop_nav', direction: 'next' });
    });
  }

  // Power Management Buttons with Confirmation Modal
  const btnSuspend = document.getElementById('btn-suspend');
  if (btnSuspend) {
    btnSuspend.addEventListener('click', () => {
      openConfirmModal(
        'Suspend Workstation',
        'The computer will enter low-power suspend mode.',
        () => sendAction({ type: 'system_power', action: 'suspend' })
      );
    });
  }

  const btnReboot = document.getElementById('btn-reboot');
  if (btnReboot) {
    btnReboot.addEventListener('click', () => {
      openConfirmModal(
        'Restart Workstation',
        'Are you sure you want to restart the system? The remote connection will be temporarily interrupted.',
        () => sendAction({ type: 'system_power', action: 'reboot' })
      );
    });
  }

  const btnPoweroff = document.getElementById('btn-poweroff');
  if (btnPoweroff) {
    btnPoweroff.addEventListener('click', () => {
      openConfirmModal(
        'Power Off Workstation',
        'Are you sure you want to fully shut down the computer? It will not be possible to turn it back on remotely without Wake-on-LAN.',
        () => sendAction({ type: 'system_power', action: 'poweroff' })
      );
    });
  }

  // Modal Dialog
  function openConfirmModal(title, description, onConfirm) {
    triggerHaptic(50);
    modalTitle.textContent = title;
    modalDesc.textContent = description;
    modalCallback = onConfirm;
    confirmModal.classList.add('active');
  }

  function closeConfirmModal() {
    confirmModal.classList.remove('active');
    modalCallback = null;
  }

  if (modalBtnCancel) {
    modalBtnCancel.addEventListener('click', () => {
      triggerHaptic(20);
      closeConfirmModal();
    });
  }

  if (modalBtnConfirm) {
    modalBtnConfirm.addEventListener('click', () => {
      triggerHaptic(80);
      if (typeof modalCallback === 'function') {
        modalCallback();
      }
      closeConfirmModal();
    });
  }



  // Initial Immediate State Fetch (Zero Delay Startup)
  async function fetchInitialState() {
    try {
      const url = authToken ? `/api/state?token=${encodeURIComponent(authToken)}` : '/api/state';
      const headers = { 'Accept': 'application/json' };
      if (authToken) {
        headers['Authorization'] = 'Bearer ' + authToken;
      }
      const res = await fetch(url, { headers });
      if (res.ok) {
        const payload = await res.json();
        currentState = payload;
        renderState();
      }
    } catch (e) {
      console.debug('Initial state fetch deferred to WS:', e);
    }
  }

  // Initial Mode & Viewport Setup
  const savedMode = localStorage.getItem('cyberdeck_view_mode');
  const isDesktopScreen = window.innerWidth >= 1024;
  const initialMode = savedMode || (isDesktopScreen ? 'desktop' : 'mobile');
  setViewMode(initialMode);
  const urlParams = new URLSearchParams(window.location.search);
  const requestedTab = urlParams.get('tab') || window.location.hash.replace('#', '');
  if (requestedTab && ['workstation', 'audio', 'telemetry', 'commands'].includes(requestedTab)) {
    switchTab(requestedTab);
  } else if (initialMode === 'desktop') {
    switchTab('workstation');
  } else {
    switchTab('audio');
  }

  // Start System & WebSocket
  fetchInitialState();
  connectWebSocket();

})();
