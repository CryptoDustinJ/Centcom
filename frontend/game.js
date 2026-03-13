// Star Office UI - 游戏主逻辑
// 依赖: layout.js（必须在这个之前加载）

// 检测浏览器是否支持 WebP
let supportsWebP = false;

// 方法 1: 使用 canvas 检测
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

// 方法 2: 使用 image 检测（备用）
function checkWebPSupportFallback() {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(true);
    img.onerror = () => resolve(false);
    img.src = 'data:image/webp;base64,UklGRkoAAABXRUJQVlA4WAoAAAAQAAAAAAAAAAAAQUxQSAwAAAABBxAR/Q9ERP8DAABWUDggGAAAADABAJ0BKgEAAQADADQlpAADcAD++/1QAA==';
  });
}

// 获取文件扩展名（根据 WebP 支持情况 + 布局配置的 forcePng）
function getExt(pngFile) {
  // star-working-spritesheet.png 太宽了，WebP 不支持，始终用 PNG
  if (pngFile === 'star-working-spritesheet.png') {
    return '.png';
  }
  // 如果布局配置里强制用 PNG，就用 .png
  if (LAYOUT.forcePng && LAYOUT.forcePng[pngFile.replace(/\.(png|webp)$/, '')]) {
    return '.png';
  }
  return supportsWebP ? '.webp' : '.png';
}

const config = {
  type: Phaser.AUTO,
  width: LAYOUT.game.width,
  height: LAYOUT.game.height,
  parent: 'game-container',
  pixelArt: true,
  physics: { default: 'arcade', arcade: { gravity: { y: 0 }, debug: false } },
  scene: { preload: preload, create: create, update: update }
};

let totalAssets = 0;
let loadedAssets = 0;
let loadingProgressBar, loadingProgressContainer, loadingOverlay, loadingText;

// Memo 相关函数
async function loadMemo() {
  const memoDate = document.getElementById('memo-date');
  const memoContent = document.getElementById('memo-content');

  try {
    const response = await fetch('/yesterday-memo?t=' + Date.now(), { cache: 'no-store' });
    const data = await response.json();

    if (data.memo) {
      memoDate.textContent = data.date || '';
      const escaped = data.memo.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      memoContent.innerHTML = escaped.replace(/\n/g, '<br>');
    } else {
      memoContent.innerHTML = '<div id="memo-placeholder">No yesterday notes</div>';
    }
  } catch (e) {
    console.error('Failed to load memo:', e);
    memoContent.innerHTML = '<div id="memo-placeholder">Load failed</div>';
  }
}

// 更新加载进度
function updateLoadingProgress() {
  loadedAssets++;
  const percent = Math.min(100, Math.round((loadedAssets / totalAssets) * 100));
  if (loadingProgressBar) {
    loadingProgressBar.style.width = percent + '%';
  }
  if (loadingText) {
    loadingText.textContent = `Loading Star's Pixel Office... ${percent}%`;
  }
}

// 隐藏加载界面
function hideLoadingOverlay() {
  setTimeout(() => {
    if (loadingOverlay) {
      loadingOverlay.style.transition = 'opacity 0.5s ease';
      loadingOverlay.style.opacity = '0';
      setTimeout(() => {
        loadingOverlay.style.display = 'none';
      }, 500);
    }
  }, 300);
}

const STATES = {
  idle: { name: 'Idle', area: 'breakroom' },
  writing: { name: 'Writing', area: 'writing' },
  researching: { name: 'Researching', area: 'researching' },
  executing: { name: 'Executing', area: 'writing' },
  syncing: { name: 'Syncing', area: 'writing' },
  error: { name: 'Error', area: 'error' }
};

// === Dynamic Room System ===
let OFFICE_ROOMS = {};  // roomId -> room definition

async function loadOfficeRooms() {
  try {
    const resp = await fetch('/office/rooms');
    if (resp.ok) {
      const data = await resp.json();
      const rooms = data.rooms || [];
      for (const room of rooms) {
        OFFICE_ROOMS[room.id] = room;
        // Generate positions for this room if not already defined
        if (!AREA_POSITIONS[room.id]) {
          // Distribute rooms in a grid pattern to the right side
          const roomIds = Object.keys(OFFICE_ROOMS);
          const idx = roomIds.indexOf(room.id);
          const cols = 2;
          const startX = 700;
          const startY = 100;
          const spacingX = 200;
          const spacingY = 120;
          const col = idx % cols;
          const row = Math.floor(idx / cols);
          const baseX = startX + col * spacingX;
          const baseY = startY + row * spacingY;
          // Primary position (for single agent placement)
          LAYOUT.areas[room.id] = { x: baseX, y: baseY };
          // Multiple slots for multiple agents in same room
          AREA_POSITIONS[room.id] = [
            { x: baseX, y: baseY },
            { x: baseX + 25, y: baseY + 25 },
            { x: baseX - 25, y: baseY + 25 },
            { x: baseX + 25, y: baseY - 25 },
            { x: baseX - 25, y: baseY - 25 },
            { x: baseX + 50, y: baseY },
            { x: baseX - 50, y: baseY },
          ];
        }
      }
      console.log(`[Office] Loaded ${rooms.length} rooms`);
    }
  } catch (e) {
    console.warn('[Office] Failed to load rooms:', e);
  }
}

function drawRoomsOverlay(scene) {
  const graphics = scene.add.graphics();
  for (const roomId in OFFICE_ROOMS) {
    const room = OFFICE_ROOMS[roomId];
    const color = Phaser.Display.Color.StringToColor(room.color || '#888888');
    const positions = AREA_POSITIONS[roomId];
    if (positions && positions.length > 0) {
      const xs = positions.map(p => p.x);
      const ys = positions.map(p => p.y);
      const minX = Math.min(...xs) - 60;
      const minY = Math.min(...ys) - 40;
      const maxX = Math.max(...xs) + 60;
      const maxY = Math.max(...ys) + 40;
      const w = maxX - minX;
      const h = maxY - minY;
      // Room background
      graphics.fillStyle(Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.12);
      graphics.fillRoundedRect(minX, minY, w, h, 10);
      graphics.lineStyle(2, Phaser.Display.Color.GetColor(color.r, color.g, color.b), 0.4);
      graphics.strokeRoundedRect(minX, minY, w, h, 10);
      // Room label
      scene.add.text(minX + 10, minY + 10, room.name, {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: '10px',
        fill: 'white',
        stroke: '#000000',
        strokeThickness: 2
      }).setScrollFactor(0).setDepth(1000);
    }
  }
}

