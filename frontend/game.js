// Global error reporting
window.addEventListener("error", (e) => console.error("❌", e.error || e.message));
window.addEventListener("unhandledrejection", (e) => console.error("❌ Unhandled Promise Rejection:", e.reason));

// OpenClaw Office UI - Main Game Logic
// Dependencies: layout.js (must load before this)

// ── WebP detection ──────────────────────────────────────────────────
let supportsWebP = false;

function checkWebPSupport() {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas');
    if (canvas.getContext && canvas.getContext('2d')) {
      resolve(canvas.toDataURL('image/webp').indexOf('data:image/webp') === 0);
    } else {
      resolve(false);
    }
  });
}

function checkWebPSupportFallback() {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = 'data:image/webp;base64,UklGRkoAAABXRUJQVlA4WAoAAAAQAAAAAAAAAAAAQUxQSAwAAAABBxAR/Q9ERP8DAABWUDggGAAAADABAJ0BKgEAAQADADQlpAADcAD++/1QAA==';
  });
}

function getExt(pngFile) {
  if (pngFile === 'star-working-spritesheet.png') return '.png';
  return supportsWebP ? '.webp' : '.png';
}

// ── Game config ─────────────────────────────────────────────────────
const gameConfig = {
  type: Phaser.AUTO,
  width: LAYOUT.game.width,
  height: LAYOUT.game.height,
  parent: 'game-container',
  pixelArt: true,
  physics: { default: 'arcade', arcade: { gravity: { y: 0 }, debug: false } },
  scene: { preload: preload, create: create, update: update }
};

// ── State ───────────────────────────────────────────────────────────
let game;
let totalAssets = 0, loadedAssets = 0;
let loadingOverlay, loadingProgressBar, loadingText;

// Agent sprite mapping: agentId -> { name, role }
const AGENT_SPRITE_MAP = {
  star:       'codemaster',
  codemaster: 'codemaster',
  rook:       'rook',
  main:       'rook',
  nova:       'nova',
  ralph:      'ralph'
};

const STATES = {
  idle:        { name: 'Idle',        area: 'breakroom' },
  writing:     { name: 'Writing',     area: 'writing' },
  researching: { name: 'Researching', area: 'researching' },
  executing:   { name: 'Executing',   area: 'writing' },
  syncing:     { name: 'Syncing',     area: 'command' },
  error:       { name: 'Error',       area: 'error' },
  sleeping:    { name: 'Sleeping',    area: 'breakroom' }
};

let currentState = 'idle', pendingDesiredState = null;
let statusText, lastFetch = 0, lastBubble = 0;
let typewriterText = '', typewriterTarget = '', typewriterIndex = 0, lastTypewriter = 0;
const FETCH_INTERVAL = 2000;
const BUBBLE_INTERVAL = 8000;
const TYPEWRITER_DELAY = 50;

// Agent tracking
let agents = {}; // agentId -> { container, sprite, nameTag, statusDot, state, targetX, targetY, ... }
let lastAgentsFetch = 0;
const AGENTS_FETCH_INTERVAL = 2500;

// Dynamic rooms
let OFFICE_ROOMS = {};

// Context pressure (CM-12)
let contextPressureData = {};
let lastPressureFetch = 0;
const PRESSURE_FETCH_INTERVAL = 30000;

// Conduits (CM-13)
let conduitZones = {}, conduitActivity = {}, conduitGraphics = null, conduitParticles = [];
let lastConduitFetch = 0;
const CONDUIT_FETCH_INTERVAL = 30000;

// Room navigation (CM-7)
let officeRooms = {}, roomGraphics = null, navigationTarget = null, mainAgentArea = 'breakroom';
let roomLabels = {};

// Live chat feed
let _liveChatMessages = [];
const CHAT_POLL_INTERVAL = 5000;
const AGENT_COLORS = {
  'Rook': 'rook', 'Ralph': 'ralph', 'Nova': 'nova',
  'CodeMaster': 'codemaster', 'Dustin': 'dustin'
};

// Drag-to-pan state
let isPanning = false, panStartX = 0, panStartY = 0, panOffsetX = 0, panOffsetY = 0;

// Cat
let lastCatBubble = 0;
const CAT_BUBBLE_INTERVAL = 18000;

// Coordinates overlay
let coordsOverlay, coordsDisplay, coordsToggle, showCoords = false;

// ── Bubble texts ────────────────────────────────────────────────────
const BUBBLE_TEXTS = {
  idle: [
    'Idle: ears perked up', 'Ready to work', 'Giving the brain a break',
    'Waiting for the perfect moment', 'Coffee\'s still hot',
    'Buffing you in the background', 'Status: Resting',
    'The cat says: slow down'
  ],
  writing: [
    'Focus mode: do not disturb', 'Nailing down the critical path',
    'Making complex things simple', 'Locking bugs in a cage',
    'Halfway through, saving now', 'Everything rollback-ready',
    'Converging first, diverging later', 'Stay steady, we can win'
  ],
  researching: [
    'Digging through evidence', 'Simmering info into conclusions',
    'Found it: key point here', 'Controlling variables first',
    'Researching: why does this happen?', 'Turning intuition into verification',
    'Locate first, optimize later'
  ],
  executing: [
    'Executing: don\'t blink', 'Slicing tasks into pieces',
    'Starting the pipeline', 'One-click deploy: here we go',
    'Let results speak', 'MVP first, beautiful version later'
  ],
  syncing: [
    'Syncing: locking into the cloud', 'Backup is security',
    'Writing... don\'t unplug', 'Cloud alignment: click',
    'Saving future me from disaster'
  ],
  error: [
    'Alarm ringing: stay calm', 'I smell a bug',
    'Reproduce first, then fix', 'Give me the logs',
    'Errors aren\'t enemies, they\'re clues', 'Stop the bleeding first',
    'I\'m on it: root cause soon'
  ],
  cat: [
    'Meow~', 'Purrrr...', 'Wagging tail', 'So happy basking in the sun',
    'Someone\'s visiting!', 'I\'m the office mascot', 'Stretching',
    'Is today\'s treat ready?', 'Best view from this spot'
  ]
};

