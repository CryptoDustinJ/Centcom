#!/usr/bin/env python3
"""Slice the Nano Banana 2 sprite sheet into Phaser-compatible sprite sheets.

Source: 'openclaw office pixal plan/4__seperate_agents_a_coder_(co.png'
Output: frontend/sprites/{agent}-walk.png, {agent}-idle.png, {agent}-talk.png

Also slices desk assets and crops the office background.
"""

from PIL import Image
import os

OUT = 'frontend/sprites'
os.makedirs(OUT, exist_ok=True)

AGENTS = ['codemaster', 'rook', 'nova', 'ralph']


def remove_bg(img, threshold=180):
    """Remove checkered light background, making it transparent."""
    img = img.convert('RGBA')
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r > threshold and g > threshold and b > threshold:
                pixels[x, y] = (r, g, b, 0)
    return img


def find_content_bbox(img):
    """Find bounding box of non-transparent content."""
    pixels = img.load()
    w, h = img.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            if pixels[x, y][3] > 32:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y
    if max_x < min_x:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


def extract_frame(img, region, target_size, bg_thresh=180):
    """Extract sprite from region, remove bg, center in target_size."""
    crop = img.crop(region)
    crop = remove_bg(crop, bg_thresh)
    bbox = find_content_bbox(crop)
    if bbox is None:
        return Image.new('RGBA', target_size, (0, 0, 0, 0))

    content = crop.crop(bbox)
    cw, ch = content.size
    tw, th = target_size

    # Scale down if content is larger than target
    if cw > tw or ch > th:
        ratio = min(tw / cw, th / ch)
        content = content.resize((int(cw * ratio), int(ch * ratio)), Image.NEAREST)
        cw, ch = content.size

    result = Image.new('RGBA', target_size, (0, 0, 0, 0))
    ox = (tw - cw) // 2
    oy = th - ch  # align to bottom
    result.paste(content, (ox, oy), content)
    return result


def slice_agents():
    """Slice agent sprite sheet using precise frame boundaries from gap analysis."""
    src_path = 'openclaw office pixal plan/4__seperate_agents_a_coder_(co.png'
    img = Image.open(src_path).convert('RGBA')
    print(f'Agent sheet: {img.size}')

    # Precise frame x-boundaries from vertical gap analysis:
    # Each agent has 3 frames. Gap analysis found these content columns:
    #   CM:    frame1=42-118,  frame2=160-209, frame3=249-316
    #   Rook:  frame1=469-520, frame2=558-613, frame3=649-704
    #   Nova:  frame1=795-845, frame2=885-935, frame3=970-1053
    #   Ralph: frame1=1127-1178, frame2=1214-1261, frame3=1304-1355
    agent_frame_xs = [
        [(155, 215), (245, 305), (335, 415)],       # CodeMaster
        [(465, 525), (555, 618), (645, 710)],       # Rook
        [(790, 850), (880, 940), (965, 1058)],      # Nova
        [(1122, 1182), (1210, 1265), (1300, 1360)], # Ralph
    ]

    # Row y-ranges (from horizontal density analysis):
    direction_rows = [
        ('down',  100, 190),
        ('up',    200, 290),
        ('left',  300, 390),
        ('right', 395, 485),
    ]

    idle_row = (495, 590)
    talking_row = (615, 690)

    # Per-agent talking headshot x-ranges (portrait only, excludes text labels)
    agent_talk_xs = [
        (155, 415),    # CodeMaster (wider scene with computer)
        (445, 545),    # Rook (portrait only)
        (775, 875),    # Nova (portrait only)
        (1115, 1195),  # Ralph (portrait only)
    ]

    FRAME_W = 64
    FRAME_H = 64
    TALK_W = 96
    TALK_H = 96

    for agent_idx, agent_name in enumerate(AGENTS):
        frames_x = agent_frame_xs[agent_idx]

        # ── Walk sheet: 4 directions × 3 frames = 12 frames ──
        # Order: down(3), up(3), left(3), right(3)
        walk_sheet = Image.new('RGBA', (FRAME_W * 12, FRAME_H), (0, 0, 0, 0))
        fi = 0
        for dir_name, row_y1, row_y2 in direction_rows:
            for fx1, fx2 in frames_x:
                sprite = extract_frame(img, (fx1, row_y1, fx2, row_y2), (FRAME_W, FRAME_H))
                walk_sheet.paste(sprite, (fi * FRAME_W, 0), sprite)
                fi += 1

        walk_path = os.path.join(OUT, f'{agent_name}-walk.png')
        walk_sheet.save(walk_path)
        print(f'  {walk_path}: {walk_sheet.size}')

        # ── Idle sheet: 3 frames ──
        idle_sheet = Image.new('RGBA', (FRAME_W * 3, FRAME_H), (0, 0, 0, 0))
        y1, y2 = idle_row
        for f, (fx1, fx2) in enumerate(frames_x):
            sprite = extract_frame(img, (fx1, y1, fx2, y2), (FRAME_W, FRAME_H))
            idle_sheet.paste(sprite, (f * FRAME_W, 0), sprite)

        idle_path = os.path.join(OUT, f'{agent_name}-idle.png')
        idle_sheet.save(idle_path)
        print(f'  {idle_path}: {idle_sheet.size}')

        # ── Talking headshot: single larger frame ──
        ty1, ty2 = talking_row
        talk_x1, talk_x2 = agent_talk_xs[agent_idx]
        sprite = extract_frame(img, (talk_x1, ty1, talk_x2, ty2), (TALK_W, TALK_H))
        sprite.save(os.path.join(OUT, f'{agent_name}-talk.png'))
        print(f'  {agent_name}-talk.png: {TALK_W}x{TALK_H}')


