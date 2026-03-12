#!/usr/bin/env python3
"""
Patch game.js to add dynamic room rendering from /rooms endpoint.
This implements task_0005: "Render rooms from rooms.json on office canvas"
"""

import re
from pathlib import Path

GAME_JS = Path("/home/dustin/openclaw-office/frontend/game.js")
if not GAME_JS.exists():
    print(f"❌ game.js not found at {GAME_JS}")
    exit(1)

original = GAME_JS.read_text()

# Insert after the STATES definition (around line 110)
states_section_end = original.find("const BUBBLE_TEXTS = {")
if states_section_end == -1:
    print("❌ Cannot find insertion point")
    exit(1)

# Add room loading system
room_system_code = '''
// === Dynamic Room System ===
let OFFICE_ROOMS = {};  // roomId -> room definition

async function loadOfficeRooms() {
  try {
    const resp = await fetch('/rooms');
    if (resp.ok) {
      const data = await resp.json();
      const rooms = data.rooms || [];
      for (const room of rooms) {
        OFFICE_ROOMS[room.id] = room;
        // Generate positions for this room if not already defined
        if (!AREA_POSITIONS[room.id]) {
          // Distribute rooms in a grid pattern to the right side of canvas
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

'''

insertion_point = original[:states_section_end].rfind('}')
if insertion_point == -1:
    print("❌ Cannot find STATES closing brace")
    exit(1)

# Insert after STATES definition
new_code = original[:insertion_point+1] + '\n' + room_system_code + '\n' + original[insertion_point+1:]

# Now add room loading in preload or create
# Find the preload function and add rooms loading after memo loading
preload_match = re.search(r'async function preload\(\) \{([\s\S]*?)\n\}', new_code)
if preload_match:
    preload_body = preload_match.group(1)
    # Insert after the memo loading lines (find "// 加载昨日小记")
    memo_comment = "// 加载昨日小记"
    memo_pos = preload_body.find(memo_comment)
    if memo_pos != -1:
        insert_pos = preload_body.find('\n', memo_pos) + 1
        new_preload_body = (
            preload_body[:insert_pos] +
            '\n  // Load office rooms for dynamic rendering\n  await loadOfficeRooms();\n' +
            preload_body[insert_pos:]
        )
        new_code = new_code.replace(preload_match.group(0), f"async function preload() {{{new_preload_body}\n}}")
    else:
        print("⚠️  Could not find memo loading section, adding to end of preload")
        new_preload_body = preload_body + "\n  await loadOfficeRooms();\n"
        new_code = new_code.replace(preload_match.group(0), f"async function preload() {{{new_preload_body}\n}}")
else:
    print("❌ Cannot find preload function")
    exit(1)

# Add drawRoomsOverlay call in create() after star creation
create_match = re.search(r'function create\(\) \{([\s\S]*?)\n\}', new_code)
if create_match:
    create_body = create_match.group(1)
    # Find where star is created and add overlay after a short delay
    star_creation = re.search(r'star = game\.physics\.add\.sprite\([^;]+\);', create_body)
    if star_creation:
        insert_pos = star_creation.end()
        new_create_body = (
            create_body[:insert_pos] +
            '\n  // Draw room overlays\n  drawRoomsOverlay(this);' +
            create_body[insert_pos:]
        )
        new_code = new_code.replace(create_match.group(0), f"function create() {{{new_create_body}\n}}")
else:
    print("❌ Cannot find create function")
    exit(1)

# Write patched file
GAME_JS.write_text(new_code)
print("✅ Patched game.js with dynamic room rendering")
print("   Features added:")
print("   - loadOfficeRooms(): fetches /rooms endpoint")
print("   - drawRoomsOverlay(): renders rooms as colored zones")
print("   - AREA_POSITIONS auto-generated per room")
print("   - Called during preload and create")