const BUBBLE_TEXTS = {
  idle: [
    'Idle: ears perked up',
    'I\'m here, ready to work',
    'Let me tidy up the desk first',
    'Ahh~ giving the brain a break',
    'Elegant efficiency every day',
    'Waiting for the perfect moment to strike',
    'Coffee\'s still hot, inspiration too',
    'I\'m buffing you in the background',
    'Status: Resting / Recharging',
    'The cat says: slow down, it\'s okay'
  ],
  writing: [
    'Entering focus mode: do not disturb',
    'Let\'s nail down the critical path first',
    'I make complex things simple',
    'Locking bugs in a cage',
    'Halfway through writing, saving now',
    'Make everything rollback-ready',
    'Today\'s progress is tomorrow\'s confidence',
    'Converge first, then diverge',
    'Making the system more explainable',
    'Stay steady, we can win'
  ],
  researching: [
    'Digging through evidence chains',
    'Let me simmer info into conclusions',
    'Found it: the key point here',
    'Controlling variables first',
    'Researching: why does this happen?',
    'Turning intuition into verification',
    'Locate first, optimize later',
    'Don\'t rush, let\'s map causality'
  ],
  executing: [
    'Executing: don\'t blink',
    'Slice tasks into pieces, tackle one by one',
    'Starting the pipeline run',
    'One-click deploy: here we go',
    'Let results speak for themselves',
    'MVP first, beautiful version later'
  ],
  syncing: [
    'Syncing: locking today into the cloud',
    'Backup isn\'t ritual, it\'s security',
    'Writing... don\'t unplug',
    'Handing changes to timestamps',
    'Cloud alignment: click',
    'Don\'t mess around until sync completes',
    'Saving future me from disaster',
    'One more backup, one less regret'
  ],
  error: [
    'Alarm ringing: stay calm first',
    'I smell a bug',
    'Reproduce first, then discuss fixes',
    'Give me the logs, I\'ll translate to human',
    'Errors aren\'t enemies, they\'re clues',
    'Mapping the impact zone',
    'Stop the bleeding first, then surgery',
    'I\'m on it: root cause LOC soon',
    'Don\'t worry, I\'ve seen this before',
    'Alert active: let the problem reveal itself'
  ],
  cat: [
    'Meow~',
    'Purrrr...',
    'Wagging tail',
    'So happy basking in the sun',
    'Someone\'s visiting me!',
    'I\'m the office mascot',
    'Stretching',
    'Is today\'s treat can ready?',
    'Purrrr',
    'Best view from this spot'
  ]
};

let game, star, sofa, serverroom, coffeeMachine, areas = {}, currentState = 'idle', pendingDesiredState = null, statusText, lastFetch = 0, lastBlink = 0, lastBubble = 0, targetX = 660, targetY = 170, bubble = null, typewriterText = '', typewriterTarget = '', typewriterIndex = 0, lastTypewriter = 0, syncAnimSprite = null, catBubble = null;
let isMoving = false;
let waypoints = [];
let lastWanderAt = 0;
let coordsOverlay, coordsDisplay, coordsToggle;
let showCoords = false;
const FETCH_INTERVAL = 2000;
const BLINK_INTERVAL = 2500;
const BUBBLE_INTERVAL = 8000;
const CAT_BUBBLE_INTERVAL = 18000;
let lastCatBubble = 0;
const TYPEWRITER_DELAY = 50;
let agents = {}; // agentId -> sprite/container
let lastAgentsFetch = 0;
const AGENTS_FETCH_INTERVAL = 2500;

// agent 颜色配置
const AGENT_COLORS = {
  star: 0xffd700,
  npc1: 0x00aaff,
  agent_nika: 0xff69b4,
  default: 0x94a3b8
};

// agent 名字颜色
const NAME_TAG_COLORS = {
  approved: 0x22c55e,
  pending: 0xf59e0b,
  rejected: 0xef4444,
  offline: 0x64748b,
  default: 0x1f2937
};

// breakroom / writing / error 区域的 agent 分布位置（多 agent 时错开）
const AREA_POSITIONS = {
  breakroom: [
    { x: 620, y: 180 },
    { x: 560, y: 220 },
    { x: 680, y: 210 },
    { x: 540, y: 170 },
    { x: 700, y: 240 },
    { x: 600, y: 250 },
    { x: 650, y: 160 },
    { x: 580, y: 200 }
  ],
  writing: [
    { x: 760, y: 320 },
    { x: 830, y: 280 },
    { x: 690, y: 350 },
    { x: 770, y: 260 },
    { x: 850, y: 340 },
    { x: 720, y: 300 },
    { x: 800, y: 370 },
    { x: 750, y: 240 }
  ],
  error: [
    { x: 180, y: 260 },
    { x: 120, y: 220 },
    { x: 240, y: 230 },
    { x: 160, y: 200 },
    { x: 220, y: 270 },
    { x: 140, y: 250 },
    { x: 200, y: 210 },
    { x: 260, y: 260 }
  ]
};


// 状态控制栏函数（用于测试）
function setState(state, detail) {
  fetch('/set_state', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, detail })
  }).then(() => fetchStatus());
}

// 初始化：先检测 WebP 支持，再启动游戏
async function initGame() {
  try {
    supportsWebP = await checkWebPSupport();
  } catch (e) {
    try {
      supportsWebP = await checkWebPSupportFallback();
    } catch (e2) {
      supportsWebP = false;
    }
  }

  console.log('WebP 支持:', supportsWebP);

  // Load office rooms before starting game
  await loadOfficeRooms();

  new Phaser.Game(config);
}

function preload() {
  loadingOverlay = document.getElementById('loading-overlay');
  loadingProgressBar = document.getElementById('loading-progress-bar');
  loadingText = document.getElementById('loading-text');
  loadingProgressContainer = document.getElementById('loading-progress-container');

  // 从 LAYOUT 读取总资源数量（避免 magic number）
  totalAssets = LAYOUT.totalAssets || 15;
  loadedAssets = 0;

  this.load.on('filecomplete', () => {
    updateLoadingProgress();
  });

  this.load.on('complete', () => {
    hideLoadingOverlay();
  });

  this.load.image('office_bg', '/static/office_bg_small' + (supportsWebP ? '.webp' : '.png') + '?v={{VERSION_TIMESTAMP}}');
  this.load.spritesheet('star_idle', '/static/star-idle-spritesheet' + getExt('star-idle-spritesheet.png'), { frameWidth: 128, frameHeight: 128 });
  this.load.spritesheet('star_researching', '/static/star-researching-spritesheet' + getExt('star-researching-spritesheet.png'), { frameWidth: 128, frameHeight: 105 });

  this.load.image('sofa_idle', '/static/sofa-idle' + getExt('sofa-idle.png'));
  this.load.spritesheet('sofa_busy', '/static/sofa-busy-spritesheet' + getExt('sofa-busy-spritesheet.png'), { frameWidth: 256, frameHeight: 256 });

  this.load.spritesheet('plants', '/static/plants-spritesheet' + getExt('plants-spritesheet.png'), { frameWidth: 160, frameHeight: 160 });
  this.load.spritesheet('posters', '/static/posters-spritesheet' + getExt('posters-spritesheet.png'), { frameWidth: 160, frameHeight: 160 });
  this.load.spritesheet('coffee_machine', '/static/coffee-machine-spritesheet' + getExt('coffee-machine-spritesheet.png'), { frameWidth: 230, frameHeight: 230 });
  this.load.spritesheet('serverroom', '/static/serverroom-spritesheet' + getExt('serverroom-spritesheet.png'), { frameWidth: 180, frameHeight: 251 });

  this.load.spritesheet('error_bug', '/static/error-bug-spritesheet-grid' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 180, frameHeight: 180 });
  this.load.spritesheet('cats', '/static/cats-spritesheet' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 160, frameHeight: 160 });
  this.load.image('desk', '/static/desk' + getExt('desk.png'));
  this.load.spritesheet('star_working', '/static/star-working-spritesheet-grid' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 230, frameHeight: 144 });
  this.load.spritesheet('sync_anim', '/static/sync-animation-spritesheet-grid' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 256, frameHeight: 256 });
  this.load.image('memo_bg', '/static/memo-bg' + (supportsWebP ? '.webp' : '.png'));

  // 新办公桌：强制 PNG（透明）
  this.load.image('desk_v2', '/static/desk-v2.png');
  this.load.spritesheet('flowers', '/static/flowers-spritesheet' + (supportsWebP ? '.webp' : '.png'), { frameWidth: 65, frameHeight: 65 });
}

