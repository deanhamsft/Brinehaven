# app_core.py
from __future__ import annotations
import pygame
import math
import sys
import os

def draw_circular_text(surface, text, center, radius, color, font_size, start_angle=90):
    if radius < 15 or font_size < 10:
        return
    try:
        font = pygame.font.SysFont("arial", font_size, bold=True)
    except:
        font = pygame.font.SysFont(None, font_size, bold=True)
    text = text.upper()
    angle_step = 360.0 / len(text) if len(text) > 0 else 0
    for i, char in enumerate(text):
        angle = start_angle + i * angle_step
        rad = math.radians(angle)
        x = center[0] + radius * math.cos(rad)
        y = center[1] + radius * math.sin(rad)
        char_surf = font.render(char, True, color)
        rotated = pygame.transform.rotate(char_surf, -angle - 90)
        rect = rotated.get_rect(center=(int(x), int(y)))
        surface.blit(rotated, rect)


def control_window(initial_image_path, shared_revealed, shared_running, shared_image_path,
                   display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset,
                   shared_markers, shared_current_condition_idx, shared_current_marker_size,
                   shared_mouse_map_nx, shared_mouse_map_ny):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Control Monitor (Reveal Fog)")
    
    current_path = initial_image_path
    image = pygame.image.load(current_path).convert()
    orig_w, orig_h = image.get_size()
    
    base_zoom = min(screen_w / orig_w, screen_h / orig_h)
    
    fog_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
    fog_orig.fill((20, 20, 60, 180))
    
    clock = pygame.time.Clock()
    reveal_radius = 60
    brush_color = (255, 255, 100, 120)
    
    conditions = [
        "BLINDED", "CHARMED", "DEAFENED", "EXHAUSTION", "FRIGHTENED",
        "GRAPPLED", "INCAPACITATED", "INVISIBLE", "PARALYZED", "PETRIFIED",
        "POISONED", "PRONE", "RESTRAINED", "STUNNED", "UNCONSCIOUS"
    ]
    
    marker_colors = [
        (0, 0, 0, 255),       # Blinded: Black
        (255, 192, 203, 255), # Charmed: Pink
        (128, 128, 128, 255), # Deafened: Gray
        (169, 169, 169, 255), # Exhaustion: Dark Gray
        (255, 255, 0, 255),   # Frightened: Yellow
        (0, 128, 0, 255),     # Grappled: Green
        (139, 0, 0, 255),     # Incapacitated: Dark Red
        (173, 216, 230, 255), # Invisible: Light Blue
        (0, 0, 255, 255),     # Paralyzed: Blue
        (112, 128, 144, 255), # Petrified: Slate Gray
        (0, 255, 0, 255),     # Poisoned: Lime
        (165, 42, 42, 255),   # Prone: Brown
        (255, 165, 0, 255),   # Restrained: Orange
        (218, 165, 32, 255),  # Stunned: Goldenrod
        (75, 0, 130, 255)     # Unconscious: Indigo
    ]
    
    marker_sizes = [12, 24, 40]  # Base screen-space radius @ zoom=1.0
    
    font = pygame.font.SysFont(None, 36)
    help_text = font.render(
        "LEFT=reveal | Shift+LEFT=pan | Wheel=zoom | F=new image | R=reset fog | "
        "M=remove last marker | 1-9,0,A-D,G=condition | Q/W/E=size | RIGHT=place marker | ESC=quit",
        True, (255, 255, 100)
    )
    status_msg = None
    status_timer = 0
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    current_drag_mode = None
    prev_pos = None
    
    min_zoom_mult = 0.1
    max_zoom_mult = 20.0
    
    while shared_running.value:
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shared_running.value = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shared_running.value = False
                if event.key == pygame.K_f:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    new_path = filedialog.askopenfilename(
                        title="Select New Map Image",
                        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
                    )
                    root.destroy()
                    if new_path and os.path.exists(new_path):
                        shared_image_path[:] = [new_path]
                        status_msg = font.render("New map loaded", True, (100, 255, 100))
                        status_timer = 180
                if event.key == pygame.K_r:
                    shared_revealed[:] = []
                    shared_markers[:] = []
                    shared_fog_reset.value += 1
                    status_msg = font.render("Fog & markers reset", True, (220, 100, 100))
                    status_timer = 120
                if event.key == pygame.K_m:
                    shared_markers.pop()
                    status_msg = font.render("Markers cleared", True, (220, 180, 60))
                    status_timer = 120
                # Condition selection 1-9,0,a-d,g
                if pygame.K_1 <= event.key <= pygame.K_9:
                    idx = event.key - pygame.K_1
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_0:
                    idx = 9
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_a:
                    idx = 10
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_s:
                    idx = 11
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_d:
                    idx = 12
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_f:
                    idx = 13
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_g:
                    idx = 14
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                # Marker size Q/W/E
                if event.key in (pygame.K_q, pygame.K_w, pygame.K_e):
                    if event.key == pygame.K_q: idx = 0
                    elif event.key == pygame.K_w: idx = 1
                    else: idx = 2
                    shared_current_marker_size.value = idx
                    status_msg = font.render(f"Marker size: {['Small','Medium','Large'][idx]}", True, (100, 255, 100))
                    status_timer = 120

            if event.type == pygame.MOUSEBUTTONDOWN:
                keys = pygame.key.get_pressed()   # get current modifier keys

                if event.button == 1:  # left click
                    shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                    current_drag_mode = 'pan' if shift_pressed else 'reveal'
                    prev_pos = event.pos

                elif event.button == 3:  # right click
                    pos = event.pos  # (x, y) in screen space

                    # Check if Shift is held → remove mode
                    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                        if not shared_markers:
                            status_msg = font.render("No markers to remove", True, (180, 180, 180))
                            status_timer = 90
                        else:
                            # Convert click position to map coordinates
                            draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                            draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                            click_map_x = (pos[0] - draw_x) / current_zoom
                            click_map_y = (pos[1] - draw_y) / current_zoom

                            closest_idx = None
                            closest_dist = float('inf')
                            removal_threshold = 60  # pixels on screen at zoom=1 → adjust as needed

                            for i, (nx, ny, nr, _) in enumerate(shared_markers):
                                marker_x = nx * orig_w
                                marker_y = ny * orig_h
                                dist = math.hypot(click_map_x - marker_x, click_map_y - marker_y)
                                screen_dist = dist * current_zoom  # approximate screen distance

                                if screen_dist < closest_dist:
                                    closest_dist = screen_dist
                                    closest_idx = i

                            if closest_idx is not None and closest_dist <= removal_threshold:
                                removed_condition = conditions[shared_markers[closest_idx][3]]
                                del shared_markers[closest_idx]
                                status_msg = font.render(f"Removed {removed_condition}", True, (220, 100, 100))
                                status_timer = 120
                            else:
                                status_msg = font.render("No marker near click", True, (180, 180, 180))
                                status_timer = 90

                    else:
                        # Normal right-click → place new marker (existing code)
                        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                        map_x = (pos[0] - draw_x) / current_zoom
                        map_y = (pos[1] - draw_y) / current_zoom
                        nx = map_x / orig_w
                        ny = map_y / orig_h
                        base_r = marker_sizes[shared_current_marker_size.value]
                        nr = base_r / current_zoom / max(orig_w, orig_h)
                        color_idx = shared_current_condition_idx.value
                        shared_markers.append((nx, ny, nr, color_idx))

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    current_drag_mode = None
                    prev_pos = None
            if event.type == pygame.MOUSEWHEEL:
                factor = 1.1 ** event.y
                new_mult = shared_zoom_multiplier.value * factor
                new_mult = max(min_zoom_mult, min(max_zoom_mult, new_mult))
                potential_zoom = base_zoom * new_mult
                if orig_w * potential_zoom > 32767 or orig_h * potential_zoom > 32767:
                    new_mult = min(new_mult,
                                   32767 / (orig_w * base_zoom) if orig_w * base_zoom else 1,
                                   32767 / (orig_h * base_zoom) if orig_h * base_zoom else 1)
                shared_zoom_multiplier.value = new_mult
            
        if shared_image_path and shared_image_path[0] != current_path:
            try:
                current_path = shared_image_path[0]
                image = pygame.image.load(current_path).convert()
                orig_w, orig_h = image.get_size()
                base_zoom = min(screen_w / orig_w, screen_h / orig_h)
                fog_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
                fog_orig.fill((20, 20, 60, 180))
                shared_revealed[:] = []
                shared_markers[:] = []
                shared_zoom_multiplier.value = 1.0
                shared_camera_nx.value = 0.5
                shared_camera_ny.value = 0.5
                shared_fog_reset.value += 1
                prev_len = 0
                local_fog_reset = shared_fog_reset.value
            except Exception as e:
                print("Failed to load new image:", e)
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            fog_orig.fill((20, 20, 60, 180))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = nx * orig_w
                y = ny * orig_h
                r = nr * max(orig_w, orig_h)
                pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(x), int(y)), int(r))
            prev_len = current_len
        
        mouse_pressed = pygame.mouse.get_pressed()[0]
        if mouse_pressed and current_drag_mode:
            pos = pygame.mouse.get_pos()
            if prev_pos is not None:
                if current_drag_mode == 'pan':
                    delta_x = pos[0] - prev_pos[0]
                    delta_y = pos[1] - prev_pos[1]
                    delta_map_x = -delta_x / current_zoom
                    delta_map_y = -delta_y / current_zoom
                    shared_camera_nx.value += delta_map_x / orig_w
                    shared_camera_ny.value += delta_map_y / orig_h
                    shared_camera_nx.value = max(0, min(1, shared_camera_nx.value))
                    shared_camera_ny.value = max(0, min(1, shared_camera_ny.value))
                elif current_drag_mode == 'reveal':
                    draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                    draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                    map_x = (pos[0] - draw_x) / current_zoom
                    map_y = (pos[1] - draw_y) / current_zoom
                    map_r = reveal_radius / current_zoom
                    nx = map_x / orig_w
                    ny = map_y / orig_h
                    nr = map_r / max(orig_w, orig_h)
                    shared_revealed.append((nx, ny, nr))
                    pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(map_x), int(map_y)), int(map_r))
                    pygame.draw.circle(screen, brush_color, pos, reveal_radius + 4, 3)
            prev_pos = pos
                # Share mouse position in map-normalized coordinates (0-1 range on original image)
        mx, my = pygame.mouse.get_pos()
        if 0 <= mx < screen_w and 0 <= my < screen_h:
            draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
            draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
            map_x = (mx - draw_x) / current_zoom
            map_y = (my - draw_y) / current_zoom
            shared_mouse_map_nx.value = map_x / orig_w
            shared_mouse_map_ny.value = map_y / orig_h
        else:
            shared_mouse_map_nx.value = -1.0
            shared_mouse_map_ny.value = -1.0

        scaled_w = int(orig_w * current_zoom)
        scaled_h = int(orig_h * current_zoom)
        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
        
        try:
            bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))
            fog_scaled = pygame.transform.smoothscale(fog_orig, (scaled_w, scaled_h))
        except ValueError as e:
            print("Zoom scale error:", e)
            continue
        
        screen.fill((0, 0, 0))
        screen.blit(bg_scaled, (draw_x, draw_y))
        screen.blit(fog_scaled, (draw_x, draw_y))
        
        # Draw all markers as rings with circular text
        for nx, ny, nr, condition_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (int(draw_x + x), int(draw_y + y))
            color = marker_colors[condition_idx]
            width = max(2, int(r / 8))
            pygame.draw.circle(screen, color, pos, r, width=width)
            
            text_radius = r - width * 2.0
            font_size = max(10, int(r / (len(conditions[condition_idx]) * 0.35)))
            draw_circular_text(
                screen,
                conditions[condition_idx],
                pos,
                text_radius,
                (0, 0, 0, 255),  # black bold text
                font_size
            )
        
        if not mouse_pressed:
            mx, my = pygame.mouse.get_pos()
            pygame.draw.circle(screen, (255, 255, 180, 80), (mx, my), reveal_radius, 2)
        
        screen.blit(help_text, (20, 20))
        if status_timer > 0:
            screen.blit(status_msg, (20, 70))
            status_timer -= 1
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