// Agent name/status colors
const NAME_TAG_COLORS = {
  approved: '#22c55e', pending: '#f59e0b', rejected: '#ef4444',
  offline: '#64748b', default: '#e2e8f0'
};

// ── Memo ────────────────────────────────────────────────────────────
async function loadMemo() {
  const memoDate = document.getElementById('memo-date');
  const memoContent = document.getElementById('memo-content');
  try {
    const response = await fetch('/yesterday-memo?t=' + Date.now(), { cache: 'no-store' });
    const data = await response.json();
    if (data.memo) {
      if (memoDate) memoDate.textContent = data.date || '';
      const escaped = data.memo.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      if (memoContent) memoContent.innerHTML = escaped.replace(/\n/g, '<br>');
    } else {
      if (memoContent) memoContent.innerHTML = '<div id="memo-placeholder">No yesterday notes</div>';
    }
  } catch (e) {
    console.error('Failed to load memo:', e);
    if (memoContent) memoContent.innerHTML = '<div id="memo-placeholder">Load failed</div>';
  }
}

// ── Loading progress ────────────────────────────────────────────────
function updateLoadingProgress() {
  loadedAssets++;
  const percent = Math.min(100, Math.round((loadedAssets / totalAssets) * 100));
  if (loadingProgressBar) loadingProgressBar.style.width = percent + '%';
  if (loadingText) loadingText.textContent = `Loading OpenClaw Office... ${percent}%`;
}

function hideLoadingOverlay() {
  setTimeout(() => {
    if (loadingOverlay) {
      loadingOverlay.style.transition = 'opacity 0.5s ease';
      loadingOverlay.style.opacity = '0';
      setTimeout(() => { loadingOverlay.style.display = 'none'; }, 500);
    }
  }, 300);
}

// ── Dynamic Room System ─────────────────────────────────────────────
async function loadOfficeRooms() {
  try {
    const resp = await fetch('/office/rooms');
    if (resp.ok) {
      const data = await resp.json();
      const rooms = data.rooms || [];
      for (const room of rooms) {
        OFFICE_ROOMS[room.id] = room;
        if (!AREA_POSITIONS[room.id]) {
          const basePos = LAYOUT.areas[room.id] || { x: 640, y: 360 };
          AREA_POSITIONS[room.id] = [
            { x: basePos.x, y: basePos.y },
            { x: basePos.x + 30, y: basePos.y + 20 },
            { x: basePos.x - 30, y: basePos.y + 20 },
            { x: basePos.x + 30, y: basePos.y - 20 },
            { x: basePos.x - 30, y: basePos.y - 20 }
          ];
        }
      }
      console.log(`[Office] Loaded ${rooms.length} rooms`);
    }
  } catch (e) {
    console.warn('[Office] Failed to load rooms:', e);
  }
}

// Furniture icon mapping
const FURNITURE_ICONS = {
  server_rack: '🖥️', monitor: '📊', terminal: '💻', pipeline: '⚙️',
  chart: '📈', alert_board: '🚨', dashboard: '📊', gauge: '🎯',
  log_stream: '📜', bookshelf: '📚', easel: '🎨', speaker: '🔊',
  palette: '🎨', preview: '👁️', whiteboard: '📝', archive: '🗄️',
  linter: '🔍', coverage: '✅', pr_board: '📋', cron_board: '⏰',
  coffee: '☕', plant: '🌿', trophy: '🏆', clock: '🕐',
  lamp: '💡', printer: '🖨️', phone: '📞', calendar: '📅',
  tv: '📺', radio: '📻', globe: '🌐', toolbox: '🧰',
  shield: '🛡️', telescope: '🔭', microscope: '🔬', beaker: '🧪',
  satellite: '📡', battery: '🔋', plug: '🔌', wrench: '🔧',
  hammer: '🔨', gear: '⚙️', magnet: '🧲', bulb: '💡',
  podium: '🎤', water_cooler: '🚰', couch: '🛋️', desk: '🪑',
  filing_cabinet: '🗃️', safe: '🔐', map: '🗺️', compass: '🧭',
};

function drawRoomsOverlay(scene) {
  const graphics = scene.add.graphics();
  for (const roomId in OFFICE_ROOMS) {
    const room = OFFICE_ROOMS[roomId];
    const color = Phaser.Display.Color.StringToColor(room.color || '#888888');
    const positions = AREA_POSITIONS[roomId];
    if (positions && positions.length > 0) {
      const xs = positions.map(p => p.x);
      const ys = positions.map(p => p.y);
      const minX = Math.min(...xs) - 80;
      const minY = Math.min(...ys) - 50;
      const maxX = Math.max(...xs) + 80;
      const maxY = Math.max(...ys) + 50;
      const w = maxX - minX, h = maxY - minY;

      graphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.08);
      graphics.fillRoundedRect(minX, minY, w, h, 8);
      graphics.lineStyle(1, Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.25);
      graphics.strokeRoundedRect(minX, minY, w, h, 8);

      scene.add.text(minX + 8, minY + 4, room.name, {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: '8px',
        fill: 'white',
        stroke: '#000000',
        strokeThickness: 2
      }).setDepth(1000).setAlpha(0.6);

      const furniture = room.furniture || [];
      const furnitureW = w - 20, furnitureH = h - 24;
      for (let fi = 0; fi < furniture.length; fi++) {
        const item = furniture[fi];
        const fx = minX + 10 + (item.x || (fi / furniture.length)) * furnitureW;
        const fy = minY + 24 + (item.y || 0.5) * furnitureH;
        const icon = FURNITURE_ICONS[item.type] || '📦';
        scene.add.text(fx, fy, icon, { fontSize: '16px' }).setOrigin(0.5).setDepth(1001);
        if (item.label) {
          scene.add.text(fx, fy + 12, item.label, {
            fontFamily: 'ArkPixel, monospace', fontSize: '7px',
            fill: '#cccccc', stroke: '#000000', strokeThickness: 1
          }).setOrigin(0.5).setDepth(1001);
        }
      }
    }
  }
}