function create() {
  game = this;
  this.add.image(640, 360, 'office_bg');

  // === 沙发（来自 LAYOUT）===
  sofa = this.add.sprite(
    LAYOUT.furniture.sofa.x,
    LAYOUT.furniture.sofa.y,
    'sofa_busy'
  ).setOrigin(LAYOUT.furniture.sofa.origin.x, LAYOUT.furniture.sofa.origin.y);
  sofa.setDepth(LAYOUT.furniture.sofa.depth);

  this.anims.create({
    key: 'sofa_busy',
    frames: this.anims.generateFrameNumbers('sofa_busy', { start: 0, end: 47 }),
    frameRate: 12,
    repeat: -1
  });

  areas = LAYOUT.areas;

  this.anims.create({
    key: 'star_idle',
    frames: this.anims.generateFrameNumbers('star_idle', { start: 0, end: 29 }),
    frameRate: 12,
    repeat: -1
  });
  this.anims.create({
    key: 'star_researching',
    frames: this.anims.generateFrameNumbers('star_researching', { start: 0, end: 95 }),
    frameRate: 12,
    repeat: -1
  });

  star = game.physics.add.sprite(areas.breakroom.x, areas.breakroom.y, 'star_idle');
  star.setOrigin(0.5);
  star.setScale(1.4);
  star.setAlpha(0.95);
  star.setDepth(20);
  star.setVisible(false);
  star.anims.stop();

  // Draw dynamic room overlays
  drawRoomsOverlay(this);

  if (game.textures.exists('sofa_busy')) {
    sofa.setTexture('sofa_busy');
    sofa.anims.play('sofa_busy', true);
  }

  // === 牌匾（来自 LAYOUT）===
  const plaqueX = LAYOUT.plaque.x;
  const plaqueY = LAYOUT.plaque.y;
  const plaqueBg = game.add.rectangle(plaqueX, plaqueY, LAYOUT.plaque.width, LAYOUT.plaque.height, 0x5d4037);
  plaqueBg.setStrokeStyle(3, 0x3e2723);
  const plaqueText = game.add.text(plaqueX, plaqueY, 'Star\'s Office', {
    fontFamily: 'ArkPixel, monospace',
    fontSize: '18px',
    fill: '#ffd700',
    fontWeight: 'bold',
    stroke: '#000',
    strokeThickness: 2
  }).setOrigin(0.5);
  game.add.text(plaqueX - 190, plaqueY, '⭐', { fontFamily: 'ArkPixel, monospace', fontSize: '20px' }).setOrigin(0.5);
  game.add.text(plaqueX + 190, plaqueY, '⭐', { fontFamily: 'ArkPixel, monospace', fontSize: '20px' }).setOrigin(0.5);

  // === 植物们（来自 LAYOUT）===
  const plantFrameCount = 16;
  for (let i = 0; i < LAYOUT.furniture.plants.length; i++) {
    const p = LAYOUT.furniture.plants[i];
    const randomPlantFrame = Math.floor(Math.random() * plantFrameCount);
    const plant = game.add.sprite(p.x, p.y, 'plants', randomPlantFrame).setOrigin(0.5);
    plant.setDepth(p.depth);
    plant.setInteractive({ useHandCursor: true });
    window[`plantSprite${i === 0 ? '' : i + 1}`] = plant;
    plant.on('pointerdown', (() => {
      const next = Math.floor(Math.random() * plantFrameCount);
      plant.setFrame(next);
    }));
  }

  // === 海报（来自 LAYOUT）===
  const postersFrameCount = 32;
  const randomPosterFrame = Math.floor(Math.random() * postersFrameCount);
  const poster = game.add.sprite(LAYOUT.furniture.poster.x, LAYOUT.furniture.poster.y, 'posters', randomPosterFrame).setOrigin(0.5);
  poster.setDepth(LAYOUT.furniture.poster.depth);
  poster.setInteractive({ useHandCursor: true });
  window.posterSprite = poster;
  window.posterFrameCount = postersFrameCount;
  poster.on('pointerdown', () => {
    const next = Math.floor(Math.random() * window.posterFrameCount);
    window.posterSprite.setFrame(next);
  });

  // === 小猫（来自 LAYOUT）===
  const catsFrameCount = 16;
  const randomCatFrame = Math.floor(Math.random() * catsFrameCount);
  const cat = game.add.sprite(LAYOUT.furniture.cat.x, LAYOUT.furniture.cat.y, 'cats', randomCatFrame).setOrigin(LAYOUT.furniture.cat.origin.x, LAYOUT.furniture.cat.origin.y);
  cat.setDepth(LAYOUT.furniture.cat.depth);
  cat.setInteractive({ useHandCursor: true });
  window.catSprite = cat;
  window.catsFrameCount = catsFrameCount;
  cat.on('pointerdown', () => {
    const next = Math.floor(Math.random() * window.catsFrameCount);
    window.catSprite.setFrame(next);
  });

  // === 咖啡机（来自 LAYOUT）===
  this.anims.create({
    key: 'coffee_machine',
    frames: this.anims.generateFrameNumbers('coffee_machine', { start: 0, end: 95 }),
    frameRate: 12.5,
    repeat: -1
  });
  coffeeMachine = this.add.sprite(
    LAYOUT.furniture.coffeeMachine.x,
    LAYOUT.furniture.coffeeMachine.y,
    'coffee_machine'
  ).setOrigin(LAYOUT.furniture.coffeeMachine.origin.x, LAYOUT.furniture.coffeeMachine.origin.y);
  coffeeMachine.setDepth(LAYOUT.furniture.coffeeMachine.depth);
  coffeeMachine.anims.play('coffee_machine', true);

  // Make coffee machine interactive
  const cmHitArea = new Phaser.Geom.Rectangle(-30, -40, 60, 70);
  coffeeMachine.setInteractive(cmHitArea, Phaser.Geom.Rectangle.Contains);
  coffeeMachine.on('pointerdown', () => {
    const now = Date.now();
    if (window.lastCoffeeClick && now - window.lastCoffeeClick < 1000) return;
    window.lastCoffeeClick = now;
    // Toggle coffee break state (just visual feedback)
    if (typeof addActivity === 'function') {
        addActivity('☕ Coffee break toggled!', 'info');
    }
    // Show a temporary bubble
    if (typeof showBubbleAt === 'function') {
        showBubbleAt(coffeeMachine.x, coffeeMachine.y - 60, 'Coffee breaks ' + (Date.now() % 2 ? 'enabled' : 'disabled'));
    } else {
        // Simple fallback: show a Phaser text
        const txt = game.add.text(coffeeMachine.x, coffeeMachine.y - 60, 'Coffee toggled!', { fontFamily: 'ArkPixel', fontSize: '12px', fill: '#fff' }).setOrigin(0.5);
        game.time.delayedCall(2000, () => txt.destroy());
    }
  });

  // === 服务器区（来自 LAYOUT）===
  this.anims.create({
    key: 'serverroom_on',
    frames: this.anims.generateFrameNumbers('serverroom', { start: 0, end: 39 }),
    frameRate: 6,
    repeat: -1
  });
  serverroom = this.add.sprite(
    LAYOUT.furniture.serverroom.x,
    LAYOUT.furniture.serverroom.y,
    'serverroom',
    0
  ).setOrigin(LAYOUT.furniture.serverroom.origin.x, LAYOUT.furniture.serverroom.origin.y);
  serverroom.setDepth(LAYOUT.furniture.serverroom.depth);
  serverroom.anims.stop();
  serverroom.setFrame(0);

  // === 新办公桌（来自 LAYOUT，强制透明 PNG）===
  const desk = this.add.image(
    LAYOUT.furniture.desk.x,
    LAYOUT.furniture.desk.y,
    'desk_v2'
  ).setOrigin(LAYOUT.furniture.desk.origin.x, LAYOUT.furniture.desk.origin.y);
  desk.setDepth(LAYOUT.furniture.desk.depth);

  // === 花盆（来自 LAYOUT）===
  const flowerFrameCount = 16;
  const randomFlowerFrame = Math.floor(Math.random() * flowerFrameCount);
  const flower = this.add.sprite(
    LAYOUT.furniture.flower.x,
    LAYOUT.furniture.flower.y,
    'flowers',
    randomFlowerFrame
  ).setOrigin(LAYOUT.furniture.flower.origin.x, LAYOUT.furniture.flower.origin.y);
  flower.setScale(LAYOUT.furniture.flower.scale || 1);
  flower.setDepth(LAYOUT.furniture.flower.depth);
  flower.setInteractive({ useHandCursor: true });
  window.flowerSprite = flower;
  window.flowerFrameCount = flowerFrameCount;
  flower.on('pointerdown', () => {
    const next = Math.floor(Math.random() * window.flowerFrameCount);
    window.flowerSprite.setFrame(next);
  });

  // === Star 在桌前工作（来自 LAYOUT）===
  this.anims.create({
    key: 'star_working',
    frames: this.anims.generateFrameNumbers('star_working', { start: 0, end: 191 }),
    frameRate: 12,
    repeat: -1
  });
  this.anims.create({
    key: 'error_bug',
    frames: this.anims.generateFrameNumbers('error_bug', { start: 0, end: 95 }),
    frameRate: 12,
    repeat: -1
  });

  // === 错误 bug（来自 LAYOUT）===
  const errorBug = this.add.sprite(
    LAYOUT.furniture.errorBug.x,
    LAYOUT.furniture.errorBug.y,
    'error_bug',
    0
  ).setOrigin(LAYOUT.furniture.errorBug.origin.x, LAYOUT.furniture.errorBug.origin.y);
  errorBug.setDepth(LAYOUT.furniture.errorBug.depth);
  errorBug.setVisible(false);
  errorBug.setScale(LAYOUT.furniture.errorBug.scale);
  errorBug.anims.play('error_bug', true);
  window.errorBug = errorBug;
  window.errorBugDir = 1;

  const starWorking = this.add.sprite(
    LAYOUT.furniture.starWorking.x,
    LAYOUT.furniture.starWorking.y,
    'star_working',
    0
  ).setOrigin(LAYOUT.furniture.starWorking.origin.x, LAYOUT.furniture.starWorking.origin.y);
  starWorking.setVisible(false);
  starWorking.setScale(LAYOUT.furniture.starWorking.scale);
  starWorking.setDepth(LAYOUT.furniture.starWorking.depth);
  window.starWorking = starWorking;

  // === 同步动画（来自 LAYOUT）===
  this.anims.create({
    key: 'sync_anim',
    frames: this.anims.generateFrameNumbers('sync_anim', { start: 1, end: 52 }),
    frameRate: 12,
    repeat: -1
  });
  syncAnimSprite = this.add.sprite(
    LAYOUT.furniture.syncAnim.x,
    LAYOUT.furniture.syncAnim.y,
    'sync_anim',
    0
  ).setOrigin(LAYOUT.furniture.syncAnim.origin.x, LAYOUT.furniture.syncAnim.origin.y);
  syncAnimSprite.setDepth(LAYOUT.furniture.syncAnim.depth);
  syncAnimSprite.anims.stop();
  syncAnimSprite.setFrame(0);

  window.starSprite = star;

  statusText = document.getElementById('status-text');
  coordsOverlay = document.getElementById('coords-overlay');
  coordsDisplay = document.getElementById('coords-display');
  coordsToggle = document.getElementById('coords-toggle');

  coordsToggle.addEventListener('click', () => {
    showCoords = !showCoords;
    coordsOverlay.style.display = showCoords ? 'block' : 'none';
    coordsToggle.textContent = showCoords ? 'Hide Coords' : 'Show Coords';
    coordsToggle.style.background = showCoords ? '#e94560' : '#333';
  });

  game.input.on('pointermove', (pointer) => {
    if (!showCoords) return;
    const x = Math.max(0, Math.min(config.width - 1, Math.round(pointer.x)));
    const y = Math.max(0, Math.min(config.height - 1, Math.round(pointer.y)));
    coordsDisplay.textContent = `${x}, ${y}`;
    coordsOverlay.style.left = (pointer.x + 18) + 'px';
    coordsOverlay.style.top = (pointer.y + 18) + 'px';
  });

  loadMemo();
  fetchStatus();
  fetchAgents();

  // === Initialize Command Center & Live Features ===
  initVitalsTiles(this);
  initIncidentAlarm(this);
  initPodium(this);
  initCommandCenter();

  // 可选调试：仅在显式开启 debug 模式时渲染测试用尼卡 agent
  let debugAgents = false;
  try {
    if (typeof window !== 'undefined') {
      if (window.STAR_OFFICE_DEBUG_AGENTS === true) {
        debugAgents = true;
      } else if (window.location && window.location.search && typeof URLSearchParams !== 'undefined') {
        const sp = new URLSearchParams(window.location.search);
        if (sp.get('debugAgents') === '1') {
          debugAgents = true;
        }
      }
    }
  } catch (e) {
    debugAgents = false;
  }

  if (debugAgents) {
    const testNika = {
      agentId: 'agent_nika',
      name: 'Nika',
      isMain: false,
      state: 'writing',
      detail: 'Drawing pixel art...',
      area: 'writing',
      authStatus: 'approved',
      updated_at: new Date().toISOString()
    };
    renderAgent(testNika);

    window.testNikaState = 'writing';
    window.testNikaTimer = setInterval(() => {
      const states = ['idle', 'writing', 'researching', 'executing'];
      const areas = { idle: 'breakroom', writing: 'writing', researching: 'writing', executing: 'writing' };
      window.testNikaState = states[Math.floor(Math.random() * states.length)];
      const testAgent = {
        agentId: 'agent_nika',
        name: 'Nika',
        isMain: false,
        state: window.testNikaState,
        detail: 'Drawing pixel art...',
        area: areas[window.testNikaState],
        authStatus: 'approved',
        updated_at: new Date().toISOString()
      };
      renderAgent(testAgent);
    }, 5000);
  }
}

