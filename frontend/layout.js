// OpenClaw Office UI - Layout & Depth Configuration
// All coordinates, depths, and asset paths managed here

const LAYOUT = {
  // === Game canvas ===
  game: {
    width: 1280,
    height: 720
  },

  // === Room areas (mapped to new futuristic office background) ===
  areas: {
    // Top-left: server/ops room
    serverroom:  { x: 240, y: 130 },
    error:       { x: 240, y: 130 },
    // Top-right: lounge/break area
    breakroom:   { x: 1000, y: 150 },
    idle:        { x: 1000, y: 150 },
    // Middle-left: coding area
    writing:     { x: 280, y: 370 },
    executing:   { x: 280, y: 370 },
    coding:      { x: 280, y: 370 },
    // Middle-right: research area
    researching: { x: 850, y: 370 },
    // Bottom-left: command center
    command:     { x: 240, y: 570 },
    syncing:     { x: 240, y: 570 },
    // Bottom-right: boardroom / meeting
    boardroom:   { x: 850, y: 570 },
    team_meeting:{ x: 850, y: 570 },
    // Center corridor
    door:        { x: 530, y: 360 },
    talking:     { x: 530, y: 360 },
    // Sleeping (dim area, top-right corner)
    sleeping:    { x: 1150, y: 100 }
  },

  // === Furniture positions on new background ===
  furniture: {
    // Cat (bottom corridor)
    cat: {
      x: 530,
      y: 620,
      origin: { x: 0.5, y: 0.5 },
      depth: 2000
    }
  },

  // === Agent sprite config ===
  agentSprite: {
    frameWidth: 64,
    frameHeight: 64,
    scale: 1.6,         // scale up pixel art sprites
    walkSpeed: 1.8,     // pixels per frame
    idleFrameRate: 4,
    walkFrameRate: 8
  },

  // === Chat bubble config ===
  bubble: {
    maxWidth: 200,
    padding: 8,
    depth: 3000,
    duration: 4000,
    typewriterDelay: 40
  },

  // === Talking portrait config ===
  portrait: {
    size: 64,           // display size for 96px source
    depth: 3001,
    offsetX: -110,      // offset from bubble center
    offsetY: 0
  },

  // === Plaque ===
  plaque: {
    x: 640,
    y: 720 - 36,
    width: 420,
    height: 44
  },

  // === Total asset count for loading bar ===
  totalAssets: 14
};

// === Area positions for multi-agent spread ===
const AREA_POSITIONS = {
  breakroom: [
    { x: 960, y: 140 },
    { x: 1040, y: 160 },
    { x: 1100, y: 130 },
    { x: 980, y: 180 },
    { x: 1060, y: 190 },
    { x: 920, y: 170 }
  ],
  writing: [
    { x: 250, y: 350 },
    { x: 330, y: 380 },
    { x: 200, y: 390 },
    { x: 380, y: 350 },
    { x: 280, y: 410 },
    { x: 160, y: 370 }
  ],
  researching: [
    { x: 820, y: 350 },
    { x: 900, y: 380 },
    { x: 780, y: 390 },
    { x: 950, y: 360 },
    { x: 860, y: 410 }
  ],
  error: [
    { x: 200, y: 120 },
    { x: 280, y: 140 },
    { x: 160, y: 150 },
    { x: 320, y: 120 },
    { x: 240, y: 160 }
  ],
  serverroom: [
    { x: 200, y: 120 },
    { x: 280, y: 140 }
  ],
  command: [
    { x: 200, y: 560 },
    { x: 280, y: 580 },
    { x: 160, y: 580 }
  ],
  boardroom: [
    { x: 820, y: 560 },
    { x: 900, y: 580 },
    { x: 780, y: 570 },
    { x: 950, y: 560 }
  ],
  workspace: [
    { x: 250, y: 350 }
  ],
  lobby: [
    { x: 530, y: 360 }
  ],
  observatory: [
    { x: 1100, y: 130 }
  ]
};