def audience_window(initial_image_path, shared_revealed, shared_running, shared_image_path,
                    display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset,
                    shared_markers, shared_current_condition_idx, shared_current_marker_size,
                    shared_mouse_map_nx, shared_mouse_map_ny):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Audience Monitor")
    
    current_path = initial_image_path
    image = pygame.image.load(current_path).convert()
    orig_w, orig_h = image.get_size()
    
    base_zoom = min(screen_w / orig_w, screen_h / orig_h)
    
    mask_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
    mask_orig.fill((0, 0, 0, 255))
    
    conditions = [
        "BLINDED", "CHARMED", "DEAFENED", "EXHAUSTION", "FRIGHTENED",
        "GRAPPLED", "INCAPACITATED", "INVISIBLE", "PARALYZED", "PETRIFIED",
        "POISONED", "PRONE", "RESTRAINED", "STUNNED", "UNCONSCIOUS"
    ]
    
    marker_colors = [
        (0, 0, 0, 255),
        (255, 192, 203, 255),
        (128, 128, 128, 255),
        (169, 169, 169, 255),
        (255, 255, 0, 255),
        (0, 128, 0, 255),
        (139, 0, 0, 255),
        (173, 216, 230, 255),
        (0, 0, 255, 255),
        (112, 128, 144, 255),
        (0, 255, 0, 255),
        (165, 42, 42, 255),
        (255, 165, 0, 255),
        (218, 165, 32, 255),
        (75, 0, 130, 255)
    ]
    
    marker_sizes = [12, 24, 40]
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    clock = pygame.time.Clock()
    
    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or \
               (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                shared_running.value = False
        
        if shared_image_path and shared_image_path[0] != current_path:
            try:
                current_path = shared_image_path[0]
                image = pygame.image.load(current_path).convert()
                orig_w, orig_h = image.get_size()
                base_zoom = min(screen_w / orig_w, screen_h / orig_h)
                mask_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
                mask_orig.fill((0, 0, 0, 255))
                prev_len = 0
                local_fog_reset = shared_fog_reset.value
            except:
                pass
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            mask_orig.fill((0, 0, 0, 255))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        
        current_len = len(shared_revealed)
        
        # Defensive: never go backwards, clamp to actual length
        if shared_fog_reset.value > local_fog_reset:
            mask_orig.fill((0, 0, 0, 255))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0  # force full reset
        
        # Only process new reveals if length actually increased
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                if i >= len(shared_revealed):  # safety against concurrent clear
                    break
                nx, ny, nr = shared_revealed[i]
                x = int(nx * orig_w)
                y = int(ny * orig_h)
                r = int(nr * max(orig_w, orig_h))
                pygame.draw.circle(mask_orig, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
        
        scaled_w = int(orig_w * current_zoom)
        scaled_h = int(orig_h * current_zoom)
        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
        
        try:
            bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))
            mask_scaled = pygame.transform.smoothscale(mask_orig, (scaled_w, scaled_h))
        except ValueError as e:
            print("Zoom scale error (audience):", e)
            continue
        
        screen.fill((0, 0, 0))
        screen.blit(bg_scaled, (draw_x, draw_y))
        screen.blit(mask_scaled, (draw_x, draw_y))
        
        # Mirror DM mouse cursor on audience display
        if shared_mouse_map_nx.value >= 0:
            mouse_map_x = shared_mouse_map_nx.value * orig_w * current_zoom
            mouse_map_y = shared_mouse_map_ny.value * orig_h * current_zoom
            indicator_x = int(draw_x + mouse_map_x)
            indicator_y = int(draw_y + mouse_map_y)

            # Red semi-transparent crosshair
            pygame.draw.circle(screen, (255, 50, 50, 140), (indicator_x, indicator_y), 14, 3)
            pygame.draw.line(screen, (255, 80, 80, 200), (indicator_x - 24, indicator_y), (indicator_x + 24, indicator_y), 4)
            pygame.draw.line(screen, (255, 80, 80, 200), (indicator_x, indicator_y - 24), (indicator_x, indicator_y + 24), 4)

            # Small "DM" label (optional, appears when zoomed in reasonably)
            if current_zoom > 0.4:
                font_small = pygame.font.SysFont(None, 22, bold=True)
                label = font_small.render("DM", True, (255, 60, 60))
                screen.blit(label, (indicator_x + 18, indicator_y - 28))

        # Draw markers as rings with circular text
        for nx, ny, nr, condition_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (int(draw_x + x), int(draw_y + y))
            color = marker_colors[condition_idx]
            width = max(2, int(r / 8))
            pygame.draw.circle(screen, color, pos, r, width=width)
            
            text_radius = r - width * 2.0
            font_size = max(10, int(r / (len(conditions[condition_idx]) * 0.35)))
            draw_circular_text(
                screen,
                conditions[condition_idx],
                pos,
                text_radius,
                (0, 0, 0, 255),  # black bold text
                font_size
            )
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()