// === Command Center (CM triggers) ===
let commandCenterOpen = false;
let commandCenterEl = null;

function initCommandCenter() {
  // Create command center button (top-right of canvas)
  const btn = document.createElement('button');
  btn.id = 'cmd-center-btn';
  btn.textContent = '⚡ Command Center';
  btn.style.cssText = 'position:fixed;top:10px;right:10px;z-index:9999;background:#1a1a2e;color:#00d4ff;border:2px solid #00d4ff;border-radius:8px;padding:8px 16px;font-family:ArkPixel,monospace;font-size:13px;cursor:pointer;';
  btn.addEventListener('click', toggleCommandCenter);
  document.body.appendChild(btn);

  // Create command center panel
  commandCenterEl = document.createElement('div');
  commandCenterEl.id = 'cmd-center-panel';
  commandCenterEl.style.cssText = 'display:none;position:fixed;top:50px;right:10px;z-index:9998;background:#1a1a2e;border:2px solid #00d4ff;border-radius:12px;padding:16px;width:320px;max-height:500px;overflow-y:auto;font-family:ArkPixel,monospace;color:#eee;';
  commandCenterEl.innerHTML = '<h3 style="margin:0 0 12px;color:#00d4ff;">⚡ Command Center</h3><div id="cmd-list">Loading...</div><div id="cmd-output" style="margin-top:12px;background:#0a0a1a;border-radius:6px;padding:8px;font-size:11px;max-height:150px;overflow-y:auto;display:none;"></div>';
  document.body.appendChild(commandCenterEl);

  // Load available commands
  fetch('/dispatch/commands').then(r => r.json()).then(data => {
    if (!data.ok) return;
    const list = document.getElementById('cmd-list');
    const categories = {};
    for (const cmd of data.commands) {
      if (!categories[cmd.category]) categories[cmd.category] = [];
      categories[cmd.category].push(cmd);
    }
    let html = '';
    for (const [cat, cmds] of Object.entries(categories)) {
      html += `<div style="margin-bottom:8px;"><div style="color:#666;font-size:10px;text-transform:uppercase;margin-bottom:4px;">${cat}</div>`;
      for (const cmd of cmds) {
        html += `<button class="cmd-btn" data-cmd="${cmd.id}" data-confirm="${cmd.confirm||false}" style="display:inline-block;margin:2px;padding:4px 10px;background:#16213e;border:1px solid #334;border-radius:6px;color:#eee;font-size:12px;cursor:pointer;font-family:ArkPixel,monospace;">${cmd.icon} ${cmd.label}</button>`;
      }
      html += '</div>';
    }
    list.innerHTML = html;
    list.querySelectorAll('.cmd-btn').forEach(btn => {
      btn.addEventListener('click', () => dispatchCommand(btn.dataset.cmd, btn.dataset.confirm === 'true'));
    });
  }).catch(() => {});
}