// ── State control ───────────────────────────────────────────────────
function setState(state, detail) {
  fetch('/set_state', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, detail })
  }).then(() => fetchStatus());
}

// ── Init ────────────────────────────────────────────────────────────
async function initGame() {
  console.log("🚀 initGame starting...");
  try { supportsWebP = await checkWebPSupport(); }
  catch (e) {
    try { supportsWebP = await checkWebPSupportFallback(); }
    catch (e2) { supportsWebP = false; }
  }
  console.log('WebP support:', supportsWebP);
  await loadOfficeRooms();
  new Phaser.Game(gameConfig);
}

// ── Preload ─────────────────────────────────────────────────────────
function preload() {
  loadingOverlay = document.getElementById('loading-overlay');
  loadingProgressBar = document.getElementById('loading-progress-bar');
  loadingText = document.getElementById('loading-text');
  totalAssets = LAYOUT.totalAssets || 22;
  loadedAssets = 0;

  this.load.on('filecomplete', () => updateLoadingProgress());
  this.load.on('complete', () => hideLoadingOverlay());

  // New office background
  this.load.image('office_bg', '/static/sprites/office-bg.png?v={{VERSION_TIMESTAMP}}');

  // Agent walk sprite sheets (12 frames: 3 down, 3 up, 3 left, 3 right)
  const FW = LAYOUT.agentSprite.frameWidth;
  const FH = LAYOUT.agentSprite.frameHeight;
  for (const name of ['codemaster', 'rook', 'nova', 'ralph']) {
    this.load.spritesheet(`${name}_walk`, `/static/sprites/${name}-walk.png`, { frameWidth: FW, frameHeight: FH });
    this.load.spritesheet(`${name}_idle`, `/static/sprites/${name}-idle.png`, { frameWidth: FW, frameHeight: FH });
    this.load.image(`${name}_talk`, `/static/sprites/${name}-talk.png`);
  }

  // Keep existing decorative assets that still work with new bg
  this.load.spritesheet('cats', '/static/cats-spritesheet' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 160, frameHeight: 160 });
}

// ── Create ──────────────────────────────────────────────────────────
function create() {
  game = this;

  // New background
  this.add.image(640, 360, 'office_bg').setDepth(0);

  // Create walk/idle animations for each agent
  for (const name of ['codemaster', 'rook', 'nova', 'ralph']) {
    // Walk: 12 frames = down(0-2), up(3-5), left(6-8), right(9-11)
    this.anims.create({ key: `${name}_walk_down`,  frames: this.anims.generateFrameNumbers(`${name}_walk`, { start: 0, end: 2 }), frameRate: LAYOUT.agentSprite.walkFrameRate, repeat: -1 });
    this.anims.create({ key: `${name}_walk_up`,    frames: this.anims.generateFrameNumbers(`${name}_walk`, { start: 3, end: 5 }), frameRate: LAYOUT.agentSprite.walkFrameRate, repeat: -1 });
    this.anims.create({ key: `${name}_walk_left`,  frames: this.anims.generateFrameNumbers(`${name}_walk`, { start: 6, end: 8 }), frameRate: LAYOUT.agentSprite.walkFrameRate, repeat: -1 });
    this.anims.create({ key: `${name}_walk_right`, frames: this.anims.generateFrameNumbers(`${name}_walk`, { start: 9, end: 11 }), frameRate: LAYOUT.agentSprite.walkFrameRate, repeat: -1 });
    // Idle: 3 frames (or fewer)
    const idleTexture = this.textures.get(`${name}_idle`);
    const idleFrameCount = idleTexture ? idleTexture.frameTotal - 1 : 3;
    this.anims.create({ key: `${name}_idle`, frames: this.anims.generateFrameNumbers(`${name}_idle`, { start: 0, end: Math.max(0, idleFrameCount - 1) }), frameRate: LAYOUT.agentSprite.idleFrameRate, repeat: -1 });
  }

  // Draw dynamic room overlays
  drawRoomsOverlay(this);

  // Cat
  const catsFrameCount = 16;
  if (game.textures.exists('cats')) {
    const cat = this.add.sprite(
      LAYOUT.furniture.cat.x, LAYOUT.furniture.cat.y,
      'cats', Math.floor(Math.random() * catsFrameCount)
    ).setOrigin(0.5).setDepth(LAYOUT.furniture.cat.depth);
    cat.setInteractive({ useHandCursor: true });
    cat.on('pointerdown', () => cat.setFrame(Math.floor(Math.random() * catsFrameCount)));
    window.catSprite = cat;
  }

  // Plaque
  const plaqueX = LAYOUT.plaque.x, plaqueY = LAYOUT.plaque.y;
  game.add.rectangle(plaqueX, plaqueY, LAYOUT.plaque.width, LAYOUT.plaque.height, 0x1a1a2e, 0.85)
    .setStrokeStyle(2, 0x3e8ec6).setDepth(2500);
  game.add.text(plaqueX, plaqueY, 'OpenClaw Office', {
    fontFamily: 'ArkPixel, monospace', fontSize: '18px',
    fill: '#3ec6e0', fontWeight: 'bold', stroke: '#000', strokeThickness: 2
  }).setOrigin(0.5).setDepth(2501);

  // Coords overlay
  statusText = document.getElementById('status-text');
  coordsOverlay = document.getElementById('coords-overlay');
  coordsDisplay = document.getElementById('coords-display');
  coordsToggle = document.getElementById('coords-toggle');
  if (coordsToggle) {
    coordsToggle.addEventListener('click', () => {
      showCoords = !showCoords;
      if (coordsOverlay) coordsOverlay.style.display = showCoords ? 'block' : 'none';
      coordsToggle.textContent = showCoords ? 'Hide Coords' : 'Show Coords';
      coordsToggle.style.background = showCoords ? '#e94560' : '#333';
    });
  }
  game.input.on('pointermove', (pointer) => {
    if (!showCoords || !coordsDisplay) return;
    const x = Math.round(Phaser.Math.Clamp(pointer.x, 0, gameConfig.width - 1));
    const y = Math.round(Phaser.Math.Clamp(pointer.y, 0, gameConfig.height - 1));
    coordsDisplay.textContent = `${x}, ${y}`;
    if (coordsOverlay) {
      coordsOverlay.style.left = (pointer.x + 18) + 'px';
      coordsOverlay.style.top = (pointer.y + 18) + 'px';
    }
  });

  // Drag-to-pan: allow grabbing the canvas to scroll the game container
  setupDragToPan();

  loadMemo();
  fetchStatus();
  fetchAgents();
  fetchContextPressure();
  initConduitVisualization();
  fetchConduits();
  fetchConduitActivity();
  fetchOfficeRoomsForNav();
  setupRoomNavigation();

  // Start live chat feed
  fetchLiveChat();
  setInterval(fetchLiveChat, CHAT_POLL_INTERVAL);

  console.log("✅ create() complete");
}