def slice_desks():
    """Slice desk images into 3-state sprite sheets."""
    DESK_W = 192
    DESK_H = 192

    for name, path, regions in [
        ('command-desk', 'openclaw office pixal plan/_i_giant_desk_with_a_speaker_a.png',
         [(40, 80, 440, 560), (470, 80, 900, 560), (930, 80, 1370, 560)]),
        ('coding-desk', 'openclaw office pixal plan/a_giant_coding_desk__area.png',
         [(20, 30, 470, 620), (470, 30, 920, 620), (920, 30, 1390, 620)]),
    ]:
        src = Image.open(path).convert('RGBA')
        print(f'{name}: {src.size}')
        sheet = Image.new('RGBA', (DESK_W * 3, DESK_H), (0, 0, 0, 0))
        for i, region in enumerate(regions):
            sprite = extract_frame(src, region, (DESK_W, DESK_H), bg_thresh=50)
            sheet.paste(sprite, (i * DESK_W, 0), sprite)
        out = os.path.join(OUT, f'{name}.png')
        sheet.save(out)
        print(f'  {out}: {sheet.size}')


def crop_background():
    """Crop office tileset into game background."""
    bg = Image.open('openclaw office pixal plan/high_tech_futeristic_ai_office.png').convert('RGBA')
    print(f'Office bg source: {bg.size}')

    # Main office area is the large connected rooms on the left
    # Exclude the door/item sprites on the right side and bottom-right
    # Crop to just the rooms area, then scale to 1280x720
    main_area = bg.crop((0, 0, 975, 630))
    scaled = main_area.resize((1280, 720), Image.NEAREST)

    out = os.path.join(OUT, 'office-bg.png')
    scaled.save(out)
    print(f'  {out}: {scaled.size}')


if __name__ == '__main__':
    print('=== Slicing agent sprites ===')
    slice_agents()
    print('\n=== Slicing desk assets ===')
    slice_desks()
    print('\n=== Cropping background ===')
    crop_background()
    print('\nDone!')