function toggleCommandCenter() {
  commandCenterOpen = !commandCenterOpen;
  commandCenterEl.style.display = commandCenterOpen ? 'block' : 'none';
}

function dispatchCommand(command, needsConfirm) {
  if (needsConfirm && !confirm(`Execute "${command}"?`)) return;
  const output = document.getElementById('cmd-output');
  output.style.display = 'block';
  output.textContent = `⏳ Running ${command}...`;
  fetch('/dispatch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command})
  }).then(r => r.json()).then(data => {
    output.textContent = data.ok ? `✅ ${data.output || data.msg || 'Done'}` : `❌ ${data.msg || 'Failed'}`;
    if (data.huddle_id) output.textContent += `\nHuddle: ${data.huddle_id}\nPlan: ${data.msg}`;
  }).catch(e => {
    output.textContent = `❌ Error: ${e.message}`;
  });
}

// === Vitals Floor Tiles (CM-21) ===
let vitalsContainer = null;
let lastVitalsFetch = 0;
const VITALS_FETCH_INTERVAL = 5000;

function initVitalsTiles(scene) {
  vitalsContainer = scene.add.container(80, 650);
  vitalsContainer.setDepth(800);

  const tiles = [
    { key: 'cpu', label: 'CPU', x: 0 },
    { key: 'ram', label: 'RAM', x: 90 },
    { key: 'disk', label: 'DISK', x: 180 },
  ];

  for (const tile of tiles) {
    const bg = scene.add.rectangle(tile.x, 0, 80, 44, 0x16213e, 0.85);
    bg.setStrokeStyle(1, 0x334455);
    const label = scene.add.text(tile.x, -14, tile.label, {
      fontFamily: 'ArkPixel, monospace', fontSize: '9px', fill: '#888'
    }).setOrigin(0.5);
    const value = scene.add.text(tile.x, 6, '--', {
      fontFamily: 'ArkPixel, monospace', fontSize: '14px', fill: '#2ecc71'
    }).setOrigin(0.5);
    value.name = 'vitals_' + tile.key;
    vitalsContainer.add([bg, label, value]);
  }
}

function fetchVitals() {
  fetch('/office/vitals').then(r => r.json()).then(data => {
    if (!data.ok || !vitalsContainer) return;
    const v = data.vitals;
    vitalsContainer.iterate(child => {
      if (child.name === 'vitals_cpu') {
        child.setText(Math.round(v.cpu_percent) + '%');
        child.setFill(v.cpu_percent > 80 ? '#e74c3c' : v.cpu_percent > 50 ? '#f39c12' : '#2ecc71');
      }
      if (child.name === 'vitals_ram') {
        child.setText(Math.round(v.ram_percent) + '%');
        child.setFill(v.ram_percent > 85 ? '#e74c3c' : v.ram_percent > 60 ? '#f39c12' : '#2ecc71');
      }
      if (child.name === 'vitals_disk') {
        child.setText(Math.round(v.disk_free_gb) + 'G');
        child.setFill(v.disk_free_gb < 10 ? '#e74c3c' : v.disk_free_gb < 50 ? '#f39c12' : '#2ecc71');
      }
    });
  }).catch(() => {});
}

// === Incident Alarm (CM-18) ===
let incidentBadge = null;
let lastIncidentFetch = 0;
const INCIDENT_FETCH_INTERVAL = 10000;

function initIncidentAlarm(scene) {
  incidentBadge = scene.add.container(1230, 30);
  incidentBadge.setDepth(2500);
  const bg = scene.add.circle(0, 0, 18, 0xe74c3c, 0);
  bg.name = 'incident_bg';
  const icon = scene.add.text(0, 0, '🚨', { fontSize: '20px' }).setOrigin(0.5);
  icon.name = 'incident_icon';
  icon.setVisible(false);
  const count = scene.add.text(12, -12, '', {
    fontFamily: 'ArkPixel, monospace', fontSize: '10px', fill: '#fff',
    backgroundColor: '#e74c3c', padding: { x: 3, y: 1 }
  }).setOrigin(0.5);
  count.name = 'incident_count';
  count.setVisible(false);
  incidentBadge.add([bg, icon, count]);
}

function fetchIncidents() {
  fetch('/office/incidents').then(r => r.json()).then(data => {
    if (!data.ok || !incidentBadge) return;
    const inc = data.incidents;
    const hasIncident = inc.level > 0;
    incidentBadge.iterate(child => {
      if (child.name === 'incident_icon') child.setVisible(hasIncident);
      if (child.name === 'incident_count') {
        child.setVisible(hasIncident && inc.recent_failures > 0);
        if (inc.recent_failures > 0) child.setText(String(inc.recent_failures));
      }
      if (child.name === 'incident_bg') {
        child.fillAlpha = hasIncident ? 0.3 : 0;
        if (hasIncident && inc.level >= 2) {
          // Pulsing for critical
          child.fillAlpha = 0.3 + Math.sin(Date.now() / 300) * 0.2;
        }
      }
    });
  }).catch(() => {});
}

// === Water Cooler OOC Bubbles (CM-14) ===
let waterCoolerBubble = null;
let lastWaterCoolerTime = 0;
const WATER_COOLER_INTERVAL = 30000;
const WATER_COOLER_MESSAGES = [
  "Did you hear? Nova wrote another sci-fi story...",
  "Ralph says disk is looking good today!",
  "I wonder if Rook ever takes a break...",
  "☕ Someone left the coffee machine running again",
  "CodeMaster just earned a new badge!",
  "The server room sounds extra busy today...",
  "Anyone else notice the new wallpaper?",
  "Ralph: 'All systems nominal' as always 😎",
  "Nova's been researching prompt techniques again",
  "Board meeting was productive today!",
  "The cats seem extra happy this morning 🐱",
  "Error bug spotted in sector 7! Oh wait, false alarm.",
];