// ── Update loop ─────────────────────────────────────────────────────
function update(time) {
  if (time - lastFetch > FETCH_INTERVAL) { fetchStatus(); lastFetch = time; }
  if (time - lastAgentsFetch > AGENTS_FETCH_INTERVAL) { fetchAgents(); lastAgentsFetch = time; }
  if (time - lastPressureFetch > PRESSURE_FETCH_INTERVAL) { fetchContextPressure(); lastPressureFetch = time; }
  if (time - lastConduitFetch > CONDUIT_FETCH_INTERVAL) { fetchConduitActivity(); lastConduitFetch = time; }

  // Update all agent sprites (movement, animations)
  updateAllAgents(time);

  // Context pressure glows
  updateAllAgentGlows(time);

  // Conduits
  drawConduits(time);
  if (Object.keys(conduitZones).length > 0) updateConduitLabels();

  // Room navigation
  updateNavigation(time);

  // Bubbles
  if (time - lastBubble > BUBBLE_INTERVAL) { showRandomBubble(); lastBubble = time; }
  if (time - lastCatBubble > CAT_BUBBLE_INTERVAL) { showCatBubble(); lastCatBubble = time; }

  // Typewriter
  if (typewriterIndex < typewriterTarget.length && time - lastTypewriter > TYPEWRITER_DELAY) {
    typewriterText += typewriterTarget[typewriterIndex];
    if (statusText) statusText.textContent = typewriterText;
    typewriterIndex++;
    lastTypewriter = time;
  }
}

// ── Status fetching ─────────────────────────────────────────────────
function normalizeState(s) {
  if (!s) return 'idle';
  if (s === 'working') return 'writing';
  if (s === 'run' || s === 'running') return 'executing';
  if (s === 'sync') return 'syncing';
  if (s === 'research') return 'researching';
  return s;
}

function fetchStatus() {
  fetch('/status')
    .then(r => r.json())
    .then(data => {
      const nextState = normalizeState(data.state);
      const stateInfo = STATES[nextState] || STATES.idle;
      const nextLine = '[' + stateInfo.name + '] ' + (data.detail || '...');
      if (nextState !== currentState) {
        currentState = nextState;
        typewriterTarget = nextLine;
        typewriterText = '';
        typewriterIndex = 0;
      } else if (typewriterTarget !== nextLine) {
        typewriterTarget = nextLine;
        typewriterText = '';
        typewriterIndex = 0;
      }
    })
    .catch(() => {
      typewriterTarget = 'Connection failed, retrying...';
      typewriterText = '';
      typewriterIndex = 0;
    });
}

// ── Agent management ────────────────────────────────────────────────
function fetchAgents() {
  fetch('/agents?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (!Array.isArray(data)) return;
      const areaSlots = {};
      for (let agent of data) {
        const area = agent.area || 'breakroom';
        agent._slotIndex = areaSlots[area] || 0;
        areaSlots[area] = (areaSlots[area] || 0) + 1;
        renderAgent(agent);
        if (agent.agentId === 'star' || agent.isMain) {
          mainAgentArea = area;
        }
      }
      // Remove stale agents
      const currentIds = new Set(data.map(a => a.agentId));
      for (let id in agents) {
        if (!currentIds.has(id)) {
          if (agents[id] && agents[id].container) {
            agents[id].container.destroy();
          }
          delete agents[id];
        }
      }
    })
    .catch(e => console.error('Failed to fetch agents:', e));
}

function getAreaPosition(area, slotIndex) {
  const positions = AREA_POSITIONS[area] || AREA_POSITIONS.breakroom;
  return positions[(slotIndex || 0) % positions.length];
}

function getSpriteKey(agentId) {
  // Map agent ID to sprite sheet name
  const lower = (agentId || '').toLowerCase();
  return AGENT_SPRITE_MAP[lower] || 'codemaster'; // fallback
}