function showWaterCoolerBubble(scene) {
  if (waterCoolerBubble) { waterCoolerBubble.destroy(); waterCoolerBubble = null; }
  const msg = WATER_COOLER_MESSAGES[Math.floor(Math.random() * WATER_COOLER_MESSAGES.length)];
  // Position near the coffee machine (water cooler stand-in)
  const x = 659, y = 340;
  const maxW = Math.min(msg.length * 7 + 20, 220);
  const bg = scene.add.rectangle(x, y, maxW, 28, 0xe8f4f8, 0.95);
  bg.setStrokeStyle(1, 0x3498db);
  const txt = scene.add.text(x, y, msg, {
    fontFamily: 'ArkPixel, monospace', fontSize: '10px', fill: '#2c3e50',
    align: 'center', wordWrap: { width: maxW - 16 }
  }).setOrigin(0.5);
  waterCoolerBubble = scene.add.container(0, 0, [bg, txt]);
  waterCoolerBubble.setDepth(1500);
  scene.time.delayedCall(8000, () => {
    if (waterCoolerBubble) { waterCoolerBubble.destroy(); waterCoolerBubble = null; }
  });
}

// === Podium Briefing (CM-16) ===
let podiumLampGlow = null;

function initPodium(scene) {
  // Podium icon near the plaque area
  const podiumX = 450, podiumY = 660;
  const podiumIcon = scene.add.text(podiumX, podiumY, '🎙️', { fontSize: '24px' }).setOrigin(0.5);
  podiumIcon.setDepth(1800);
  podiumIcon.setInteractive({ useHandCursor: true });

  podiumLampGlow = scene.add.circle(podiumX, podiumY - 15, 8, 0x666666, 0);
  podiumLampGlow.setDepth(1799);

  // Check briefing freshness
  fetch('/office/briefing-status').then(r => r.json()).then(data => {
    if (data.fresh) {
      podiumLampGlow.fillColor = 0x2ecc71;
      podiumLampGlow.fillAlpha = 0.7;
    }
  }).catch(() => {});

  podiumIcon.on('pointerdown', () => {
    showBriefingModal();
  });
}

function showBriefingModal() {
  // Remove existing modal
  const existing = document.getElementById('briefing-modal');
  if (existing) { existing.remove(); return; }

  const modal = document.createElement('div');
  modal.id = 'briefing-modal';
  modal.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:10000;background:#1a1a2e;border:2px solid #2ecc71;border-radius:12px;padding:24px;width:500px;max-height:400px;overflow-y:auto;color:#eee;font-family:ArkPixel,monospace;';
  modal.innerHTML = '<h3 style="margin:0 0 12px;color:#2ecc71;">🎙️ Board Meeting Briefing</h3><div id="briefing-text" style="font-size:13px;line-height:1.6;">Loading...</div><div style="margin-top:16px;display:flex;gap:8px;"><button id="briefing-tts" style="background:#2ecc71;color:#000;border:none;border-radius:6px;padding:6px 14px;cursor:pointer;font-family:ArkPixel,monospace;">🔊 Read Aloud</button><button id="briefing-close" style="background:#333;color:#eee;border:1px solid #555;border-radius:6px;padding:6px 14px;cursor:pointer;font-family:ArkPixel,monospace;">Close</button></div>';
  document.body.appendChild(modal);

  document.getElementById('briefing-close').addEventListener('click', () => modal.remove());

  fetch('/office/latest-briefing').then(r => r.json()).then(data => {
    const text = data.briefing?.text || 'No briefing available.';
    document.getElementById('briefing-text').textContent = text;
    document.getElementById('briefing-tts').addEventListener('click', () => {
      if ('speechSynthesis' in window) {
        const utter = new SpeechSynthesisUtterance(text);
        utter.rate = 0.9;
        speechSynthesis.speak(utter);
      }
    });
  }).catch(() => {
    document.getElementById('briefing-text').textContent = 'Failed to load briefing.';
  });
}

function update(time) {
  if (time - lastFetch > FETCH_INTERVAL) { fetchStatus(); lastFetch = time; }
  if (time - lastAgentsFetch > AGENTS_FETCH_INTERVAL) { fetchAgents(); lastAgentsFetch = time; }

  // Vitals polling
  if (time - lastVitalsFetch > VITALS_FETCH_INTERVAL) { fetchVitals(); lastVitalsFetch = time; }
  // Incident polling
  if (time - lastIncidentFetch > INCIDENT_FETCH_INTERVAL) { fetchIncidents(); lastIncidentFetch = time; }
  // Water cooler bubbles
  if (time - lastWaterCoolerTime > WATER_COOLER_INTERVAL) { showWaterCoolerBubble(game); lastWaterCoolerTime = time; }

  const effectiveStateForServer = pendingDesiredState || currentState;
  if (serverroom) {
    if (effectiveStateForServer === 'idle') {
      if (serverroom.anims.isPlaying) {
        serverroom.anims.stop();
        serverroom.setFrame(0);
      }
    } else {
      if (!serverroom.anims.isPlaying || serverroom.anims.currentAnim?.key !== 'serverroom_on') {
        serverroom.anims.play('serverroom_on', true);
      }
    }
  }

  if (window.errorBug) {
    if (effectiveStateForServer === 'error') {
      window.errorBug.setVisible(true);
      if (!window.errorBug.anims.isPlaying || window.errorBug.anims.currentAnim?.key !== 'error_bug') {
        window.errorBug.anims.play('error_bug', true);
      }
      const leftX = LAYOUT.furniture.errorBug.pingPong.leftX;
      const rightX = LAYOUT.furniture.errorBug.pingPong.rightX;
      const speed = LAYOUT.furniture.errorBug.pingPong.speed;
      const dir = window.errorBugDir || 1;
      window.errorBug.x += speed * dir;
      window.errorBug.y = LAYOUT.furniture.errorBug.y;
      if (window.errorBug.x >= rightX) {
        window.errorBug.x = rightX;
        window.errorBugDir = -1;
      } else if (window.errorBug.x <= leftX) {
        window.errorBug.x = leftX;
        window.errorBugDir = 1;
      }
    } else {
      window.errorBug.setVisible(false);
      window.errorBug.anims.stop();
    }
  }

  if (syncAnimSprite) {
    if (effectiveStateForServer === 'syncing') {
      if (!syncAnimSprite.anims.isPlaying || syncAnimSprite.anims.currentAnim?.key !== 'sync_anim') {
        syncAnimSprite.anims.play('sync_anim', true);
      }
    } else {
      if (syncAnimSprite.anims.isPlaying) syncAnimSprite.anims.stop();
      syncAnimSprite.setFrame(0);
    }
  }

  if (time - lastBubble > BUBBLE_INTERVAL) {
    showBubble();
    lastBubble = time;
  }
  if (time - lastCatBubble > CAT_BUBBLE_INTERVAL) {
    showCatBubble();
    lastCatBubble = time;
  }

  if (typewriterIndex < typewriterTarget.length && time - lastTypewriter > TYPEWRITER_DELAY) {
    typewriterText += typewriterTarget[typewriterIndex];
    statusText.textContent = typewriterText;
    typewriterIndex++;
    lastTypewriter = time;
  }

  moveStar(time);
}

function normalizeState(s) {
  if (!s) return 'idle';
  if (s === 'working') return 'writing';
  if (s === 'run' || s === 'running') return 'executing';
  if (s === 'sync') return 'syncing';
  if (s === 'research') return 'researching';
  return s;
}

// Context Pressure Heatmaps (CM-12)
function getContextUsagePct(agent) {
  const state = normalizeState(agent.state || 'idle');
  const baseUsage = { 'executing': 85, 'researching': 80, 'writing': 65, 'syncing': 40, 'idle': 15 };
  let usage = baseUsage[state] || 15;
  if (agent.progress !== undefined) {
    usage += Math.min(15, agent.progress * 0.15);
  }
  usage += (Math.random() * 10 - 5);
  return Math.min(100, Math.max(0, Math.round(usage)));
}

function getGlowColor(usagePct) {
  if (usagePct >= 90) return 0xff0000;
  if (usagePct >= 75) return 0xff8c00;
  if (usagePct >= 50) return 0x00bfff;
  return null;
}

function updateAgentGlow(container, agent) {
  if (!container.glowGraphics) return;
  const usagePct = getContextUsagePct(agent);
  const glowColor = getGlowColor(usagePct);
  if (!glowColor) {
    container.glowGraphics.clear();
    return;
  }
  const now = Date.now();
  const isCritical = usagePct >= 90;
  const baseRadius = 45;
  let pulseFactor = 1;
  if (isCritical) {
    container.glowPhase = (container.glowPhase || 0) + 0.1;
    pulseFactor = 1 + Math.sin(container.glowPhase) * 0.15;
  }
  const radius = baseRadius * pulseFactor;
  const alpha = isCritical ? 0.4 : 0.25;
  const lineWidth = isCritical ? 6 : 4;
  container.glowGraphics.clear();
  const layers = isCritical ? 4 : 3;
  for (let i = layers; i >= 1; i--) {
    const layerRadius = radius * (1 + i * 0.25);
    const layerAlpha = alpha * (1 - (i-1) * 0.25) / 255;
    container.glowGraphics.lineStyle(lineWidth, glowColor, layerAlpha);
    container.glowGraphics.strokeCircle(0, 0, layerRadius);
  }
}

function fetchStatus() {
  fetch('/status')
    .then(response => response.json())
    .then(data => {
      const nextState = normalizeState(data.state);
      const stateInfo = STATES[nextState] || STATES.idle;
      const changed = (pendingDesiredState === null) && (nextState !== currentState);
      const nextLine = '[' + stateInfo.name + '] ' + (data.detail || '...');
      if (changed) {
        typewriterTarget = nextLine;
        typewriterText = '';
        typewriterIndex = 0;

        pendingDesiredState = null;
        currentState = nextState;

        if (nextState === 'idle') {
          if (game.textures.exists('sofa_busy')) {
            sofa.setTexture('sofa_busy');
            sofa.anims.play('sofa_busy', true);
          }
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(false);
            window.starWorking.anims.stop();
          }
        } else if (nextState === 'error') {
          sofa.anims.stop();
          sofa.setTexture('sofa_idle');
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(false);
            window.starWorking.anims.stop();
          }
        } else if (nextState === 'syncing') {
          sofa.anims.stop();
          sofa.setTexture('sofa_idle');
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(false);
            window.starWorking.anims.stop();
          }
        } else {
          sofa.anims.stop();
          sofa.setTexture('sofa_idle');
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(true);
            window.starWorking.anims.play('star_working', true);
          }
        }

        if (serverroom) {
          if (nextState === 'idle') {
            serverroom.anims.stop();
            serverroom.setFrame(0);
          } else {
            serverroom.anims.play('serverroom_on', true);
          }
        }

        if (syncAnimSprite) {
          if (nextState === 'syncing') {
            if (!syncAnimSprite.anims.isPlaying || syncAnimSprite.anims.currentAnim?.key !== 'sync_anim') {
              syncAnimSprite.anims.play('sync_anim', true);
            }
          } else {
            if (syncAnimSprite.anims.isPlaying) syncAnimSprite.anims.stop();
            syncAnimSprite.setFrame(0);
          }
        }
      } else {
        if (!typewriterTarget || typewriterTarget !== nextLine) {
          typewriterTarget = nextLine;
          typewriterText = '';
          typewriterIndex = 0;
        }
      }
    })
    .catch(error => {
      typewriterTarget = 'Connection failed, retrying...';
      typewriterText = '';
      typewriterIndex = 0;
    });
}

function moveStar(time) {
  const effectiveState = pendingDesiredState || currentState;
  const stateInfo = STATES[effectiveState] || STATES.idle;
  const baseTarget = areas[stateInfo.area] || areas.breakroom;

  const dx = targetX - star.x;
  const dy = targetY - star.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const speed = 1.4;
  const wobble = Math.sin(time / 200) * 0.8;

  if (dist > 3) {
    star.x += (dx / dist) * speed;
    star.y += (dy / dist) * speed;
    star.setY(star.y + wobble);
    isMoving = true;
  } else {
    if (waypoints && waypoints.length > 0) {
      waypoints.shift();
      if (waypoints.length > 0) {
        targetX = waypoints[0].x;
        targetY = waypoints[0].y;
        isMoving = true;
      } else {
        if (pendingDesiredState !== null) {
          isMoving = false;
          currentState = pendingDesiredState;
          pendingDesiredState = null;

          if (currentState === 'idle') {
            star.setVisible(false);
            star.anims.stop();
            if (window.starWorking) {
              window.starWorking.setVisible(false);
              window.starWorking.anims.stop();
            }
          } else {
            star.setVisible(false);
            star.anims.stop();
            if (window.starWorking) {
              window.starWorking.setVisible(true);
              window.starWorking.anims.play('star_working', true);
            }
          }
        }
      }
    } else {
      if (pendingDesiredState !== null) {
        isMoving = false;
        currentState = pendingDesiredState;
        pendingDesiredState = null;

        if (currentState === 'idle') {
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(false);
            window.starWorking.anims.stop();
          }
          if (game.textures.exists('sofa_busy')) {
            sofa.setTexture('sofa_busy');
            sofa.anims.play('sofa_busy', true);
          }
        } else {
          star.setVisible(false);
          star.anims.stop();
          if (window.starWorking) {
            window.starWorking.setVisible(true);
            window.starWorking.anims.play('star_working', true);
          }
          sofa.anims.stop();
          sofa.setTexture('sofa_idle');
        }
      }
    }
  }
}

function showBubble() {
  if (bubble) { bubble.destroy(); bubble = null; }
  const texts = BUBBLE_TEXTS[currentState] || BUBBLE_TEXTS.idle;
  if (currentState === 'idle') return;

  let anchorX = star.x;
  let anchorY = star.y;
  if (currentState === 'syncing' && syncAnimSprite && syncAnimSprite.visible) {
    anchorX = syncAnimSprite.x;
    anchorY = syncAnimSprite.y;
  } else if (currentState === 'error' && window.errorBug && window.errorBug.visible) {
    anchorX = window.errorBug.x;
    anchorY = window.errorBug.y;
  } else if (!star.visible && window.starWorking && window.starWorking.visible) {
    anchorX = window.starWorking.x;
    anchorY = window.starWorking.y;
  }

  const text = texts[Math.floor(Math.random() * texts.length)];
  const bubbleY = anchorY - 70;
  const bg = game.add.rectangle(anchorX, bubbleY, text.length * 10 + 20, 28, 0xffffff, 0.95);
  bg.setStrokeStyle(2, 0x000000);
  const txt = game.add.text(anchorX, bubbleY, text, { fontFamily: 'ArkPixel, monospace', fontSize: '12px', fill: '#000', align: 'center' }).setOrigin(0.5);
  bubble = game.add.container(0, 0, [bg, txt]);
  bubble.setDepth(1200);
  setTimeout(() => { if (bubble) { bubble.destroy(); bubble = null; } }, 3000);
}