function renderAgent(agent) {
  const agentId = agent.agentId;
  const name = agent.name || 'Agent';
  const area = agent.area || 'breakroom';
  const agentState = normalizeState(agent.state) || 'idle';
  const authStatus = agent.authStatus || 'pending';
  const isMain = !!agent.isMain;
  const spriteKey = getSpriteKey(agentId);

  const pos = getAreaPosition(area, agent._slotIndex || 0);
  const targetX = pos.x;
  const targetY = pos.y;

  // Alpha based on status
  let alpha = 1;
  if (authStatus === 'pending') alpha = 0.7;
  if (authStatus === 'rejected') alpha = 0.4;
  if (authStatus === 'offline') alpha = 0.5;
  if (agentState === 'sleeping') alpha = 0.5;

  const nameColor = NAME_TAG_COLORS[authStatus] || NAME_TAG_COLORS.default;

  if (!agents[agentId]) {
    // ── Create new agent sprite ──
    const container = game.add.container(targetX, targetY);
    container.setDepth(1200 + (isMain ? 100 : 0));

    // Sprite (using idle animation initially)
    const sprite = game.add.sprite(0, 0, `${spriteKey}_idle`, 0);
    sprite.setScale(LAYOUT.agentSprite.scale);
    sprite.setOrigin(0.5, 1); // anchor at feet
    sprite.name = 'sprite';

    // Play idle animation
    const idleKey = `${spriteKey}_idle`;
    if (game.anims.exists(idleKey)) {
      sprite.play(idleKey);
    }

    // Make clickable
    sprite.setInteractive(
      new Phaser.Geom.Rectangle(-20, -50, 40, 55),
      Phaser.Geom.Rectangle.Contains
    );
    sprite.on('pointerdown', () => {
      if (typeof window.openAgentPanel === 'function') {
        window.openAgentPanel(agentId);
      }
    });

    // Name tag (above sprite)
    const nameTag = game.add.text(0, -sprite.displayHeight - 8, name, {
      fontFamily: 'ArkPixel, monospace', fontSize: '12px',
      fill: nameColor, stroke: '#000', strokeThickness: 3
    }).setOrigin(0.5);
    nameTag.name = 'nameTag';

    // Status dot
    let dotColor = getDotColor(authStatus);
    const statusDot = game.add.circle(22, -sprite.displayHeight + 5, 4, dotColor, alpha);
    statusDot.setStrokeStyle(1.5, 0x000000, alpha);
    statusDot.name = 'statusDot';

    // Progress bar
    const barW = 36, barH = 3;
    const barBg = game.add.rectangle(0, -sprite.displayHeight - 22, barW, barH, 0x000000, 0.5);
    barBg.setStrokeStyle(1, 0xffffff, 0.3);
    const barFill = game.add.rectangle(-barW / 2, -sprite.displayHeight - 22, 0, barH, 0x22c55e);
    barFill.setOrigin(0, 0.5);
    barFill.name = 'progressFill';

    container.add([sprite, statusDot, nameTag, barBg, barFill]);

    // Update progress bar
    const progress = Math.min(100, Math.max(0, agent.progress || 0));
    barFill.width = (barW * progress) / 100;

    agents[agentId] = {
      container,
      sprite,
      spriteKey,
      targetX,
      targetY,
      currentState: agentState,
      area,
      isMoving: false,
      lastArea: area
    };

    container.setAlpha(alpha);
  } else {
    // ── Update existing agent ──
    const agentData = agents[agentId];
    const container = agentData.container;

    // Update target position (agent will move there in updateAllAgents)
    agentData.targetX = targetX;
    agentData.targetY = targetY;
    agentData.currentState = agentState;
    agentData.area = area;

    container.setAlpha(alpha);
    container.setDepth(1200 + (isMain ? 100 : 0));

    // Update name tag
    const nameTag = container.list.find(c => c.name === 'nameTag');
    if (nameTag) {
      nameTag.setText(name);
      nameTag.setFill(nameColor);
    }

    // Update status dot
    const statusDot = container.list.find(c => c.name === 'statusDot');
    if (statusDot) {
      statusDot.fillColor = getDotColor(authStatus);
    }

    // Update progress bar
    const progress = Math.min(100, Math.max(0, agent.progress || 0));
    const barFill = container.list.find(c => c.name === 'progressFill');
    if (barFill) {
      barFill.width = (36 * progress) / 100;
    }

    // If sprite key changed (different agent type), swap sprite
    if (agentData.spriteKey !== spriteKey) {
      agentData.spriteKey = spriteKey;
      const sprite = container.list.find(c => c.name === 'sprite');
      if (sprite) {
        const idleKey = `${spriteKey}_idle`;
        if (game.anims.exists(idleKey)) sprite.play(idleKey);
      }
    }
  }
}

function getDotColor(authStatus) {
  if (authStatus === 'approved') return 0x22c55e;
  if (authStatus === 'pending') return 0xf59e0b;
  if (authStatus === 'rejected') return 0xef4444;
  if (authStatus === 'offline') return 0x94a3b8;
  return 0x64748b;
}

// ── Agent movement & animation ──────────────────────────────────────
function updateAllAgents(time) {
  for (const agentId in agents) {
    const a = agents[agentId];
    if (!a || !a.container || !a.container.active) continue;

    const container = a.container;
    const sprite = container.list.find(c => c.name === 'sprite');
    if (!sprite) continue;

    const dx = a.targetX - container.x;
    const dy = a.targetY - container.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const speed = LAYOUT.agentSprite.walkSpeed;

    if (dist > 4) {
      // Moving toward target
      container.x += (dx / dist) * speed;
      container.y += (dy / dist) * speed;

      // Determine walk direction
      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);
      let dir;
      if (absDx > absDy) {
        dir = dx > 0 ? 'right' : 'left';
      } else {
        dir = dy > 0 ? 'down' : 'up';
      }

      const walkKey = `${a.spriteKey}_walk_${dir}`;
      if (game.anims.exists(walkKey) && (!sprite.anims.isPlaying || sprite.anims.currentAnim?.key !== walkKey)) {
        sprite.play(walkKey);
      }

      a.isMoving = true;
    } else {
      // Arrived at target
      if (a.isMoving) {
        a.isMoving = false;
        // Switch to idle animation
        const idleKey = `${a.spriteKey}_idle`;
        if (game.anims.exists(idleKey)) {
          sprite.play(idleKey);
        }
      }

      // Sleeping effect: gentle bob + dimming
      if (a.currentState === 'sleeping') {
        sprite.setAlpha(0.5 + 0.1 * Math.sin(time / 1000));
      }

      // Subtle idle bob
      if (!a.isMoving) {
        const bob = Math.sin(time / 800 + (agentId.charCodeAt(0) || 0)) * 1.5;
        sprite.y = bob;
      }
    }

    // Sort depth by y-position (agents lower on screen render on top)
    container.setDepth(1200 + Math.floor(container.y));
  }
}

// ── Chat bubbles ────────────────────────────────────────────────────
let activeBubbles = []; // { container, agentId, expireAt }