function showCatBubble() {
  if (!window.catSprite) return;
  if (window.catBubble) { window.catBubble.destroy(); window.catBubble = null; }
  const texts = BUBBLE_TEXTS.cat || ['Meow~', 'Purrrr...'];
  const text = texts[Math.floor(Math.random() * texts.length)];
  const anchorX = window.catSprite.x;
  const anchorY = window.catSprite.y - 60;
  const bg = game.add.rectangle(anchorX, anchorY, text.length * 10 + 20, 24, 0xfffbeb, 0.95);
  bg.setStrokeStyle(2, 0xd4a574);
  const txt = game.add.text(anchorX, anchorY, text, { fontFamily: 'ArkPixel, monospace', fontSize: '11px', fill: '#8b6914', align: 'center' }).setOrigin(0.5);
  window.catBubble = game.add.container(0, 0, [bg, txt]);
  window.catBubble.setDepth(2100);
  setTimeout(() => { if (window.catBubble) { window.catBubble.destroy(); window.catBubble = null; } }, 4000);
}

function fetchAgents() {
  fetch('/agents?t=' + Date.now(), { cache: 'no-store' })
    .then(response => response.json())
    .then(data => {
      if (!Array.isArray(data)) return;
      // 重置位置计数器
      // 按区域分配不同位置索引，避免重叠
      const areaSlots = { breakroom: 0, writing: 0, error: 0 };
      for (let agent of data) {
        const area = agent.area || 'breakroom';
        agent._slotIndex = areaSlots[area] || 0;
        areaSlots[area] = (areaSlots[area] || 0) + 1;
        renderAgent(agent);
      }
      // 移除不再存在的 agent
      const currentIds = new Set(data.map(a => a.agentId));
      for (let id in agents) {
        if (!currentIds.has(id)) {
          if (agents[id]) {
            agents[id].destroy();
            delete agents[id];
          }
        }
      }
    })
    .catch(error => {
      console.error('Failed to fetch agents:', error);
    });
}

function getAreaPosition(area, slotIndex) {
  const positions = AREA_POSITIONS[area] || AREA_POSITIONS.breakroom;
  const idx = (slotIndex || 0) % positions.length;
  return positions[idx];
}

function renderAgent(agent) {
  const agentId = agent.agentId;
  const name = agent.name || 'Agent';
  const area = agent.area || 'breakroom';
  const authStatus = agent.authStatus || 'pending';
  const isMain = !!agent.isMain;

  // 获取这个 agent 在区域里的位置
  const pos = getAreaPosition(area, agent._slotIndex || 0);
  const baseX = pos.x;
  const baseY = pos.y;

  // 颜色
  const bodyColor = AGENT_COLORS[agentId] || AGENT_COLORS.default;
  const nameColor = NAME_TAG_COLORS[authStatus] || NAME_TAG_COLORS.default;

  // 透明度（离线/待批准/拒绝时变半透明）
  let alpha = 1;
  if (authStatus === 'pending') alpha = 0.7;
  if (authStatus === 'rejected') alpha = 0.4;
  if (authStatus === 'offline') alpha = 0.5;

  if (!agents[agentId]) {
    // 新建 agent
    const container = game.add.container(baseX, baseY);
    container.setDepth(1200 + (isMain ? 100 : 0)); // 放到最顶层！

    // 像素小人：用星星图标，更明显
    const starIcon = game.add.text(0, 0, '⭐', {
      fontFamily: 'ArkPixel, monospace',
      fontSize: '32px'
    }).setOrigin(0.5);
    starIcon.name = 'starIcon';
    // Make agent clickable
    starIcon.setInteractive(new Phaser.Geom.Circle(0, 0, 20), Phaser.Geom.Circle.Contains);
    starIcon.on('pointerdown', () => {
        if (typeof window.openAgentPanel === 'function') {
            window.openAgentPanel(agentId);
        }
    });

    // 名字标签（漂浮）
    const nameTag = game.add.text(0, -36, name, {
      fontFamily: 'ArkPixel, monospace',
      fontSize: '14px',
      fill: '#' + nameColor.toString(16).padStart(6, '0'),
      stroke: '#000',
      strokeThickness: 3,
      backgroundColor: 'rgba(255,255,255,0.95)'
    }).setOrigin(0.5);
    nameTag.name = 'nameTag';

    // 状态小点（绿色/黄色/红色）
    let dotColor = 0x64748b;
    if (authStatus === 'approved') dotColor = 0x22c55e;
    if (authStatus === 'pending') dotColor = 0xf59e0b;
    if (authStatus === 'rejected') dotColor = 0xef4444;
    if (authStatus === 'offline') dotColor = 0x94a3b8;
    const statusDot = game.add.circle(20, -20, 5, dotColor, alpha);
    statusDot.setStrokeStyle(2, 0x000000, alpha);
    statusDot.name = 'statusDot';

    // Progress bar (above agent)
    const barW = 36, barH = 4;
    const barBg = game.add.rectangle(0, -42, barW, barH, 0x000000, 0.6);
    barBg.setStrokeStyle(1, 0xffffff, 0.5);
    const barFill = game.add.rectangle(-barW/2, -42, 0, barH, 0x22c55e); // width 0 initially
    barFill.setOrigin(0, 0.5);
    barFill.name = 'progressFill';

    container.add([starIcon, statusDot, nameTag, barBg, barFill]);
    container.progressFill = barFill;

    // Update progress bar when agent updates
    const progress = Math.min(100, Math.max(0, agent.progress || 0));
    barFill.width = (barW * progress) / 100;

    agents[agentId] = container;
  } else {
    // 更新 agent
    const container = agents[agentId];
    container.setPosition(baseX, baseY);
    container.setAlpha(alpha);
    container.setDepth(1200 + (isMain ? 100 : 0));

    // 更新名字和颜色（如果变化）
    const nameTag = container.getAt(2);
    if (nameTag && nameTag.name === 'nameTag') {
      nameTag.setText(name);
      nameTag.setFill('#' + (NAME_TAG_COLORS[authStatus] || NAME_TAG_COLORS.default).toString(16).padStart(6, '0'));
    }
    // 更新状态点颜色
    const statusDot = container.getAt(1);
    if (statusDot && statusDot.name === 'statusDot') {
      let dotColor = 0x64748b;
      if (authStatus === 'approved') dotColor = 0x22c55e;
      if (authStatus === 'pending') dotColor = 0xf59e0b;
      if (authStatus === 'rejected') dotColor = 0xef4444;
      if (authStatus === 'offline') dotColor = 0x94a3b8;
      statusDot.fillColor = dotColor;
    }
    // Update progress bar
    const progress = Math.min(100, Math.max(0, agent.progress || 0));
    if (container.progressFill) {
      const barW = 36;
      container.progressFill.width = (barW * progress) / 100;
    }
  }
}

// 启动游戏
initGame();