function showRandomBubble() {
  if (currentState === 'idle') return;

  // Pick a random active agent to show a bubble
  const agentIds = Object.keys(agents);
  if (agentIds.length === 0) return;

  const agentId = agentIds[Math.floor(Math.random() * agentIds.length)];
  const a = agents[agentId];
  if (!a || !a.container) return;

  const state = a.currentState || 'idle';
  const texts = BUBBLE_TEXTS[state] || BUBBLE_TEXTS.idle;
  const text = texts[Math.floor(Math.random() * texts.length)];

  showAgentBubble(agentId, text);
}

function showAgentBubble(agentId, text) {
  const a = agents[agentId];
  if (!a || !a.container) return;

  // Remove existing bubble for this agent
  activeBubbles = activeBubbles.filter(b => {
    if (b.agentId === agentId) { b.container.destroy(); return false; }
    return true;
  });

  const spriteKey = a.spriteKey;
  const anchorX = a.container.x;
  const anchorY = a.container.y - 80;

  // Create bubble container
  const bubbleContainer = game.add.container(0, 0);
  bubbleContainer.setDepth(LAYOUT.bubble.depth);

  // Talking headshot portrait (left of bubble)
  const talkKey = `${spriteKey}_talk`;
  if (game.textures.exists(talkKey)) {
    const portrait = game.add.image(anchorX - 80, anchorY, talkKey);
    portrait.setScale(0.65);
    portrait.setOrigin(0.5);
    // Portrait frame
    const frame = game.add.rectangle(anchorX - 80, anchorY, 50, 50, 0x000000, 0)
      .setStrokeStyle(2, 0x3ec6e0, 0.8);
    bubbleContainer.add([frame, portrait]);
  }

  // Bubble background
  const textWidth = Math.min(text.length * 8 + 16, LAYOUT.bubble.maxWidth);
  const bg = game.add.rectangle(anchorX + 10, anchorY, textWidth, 26, 0x1a1a2e, 0.92);
  bg.setStrokeStyle(1.5, 0x3ec6e0, 0.7);
  bg.setOrigin(0.5);

  // Bubble text
  const txt = game.add.text(anchorX + 10, anchorY, text, {
    fontFamily: 'ArkPixel, monospace', fontSize: '11px',
    fill: '#e0e0e0', align: 'center',
    wordWrap: { width: LAYOUT.bubble.maxWidth - 16 }
  }).setOrigin(0.5);

  // Bubble tail (small triangle pointing down)
  const tail = game.add.triangle(anchorX, anchorY + 14, 0, 0, 10, 0, 5, 8, 0x1a1a2e, 0.92);
  tail.setStrokeStyle(1, 0x3ec6e0, 0.5);

  bubbleContainer.add([bg, txt, tail]);

  activeBubbles.push({
    container: bubbleContainer,
    agentId,
    expireAt: Date.now() + LAYOUT.bubble.duration
  });

  // Auto-cleanup
  setTimeout(() => {
    activeBubbles = activeBubbles.filter(b => {
      if (b.agentId === agentId && b.container === bubbleContainer) {
        b.container.destroy();
        return false;
      }
      return true;
    });
  }, LAYOUT.bubble.duration);
}

function showCatBubble() {
  if (!window.catSprite) return;
  if (window.catBubble) { window.catBubble.destroy(); window.catBubble = null; }
  const texts = BUBBLE_TEXTS.cat;
  const text = texts[Math.floor(Math.random() * texts.length)];
  const anchorX = window.catSprite.x;
  const anchorY = window.catSprite.y - 60;
  const bg = game.add.rectangle(anchorX, anchorY, text.length * 9 + 16, 22, 0xfffbeb, 0.92);
  bg.setStrokeStyle(1.5, 0xd4a574);
  const txt = game.add.text(anchorX, anchorY, text, {
    fontFamily: 'ArkPixel, monospace', fontSize: '10px', fill: '#8b6914', align: 'center'
  }).setOrigin(0.5);
  window.catBubble = game.add.container(0, 0, [bg, txt]);
  window.catBubble.setDepth(2100);
  setTimeout(() => { if (window.catBubble) { window.catBubble.destroy(); window.catBubble = null; } }, 4000);
}

// ── Context Pressure (CM-12) ────────────────────────────────────────
function fetchContextPressure() {
  fetch('/office/context-pressure?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (!data.ok || !Array.isArray(data.agents)) return;
      data.agents.forEach(agent => {
        if (agent.agentId && agent.context_usage_pct !== undefined) {
          contextPressureData[agent.agentId] = {
            usage: agent.context_usage_pct,
            last_update: Date.now()
          };
        }
      });
    })
    .catch(() => {});
}

function updateAgentGlow(agentId, container) {
  const pressure = contextPressureData[agentId];
  if (!pressure) {
    const glow = container.list ? container.list.find(c => c.name === 'glow') : null;
    if (glow) glow.destroy();
    return;
  }

  const usage = pressure.usage;
  let glowColor = 0x22c55e;
  if (usage >= 80) glowColor = 0xf59e0b;
  if (usage >= 90) glowColor = 0xef4444;

  const baseRadius = 30 + Math.min(usage / 100 * 30, 30);
  let alpha = 0.15 + usage / 100 * 0.3;
  if (usage >= 90) alpha = 0.3 + 0.2 * Math.sin(Date.now() / 300);

  let glow = container.list ? container.list.find(c => c.name === 'glow') : null;
  if (!glow) {
    glow = game.add.graphics();
    glow.name = 'glow';
    container.add(glow);
    container.sendToBack(glow);
  }
  glow.clear();
  glow.fillStyle(glowColor, alpha);
  glow.fillCircle(0, -20, baseRadius);
}

function updateAllAgentGlows(time) {
  for (let agentId in agents) {
    if (agents[agentId] && agents[agentId].container && agents[agentId].container.active) {
      updateAgentGlow(agentId, agents[agentId].container);
    }
  }
}

// ── Conduits (CM-13) ────────────────────────────────────────────────
function fetchConduits() {
  fetch('/office/conduits?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => { if (data.ok && data.conduits) conduitZones = data.conduits; })
    .catch(() => {});
}

function fetchConduitActivity() {
  fetch('/office/conduits/activity?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => { if (data.ok && data.activity) conduitActivity = data.activity; })
    .catch(() => {});
}

function initConduitVisualization() {
  if (!conduitGraphics) {
    conduitGraphics = game.add.graphics();
    conduitGraphics.setDepth(900);
  }
}

function getZonePosition(zoneId, index, total) {
  const cw = LAYOUT.game.width, ch = LAYOUT.game.height;
  const padding = 80;
  const y = ch - 50;
  const spacing = (cw - padding * 2) / (total - 1 || 1);
  return { x: padding + index * spacing, y };
}

function drawConduits(time) {
  if (!conduitGraphics) return;
  conduitGraphics.clear();
  const zoneIds = Object.keys(conduitZones);
  if (zoneIds.length === 0) return;

  const positions = {};
  zoneIds.forEach((id, idx) => { positions[id] = getZonePosition(id, idx, zoneIds.length); });

  for (let i = 0; i < zoneIds.length; i++) {
    for (let j = i + 1; j < zoneIds.length; j++) {
      const idA = zoneIds[i], idB = zoneIds[j];
      const combined = (conduitActivity[idA]?.calls || 0) + (conduitActivity[idB]?.calls || 0);
      const intensity = Math.min(combined / 20, 1);
      if (intensity < 0.05) continue;

      const posA = positions[idA], posB = positions[idB];
      const color = Phaser.Display.Color.StringToColor(conduitZones[idA].color);
      conduitGraphics.lineStyle(2 + intensity * 4, Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.3 + intensity * 0.7);
      conduitGraphics.beginPath();
      conduitGraphics.moveTo(posA.x, posA.y);
      conduitGraphics.lineTo(posB.x, posB.y);
      conduitGraphics.strokePath();

      if (combined > 5 && Math.random() < intensity * 0.1) {
        conduitParticles.push({
          x: posA.x, y: posA.y, targetX: posB.x, targetY: posB.y,
          progress: 0, speed: 0.01 + Math.random() * 0.01,
          color: Phaser.Display.Color.GetColor(color.r, color.g, color.b)
        });
      }
    }
  }

  for (let i = conduitParticles.length - 1; i >= 0; i--) {
    const p = conduitParticles[i];
    p.progress += p.speed;
    if (p.progress >= 1) { conduitParticles.splice(i, 1); continue; }
    conduitGraphics.fillStyle(p.color, 0.9);
    conduitGraphics.fillCircle(
      p.x + (p.targetX - p.x) * p.progress,
      p.y + (p.targetY - p.y) * p.progress, 3
    );
  }

  zoneIds.forEach((id, idx) => {
    const pos = positions[id];
    const zone = conduitZones[id];
    const color = Phaser.Display.Color.StringToColor(zone.color);
    const activity = conduitActivity[id]?.calls || 0;
    const pulse = 1 + 0.2 * Math.sin(time / 500);
    const radius = 12 + Math.min(activity * 2, 8) * pulse;
    conduitGraphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.3);
    conduitGraphics.fillCircle(pos.x, pos.y, radius + 3);
    conduitGraphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.9);
    conduitGraphics.fillCircle(pos.x, pos.y, radius);
  });
}

function updateConduitLabels() {
  const zoneIds = Object.keys(conduitZones);
  if (!window.conduitLabels) window.conduitLabels = {};

  zoneIds.forEach((id, idx) => {
    const pos = getZonePosition(id, idx, zoneIds.length);
    if (!window.conduitLabels[id]) {
      window.conduitLabels[id] = game.add.text(pos.x, pos.y + 20, conduitZones[id].label, {
        fontFamily: 'ArkPixel, monospace', fontSize: '9px',
        fill: '#' + conduitZones[id].color.replace('#', ''),
        stroke: '#000', strokeThickness: 2
      }).setOrigin(0.5).setDepth(901);
    } else {
      window.conduitLabels[id].setText(conduitZones[id].label).setPosition(pos.x, pos.y + 20);
    }
  });

  for (let id in window.conduitLabels) {
    if (!zoneIds.includes(id)) {
      window.conduitLabels[id].destroy();
      delete window.conduitLabels[id];
    }
  }
}

// ── Room Navigation (CM-7) ──────────────────────────────────────────
function fetchOfficeRoomsForNav() {
  fetch('/office/rooms?t=' + Date.now(), { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      if (data && Array.isArray(data.rooms)) {
        officeRooms = {};
        data.rooms.forEach(room => { officeRooms[room.id] = room; });
        if (roomGraphics) { drawRoomNavigationGraph(); updateRoomLabelsNav(); }
      }
    })
    .catch(() => {});
}

function getRoomCenter(roomId) {
  const mapX = 1140, mapY = 50, spacing = 45;
  const roomList = Object.keys(officeRooms);
  const idx = roomList.indexOf(roomId);
  if (idx === -1) return { x: mapX, y: mapY, radius: 14 };
  const cols = 2;
  return { x: mapX + (idx % cols) * spacing, y: mapY + Math.floor(idx / cols) * spacing, radius: 14 };
}

function drawRoomNavigationGraph() {
  if (!roomGraphics) { roomGraphics = game.add.graphics(); roomGraphics.setDepth(2000); }
  roomGraphics.clear();
  const roomIds = Object.keys(officeRooms);
  if (roomIds.length === 0) return;

  roomIds.forEach(fromId => {
    const fromPos = getRoomCenter(fromId);
    (officeRooms[fromId].connections || []).forEach(toId => {
      if (!officeRooms[toId] || fromId >= toId) return;
      const toPos = getRoomCenter(toId);
      roomGraphics.lineStyle(1.5, 0xffffff, 0.2);
      roomGraphics.beginPath();
      roomGraphics.moveTo(fromPos.x, fromPos.y);
      roomGraphics.lineTo(toPos.x, toPos.y);
      roomGraphics.strokePath();
    });
  });

  roomIds.forEach(roomId => {
    const room = officeRooms[roomId];
    const pos = getRoomCenter(roomId);
    const color = Phaser.Display.Color.StringToColor(room.color);
    const isCurrent = roomId === mainAgentArea;
    const isNav = navigationTarget && navigationTarget.roomId === roomId;

    if (isCurrent || isNav) {
      const glowA = isNav ? 0.5 + 0.2 * Math.sin(Date.now() / 200) : 0.3;
      roomGraphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), glowA);
      roomGraphics.fillCircle(pos.x, pos.y, pos.radius + 6);
    }
    roomGraphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.85);
    roomGraphics.fillCircle(pos.x, pos.y, pos.radius);
  });
}

function updateRoomLabelsNav() {
  const roomIds = Object.keys(officeRooms);
  roomIds.forEach(roomId => {
    const room = officeRooms[roomId];
    const pos = getRoomCenter(roomId);
    if (!roomLabels[roomId]) {
      roomLabels[roomId] = game.add.text(pos.x, pos.y + 16, room.name, {
        fontFamily: 'ArkPixel, monospace', fontSize: '8px',
        fill: '#ffffff', stroke: '#000000', strokeThickness: 1
      }).setOrigin(0.5).setDepth(2001);
    } else {
      roomLabels[roomId].setPosition(pos.x, pos.y + 16).setText(room.name);
    }
  });
  for (let id in roomLabels) {
    if (!officeRooms[id]) { roomLabels[id].destroy(); delete roomLabels[id]; }
  }
}

function setupRoomNavigation() {
  game.input.on('pointerdown', (pointer) => {
    const mapRegion = { x: 1080, y: 20, w: 180, h: 200 };
    if (pointer.x >= mapRegion.x && pointer.x <= mapRegion.x + mapRegion.w &&
        pointer.y >= mapRegion.y && pointer.y <= mapRegion.y + mapRegion.h) {
      const roomIds = Object.keys(officeRooms);
      for (let roomId of roomIds) {
        const pos = getRoomCenter(roomId);
        if (Math.sqrt((pointer.x - pos.x) ** 2 + (pointer.y - pos.y) ** 2) <= pos.radius + 5) {
          initiateNavigationToRoom(roomId);
          break;
        }
      }
    }
  });
}

function initiateNavigationToRoom(roomId) {
  if (!officeRooms[roomId]) return;
  if (AREA_POSITIONS[roomId] && AREA_POSITIONS[roomId].length > 0) {
    const targetPos = AREA_POSITIONS[roomId][0];
    navigationTarget = { roomId, x: targetPos.x, y: targetPos.y, arrivalTime: Date.now() + 3000 };
    if (typeof addActivity === 'function') addActivity(`Navigating to ${officeRooms[roomId].name}`, 'info');
    fetch('/set_state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: 'executing', detail: `Walking to ${officeRooms[roomId].name}` })
    }).then(() => fetchStatus());
  }
}

function updateNavigation(time) {
  if (!navigationTarget) return;
  if (Date.now() >= navigationTarget.arrivalTime) {
    fetch('/set_state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: 'idle', detail: `Arrived at ${officeRooms[navigationTarget.roomId]?.name || navigationTarget.roomId}` })
    }).then(() => fetchStatus());
    navigationTarget = null;
  }
}

// ── Drag-to-Pan (page-level scrolling) ──────────────────────────────
function setupDragToPan() {
  // Enable page-level drag-to-scroll when the map is bigger than the viewport
  const body = document.body;
  body.style.cursor = 'grab';

  body.addEventListener('mousedown', (e) => {
    // Skip if clicking on UI controls (buttons, inputs, panels)
    if (e.target.closest('button, input, select, textarea, #bottom-panels, .panel, #asset-drawer')) return;
    if (e.button !== 0) return;
    isPanning = true;
    panStartX = e.clientX;
    panStartY = e.clientY;
    body.style.cursor = 'grabbing';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!isPanning) return;
    window.scrollBy(panStartX - e.clientX, panStartY - e.clientY);
    panStartX = e.clientX;
    panStartY = e.clientY;
  });

  window.addEventListener('mouseup', () => {
    if (isPanning) {
      isPanning = false;
      body.style.cursor = 'grab';
    }
  });
}

// ── Live Chat Feed ──────────────────────────────────────────────────
function formatChatTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  } catch { return ''; }
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderChatFeed(messages) {
  const list = document.getElementById('chat-feed-list');
  if (!list) return;
  if (!messages || messages.length === 0) {
    list.innerHTML = '<div style="color:#6b7280;font-size:11px;text-align:center;padding:20px 0;">No recent messages</div>';
    return;
  }
  const wasAtBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 20;
  let html = '';
  const sorted = [...messages].reverse();
  for (const msg of sorted) {
    const dotClass = AGENT_COLORS[msg.sender] || 'unknown';
    const time = formatChatTime(msg.timestamp);
    const text = escapeHtml(msg.text.length > 200 ? msg.text.slice(0, 200) + '...' : msg.text);
    html += '<div class="chat-msg">' +
      '<span class="chat-dot ' + dotClass + '"></span>' +
      '<span class="chat-sender">' + escapeHtml(msg.sender) + '</span>' +
      '<span class="chat-text">' + text + '</span>' +
      '<span class="chat-time">' + time + '</span>' +
      '</div>';
  }
  list.innerHTML = html;
  if (wasAtBottom) list.scrollTop = list.scrollHeight;
}

async function fetchLiveChat() {
  try {
    const res = await fetch('/agent-messages?limit=25&t=' + Date.now(), { cache: 'no-store' });
    const data = await res.json();
    if (data.ok && data.messages) {
      _liveChatMessages = data.messages;
      renderChatFeed(data.messages);
    }
  } catch (e) {
    console.error('Chat feed error:', e);
  }
}

function getLastMessageForAgent(agentName) {
  if (!_liveChatMessages || _liveChatMessages.length === 0) return null;
  for (const msg of _liveChatMessages) {
    if (msg.sender === agentName) return msg.text;
  }
  return null;
}

// ── Start ───────────────────────────────────────────────────────────
try { initGame(); } catch(e) { console.error("Init failed:", e); }
