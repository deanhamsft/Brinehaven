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


def map_view(orig_w, orig_h, zoom, camera_nx, camera_ny, screen_w, screen_h):
    """Return the camera origin plus the source rect and dest rect that are actually on screen.

    Scaling that crop, instead of the whole map, keeps a zoomed-in battle map at roughly
    screen resolution. draw_x/draw_y stay in the same space the markers already use.
    """
    draw_x = screen_w / 2 - (camera_nx * orig_w) * zoom
    draw_y = screen_h / 2 - (camera_ny * orig_h) * zoom
    if orig_w <= 0 or orig_h <= 0 or zoom <= 0:
        return draw_x, draw_y, None, (0, 0), (0, 0)

    sx0 = (0 - draw_x) / zoom
    sy0 = (0 - draw_y) / zoom
    sx1 = (screen_w - draw_x) / zoom
    sy1 = (screen_h - draw_y) / zoom
    ix0 = max(0, math.floor(sx0))
    iy0 = max(0, math.floor(sy0))
    ix1 = min(orig_w, math.ceil(sx1))
    iy1 = min(orig_h, math.ceil(sy1))
    if ix1 <= ix0 or iy1 <= iy0:
        return draw_x, draw_y, None, (0, 0), (0, 0)

    src_rect = pygame.Rect(int(ix0), int(iy0), int(ix1 - ix0), int(iy1 - iy0))
    dest_pos = (draw_x + ix0 * zoom, draw_y + iy0 * zoom)
    dest_size = (
        max(1, int(math.ceil((ix1 - ix0) * zoom - 1e-9))),
        max(1, int(math.ceil((iy1 - iy0) * zoom - 1e-9))),
    )
    return draw_x, draw_y, src_rect, dest_pos, dest_size


class SurfaceScaleCache:
    """Reuse a smoothscale result until the crop, zoom, or source pixels change."""

    def __init__(self):
        self._key = None
        self.surface = None

    def clear(self):
        self._key = None
        self.surface = None

    def scale(self, source, src_rect, dest_size, token):
        key = (
            id(source), token,
            src_rect.x, src_rect.y, src_rect.w, src_rect.h,
            dest_size[0], dest_size[1],
        )
        if key != self._key:
            self.surface = pygame.transform.smoothscale(source.subsurface(src_rect), dest_size)
            self._key = key
        return self.surface


def blit_map_and_fog(image, fog, view, bg_cache, fog_cache, image_token, fog_token):
    """Scale the visible map and fog. Returns (bg, fog, dest) or None if there is nothing to draw."""
    _draw_x, _draw_y, src_rect, dest_pos, dest_size = view
    if src_rect is None:
        return None
    bg = bg_cache.scale(image, src_rect, dest_size, image_token)
    fg = fog_cache.scale(fog, src_rect, dest_size, fog_token)
    return bg, fg, dest_pos


def consume_full_reveal(mask, armed):
    """Clear the audience fog once.

    The flag has to drop after that. Leaving it armed refills the mask every frame,
    which erases later brush strokes and makes Reset unable to bring the fog back.
    Returns (flag, did_clear).
    """
    if not armed:
        return False, False
    mask.fill((0, 0, 0, 0))
    return False, True


def sync_reveal_count(prev_len, current_len):
    """Follow a cleared stroke list so the next stroke is not skipped."""
    if current_len < prev_len:
        return current_len
    return prev_len


def draw_shape(surface, shape_type, center, base_size_pixels, rotation, color, width):
    """Draw one spell shape. shape_type: 0 circle, 1 square, 2 cone, 3 line."""
    if base_size_pixels < 1:
        return
    angle_rad = math.radians(rotation)
    if shape_type == 0:
        radius = int(base_size_pixels / 2)
        if radius > 0:
            pygame.draw.circle(surface, color, center, radius, width)
    elif shape_type == 1:
        side = max(1, int(base_size_pixels))
        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.rect(surf, color, (0, 0, side, side), width)
        rotated = pygame.transform.rotate(surf, rotation)
        surface.blit(rotated, rotated.get_rect(center=center))
    elif shape_type == 2:
        length = base_size_pixels * 1.4
        apex_angle = math.radians(30)
        left_angle = angle_rad - apex_angle
        right_angle = angle_rad + apex_angle
        apex = center
        left = (apex[0] + length * math.cos(left_angle), apex[1] + length * math.sin(left_angle))
        right = (apex[0] + length * math.cos(right_angle), apex[1] + length * math.sin(right_angle))
        pygame.draw.polygon(surface, color, [apex, left, right], width)
    elif shape_type == 3:
        w = max(1, int(base_size_pixels * 1.8))
        h = max(1, int(base_size_pixels * 0.45))
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, color, (0, 0, w, h), width)
        rotated = pygame.transform.rotate(surf, rotation)
        surface.blit(rotated, rotated.get_rect(center=center))


def draw_shared_shapes(surface, shapes, draw_x, draw_y, orig_w, orig_h, zoom, color=(200, 0, 0), width=3):
    diag = max(orig_w, orig_h) * zoom
    for sh in shapes:
        pos = (
            int(draw_x + sh['nx'] * orig_w * zoom),
            int(draw_y + sh['ny'] * orig_h * zoom),
        )
        draw_shape(
            surface, sh['type'], pos, sh['size'] * diag,
            sh.get('rotation', 0.0), color, width,
        )


def control_window(initial_image_path, shared_revealed, shared_running, shared_image_path,
                   display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset,
                   shared_markers, shared_current_condition_idx, shared_current_marker_size,
                   shared_mouse_map_nx, shared_mouse_map_ny, shared_current_shape_type,
                   shared_shapes, shared_current_rotation, shared_current_shape_size,
                   shared_full_reveal):
    
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
    show_help = False
    
    conditions = [
        "Blinded", "Charmed", "Deafened", "Exhausted", "Frightened",
        "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
        "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious"
    ]
    
    marker_colors = [
        (0, 0, 0), (255, 192, 203), (128, 128, 128), (169, 169, 169), (255, 255, 0),
        (0, 128, 0), (139, 0, 0), (173, 216, 230), (0, 0, 255), (112, 128, 144),
        (0, 255, 0), (165, 42, 42), (255, 165, 0), (218, 165, 32), (75, 0, 130)
    ]
    
    marker_sizes = [12, 24, 40]
    
    shapes = ["Circle", "Square", "Cone", "Line/Rect"]
    
    font = pygame.font.SysFont(None, 36)
    menu_font = pygame.font.SysFont(None, 24)
    
    # Menu geometry
    MENU_HEIGHT = 160
    menu_area = pygame.Rect(0, screen_h - MENU_HEIGHT, screen_w, MENU_HEIGHT)
    menu_bg = pygame.Surface((screen_w, MENU_HEIGHT), pygame.SRCALPHA)
    menu_bg.fill((30, 30, 50, 180))
    
    display_help_key = font.render("Press H for help", True, (255, 255, 180))
    status_msg = None
    status_timer = 0
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    current_drag_mode = None
    prev_pos = None
    
    min_zoom_mult = 0.1
    max_zoom_mult = 20.0
    bg_cache = SurfaceScaleCache()
    fog_cache = SurfaceScaleCache()
    image_token = 0
    fog_token = 0
    
    while shared_running.value:
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shared_running.value = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shared_running.value = False
                if event.key == pygame.K_h:
                    show_help = not show_help
                
                # Hotkeys
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
                if event.key == pygame.K_o and (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]):
                    shared_revealed[:] = []
                    shared_full_reveal.value = True
                    status_msg = font.render("Full reveal sent to audience", True, (100, 255, 100))
                    status_timer = 120
                if event.key == pygame.K_r:
                    if event.mod & pygame.KMOD_CTRL:
                        shared_current_rotation.value = 0.0
                        status_msg = font.render("Rotation reset", True, (180, 220, 255))
                        status_timer = 90
                    else:
                        shared_revealed[:] = []
                        shared_markers[:] = []
                        shared_shapes[:] = []
                        shared_fog_reset.value += 1
                        status_msg = font.render("Everything reset", True, (220, 100, 100))
                        status_timer = 120
                if event.key == pygame.K_m:
                    if shared_markers:
                        shared_markers.pop()
                        status_msg = font.render("Last marker removed", True, (220, 180, 60))
                        status_timer = 120
                
                # Condition hotkeys (1-9,0,a,s,d,g)
                if pygame.K_1 <= event.key <= pygame.K_9:
                    idx = event.key - pygame.K_1
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key == pygame.K_0:
                    shared_current_condition_idx.value = 9
                    status_msg = font.render(f"Condition: {conditions[9]}", True, (100, 255, 100))
                    status_timer = 120
                elif event.key in (pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_g):
                    mapping = {pygame.K_a:10, pygame.K_s:11, pygame.K_d:12, pygame.K_g:14}
                    idx = mapping[event.key]
                    shared_current_condition_idx.value = idx
                    status_msg = font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                    status_timer = 120
                
                # Q/E rotate a selected shape. Otherwise Q/W/E pick the marker size.
                shape_selected = shared_current_shape_type.value != -1
                if event.key == pygame.K_q and shape_selected:
                    shared_current_rotation.value = (shared_current_rotation.value - 15) % 360
                    status_msg = font.render(f"Rotation: {int(shared_current_rotation.value)}°", True, (180, 220, 255))
                    status_timer = 90
                elif event.key == pygame.K_e and shape_selected:
                    shared_current_rotation.value = (shared_current_rotation.value + 15) % 360
                    status_msg = font.render(f"Rotation: {int(shared_current_rotation.value)}°", True, (180, 220, 255))
                    status_timer = 90
                elif event.key in (pygame.K_q, pygame.K_w, pygame.K_e):
                    idx = {pygame.K_q:0, pygame.K_w:1, pygame.K_e:2}[event.key]
                    shared_current_marker_size.value = idx
                    status_msg = font.render(f"Size: {['Small','Medium','Large'][idx]}", True, (100, 255, 100))
                    status_timer = 120
                
                # Deselect shape
                if event.key == pygame.K_SPACE:
                    shared_current_shape_type.value = -1
                    status_msg = font.render("Shape deselected", True, (220, 180, 100))
                    status_timer = 90
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                
                if menu_area.collidepoint((mx, my)):
                    rel_y = my - menu_area.top
                    
                    # Conditions
                    if rel_y < 80:
                        col_w = screen_w // 5
                        row_h = 40
                        col = mx // col_w
                        row = rel_y // row_h
                        idx = row * 5 + col
                        if 0 <= idx < len(conditions):
                            shared_current_condition_idx.value = idx
                            status_msg = menu_font.render(f"Condition: {conditions[idx]}", True, (100, 255, 100))
                            status_timer = 90
                    
                    # Shapes
                    elif 80 <= rel_y < 120:
                        shape_w = screen_w // len(shapes)
                        idx = mx // shape_w
                        if 0 <= idx < len(shapes):
                            new_val = idx if shared_current_shape_type.value != idx else -1
                            shared_current_shape_type.value = new_val
                            status = f"Shape: {shapes[idx]}" if new_val != -1 else "Shape deselected"
                            status_msg = menu_font.render(status, True, (180, 220, 255))
                            status_timer = 90
                    
                    # Marker sizes
                    elif rel_y >= 120:
                        size_start_x = screen_w - 360
                        if mx >= size_start_x:
                            button_w = 100
                            if mx < size_start_x + button_w:
                                shared_current_marker_size.value = 0
                                status_msg = menu_font.render("Size: Small", True, (100, 255, 100))
                            elif mx < size_start_x + button_w * 2:
                                shared_current_marker_size.value = 1
                                status_msg = menu_font.render("Size: Medium", True, (100, 255, 100))
                            else:
                                shared_current_marker_size.value = 2
                                status_msg = menu_font.render("Size: Large", True, (100, 255, 100))
                            status_timer = 90
                    continue
                
                # Map interaction
                if event.button == 1:
                    shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                    current_drag_mode = 'pan' if shift_pressed else 'reveal'
                    prev_pos = event.pos
                
                elif event.button == 3:
                    pos = event.pos
                    current_zoom = base_zoom * shared_zoom_multiplier.value
                    draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                    draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                    map_x = (pos[0] - draw_x) / current_zoom
                    map_y = (pos[1] - draw_y) / current_zoom
                    nx = map_x / orig_w
                    ny = map_y / orig_h
                    
                    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                        # Remove nearest marker (simple nearest for now)
                        if shared_markers:
                            closest_idx = None
                            closest_dist = float('inf')
                            for i, (mnx, mny, mnr, _) in enumerate(shared_markers):
                                dist = math.hypot(nx - mnx, ny - mny)
                                if dist < closest_dist:
                                    closest_dist = dist
                                    closest_idx = i
                            if closest_idx is not None and closest_dist < 0.05:
                                del shared_markers[closest_idx]
                                status_msg = font.render("Marker removed", True, (220, 100, 100))
                                status_timer = 120
                    else:
                        shape_idx = shared_current_shape_type.value
                        if shape_idx != -1:
                            shared_shapes.append({
                                'type': shape_idx,
                                'nx': nx,
                                'ny': ny,
                                'size': shared_current_shape_size.value,
                                'rotation': shared_current_rotation.value,
                            })
                            shared_current_shape_type.value = -1
                            
                            status_msg = font.render(
                                f"{shapes[shape_idx]} placed "
                                f"({int(shared_current_rotation.value)}°, "
                                f"size {int(shared_current_shape_size.value*100)}%)",
                                True, (180, 220, 255)
                            )
                            status_timer = 120
                        else:
                            base_r = marker_sizes[shared_current_marker_size.value]
                            nr = base_r / current_zoom / max(orig_w, orig_h)
                            shared_markers.append((nx, ny, nr, shared_current_condition_idx.value))
            
            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    current_drag_mode = None
                    prev_pos = None
            
            if event.type == pygame.MOUSEWHEEL:
                mods = pygame.key.get_mods()
                delta = event.y
                
                if shared_current_shape_type.value != -1:
                    if mods & pygame.KMOD_SHIFT:
                        shared_current_rotation.value = (shared_current_rotation.value + delta * 5) % 360
                    else:
                        size_change = delta * 0.008
                        new_size = shared_current_shape_size.value + size_change
                        shared_current_shape_size.value = max(0.01, min(0.40, new_size))
                        status_msg = font.render(f"Shape size: {int(shared_current_shape_size.value * 100)}%", True, (180, 220, 255))
                        status_timer = 60
                else:
                    factor = 1.1 ** delta
                    new_mult = shared_zoom_multiplier.value * factor
                    new_mult = max(min_zoom_mult, min(max_zoom_mult, new_mult))
                    shared_zoom_multiplier.value = new_mult
        
        # Image reload
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
                shared_shapes[:] = []
                shared_zoom_multiplier.value = 1.0
                shared_camera_nx.value = 0.5
                shared_camera_ny.value = 0.5
                shared_fog_reset.value += 1
                prev_len = 0
                local_fog_reset = shared_fog_reset.value
                bg_cache.clear()
                fog_cache.clear()
                image_token += 1
                fog_token += 1
                status_msg = font.render("New map loaded", True, (100, 255, 100))
                status_timer = 180
            except Exception as e:
                print("Failed to load new image:", e)
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            fog_orig.fill((20, 20, 60, 180))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
            fog_token += 1
        
        current_len = len(shared_revealed)
        prev_len = sync_reveal_count(prev_len, current_len)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = int(nx * orig_w)
                y = int(ny * orig_h)
                r = int(nr * max(orig_w, orig_h))
                pygame.draw.circle(fog_orig, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
            fog_token += 1
        
        # Dragging (reveal / pan)
        mouse_pressed = pygame.mouse.get_pressed()[0]
        if mouse_pressed and current_drag_mode:
            pos = pygame.mouse.get_pos()
            if prev_pos is not None:
                draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                
                if current_drag_mode == 'pan':
                    delta_x = pos[0] - prev_pos[0]
                    delta_y = pos[1] - prev_pos[1]
                    shared_camera_nx.value -= delta_x / (current_zoom * orig_w)
                    shared_camera_ny.value -= delta_y / (current_zoom * orig_h)
                    shared_camera_nx.value = max(0, min(1, shared_camera_nx.value))
                    shared_camera_ny.value = max(0, min(1, shared_camera_ny.value))
                elif current_drag_mode == 'reveal':
                    map_x = (pos[0] - draw_x) / current_zoom
                    map_y = (pos[1] - draw_y) / current_zoom
                    map_r = reveal_radius / current_zoom
                    nx = map_x / orig_w
                    ny = map_y / orig_h
                    nr = map_r / max(orig_w, orig_h)
                    shared_revealed.append((nx, ny, nr))
                    pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(map_x), int(map_y)), int(map_r))
                    fog_token += 1
            prev_pos = pos
        
        view = map_view(
            orig_w, orig_h, current_zoom,
            shared_camera_nx.value, shared_camera_ny.value,
            screen_w, screen_h,
        )
        draw_x, draw_y = view[0], view[1]

        # Shared mouse position for audience cursor mirror
        mx, my = pygame.mouse.get_pos()
        if draw_x <= mx < draw_x + orig_w * current_zoom and draw_y <= my < draw_y + orig_h * current_zoom:
            map_x = (mx - draw_x) / current_zoom
            map_y = (my - draw_y) / current_zoom
            shared_mouse_map_nx.value = map_x / orig_w
            shared_mouse_map_ny.value = map_y / orig_h
        else:
            shared_mouse_map_nx.value = -1.0
            shared_mouse_map_ny.value = -1.0
        
        # Rendering. The scaled surfaces are cached until the crop, zoom, or fog pixels change.
        screen.fill((0, 0, 0))
        try:
            layers = blit_map_and_fog(image, fog_orig, view, bg_cache, fog_cache, image_token, fog_token)
        except (ValueError, pygame.error) as e:
            print("Zoom scale error:", e)
            pygame.display.flip()
            clock.tick(60)
            continue
        if layers is not None:
            bg_scaled, fog_scaled, dest_pos = layers
            screen.blit(bg_scaled, dest_pos)
            screen.blit(fog_scaled, dest_pos)
        
        # Markers
        for nx, ny, nr, condition_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (int(draw_x + x), int(draw_y + y))
            color = marker_colors[condition_idx]
            width = max(2, int(r / 10))
            pygame.draw.circle(screen, color, pos, r, width)
            text_radius = r - width * 2
            font_size = max(10, int(r / (len(conditions[condition_idx]) * 0.4)))
            draw_circular_text(screen, conditions[condition_idx], pos, text_radius, (0,0,0), font_size)
        
        draw_shared_shapes(screen, shared_shapes, draw_x, draw_y, orig_w, orig_h, current_zoom)
        
        # Shape preview near mouse
        shape_idx = shared_current_shape_type.value
        if shape_idx != -1 and not mouse_pressed and not menu_area.collidepoint(pygame.mouse.get_pos()):
            mx, my = pygame.mouse.get_pos()
            preview_pixels = shared_current_shape_size.value * max(orig_w, orig_h) * current_zoom
            draw_shape(
                screen, shape_idx, (mx, my), preview_pixels,
                shared_current_rotation.value, (200, 220, 255, 140), 3,
            )
        
        # Brush preview (when no shape selected)
        if not mouse_pressed and shape_idx == -1:
            mx, my = pygame.mouse.get_pos()
            pygame.draw.circle(screen, (255, 255, 180, 80), (mx, my), reveal_radius, 2)
        
        # Menu
        screen.blit(menu_bg, menu_area.topleft)
        
        # Conditions
        col_w = screen_w // 5
        for i, cond in enumerate(conditions):
            col = i % 5
            row = i // 5
            x = col * col_w + 10
            y = menu_area.top + row * 40 + 5
            rect = pygame.Rect(x, y, col_w - 20, 35)
            colr = marker_colors[i] + (255,) if len(marker_colors[i]) == 3 else marker_colors[i]
            pygame.draw.rect(screen, colr, rect, border_radius=5)
            if i == shared_current_condition_idx.value:
                pygame.draw.rect(screen, (255, 255, 180), rect, 3, border_radius=5)
            text_color = (0,0,0) if sum(colr[:3]) > 380 else (255,255,255)
            txt = menu_font.render(cond, True, text_color)
            screen.blit(txt, (rect.x + 8, rect.y + 8))
        
        # Shapes
        shape_w = screen_w // len(shapes)
        for i, shape in enumerate(shapes):
            x = i * shape_w + 10
            y = menu_area.top + 85
            rect = pygame.Rect(x, y, shape_w - 20, 35)
            col = (120, 200, 120) if i == shared_current_shape_type.value else (90, 90, 130)
            pygame.draw.rect(screen, col, rect, border_radius=6)
            txt = menu_font.render(shape, True, (255,255,255))
            screen.blit(txt, (rect.x + 12, rect.y + 8))
        
        # Marker sizes
        size_start_x = screen_w - 360
        size_labels = ["Small", "Medium", "Large"]
        for i, label in enumerate(size_labels):
            x = size_start_x + i * 110
            rect = pygame.Rect(x, menu_area.top + 125, 100, 32)
            col = (100, 180, 255) if i == shared_current_marker_size.value else (70, 70, 110)
            pygame.draw.rect(screen, col, rect, border_radius=6)
            txt = menu_font.render(label, True, (240,240,240))
            screen.blit(txt, (rect.x + 12, rect.y + 6))
        
        # Status & help
        screen.blit(display_help_key, (20, 20))
        if status_timer > 0:
            screen.blit(status_msg, (20, 70))
            status_timer -= 1
        
        if show_help:
            help_lines = [
                "Left click / drag: reveal fog",
                "Shift + Left drag: pan map",
                "Right click: place marker or shape",
                "Shift + Right click: remove nearest marker",
                "Mouse wheel: zoom map / resize shape",
                "Shift + wheel: rotate shape",
                "Q / E: rotate selected shape 15°",
                "Ctrl + R: reset rotation",
                "SPACE: deselect shape",
                "F: load new map",
                "R: reset everything",
                "M: remove last marker",
                "1-9,0,A,S,D,G: select condition",
                "Q / W / E: marker size (no shape selected)",
                "H: toggle help",
                "ESC: quit"
            ]
            for i, line in enumerate(help_lines):
                img = font.render(line, True, (220, 220, 160))
                screen.blit(img, (20, 120 + i * 38))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


def audience_window(initial_image_path, shared_revealed, shared_running, shared_image_path,
                    display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset,
                    shared_markers, shared_current_condition_idx, shared_current_marker_size,
                    shared_mouse_map_nx, shared_mouse_map_ny, shared_current_shape_type,
                    shared_shapes, shared_current_rotation, shared_current_shape_size,
                    shared_full_reveal):
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
        "Blinded", "Charmed", "Deafened", "Exhausted", "Frightened",
        "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
        "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious"
    ]
    
    marker_colors = [
        (0, 0, 0), (255, 192, 203), (128, 128, 128), (169, 169, 169), (255, 255, 0),
        (0, 128, 0), (139, 0, 0), (173, 216, 230), (0, 0, 255), (112, 128, 144),
        (0, 255, 0), (165, 42, 42), (255, 165, 0), (218, 165, 32), (75, 0, 130)
    ]
    
    marker_sizes = [12, 24, 40]
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    clock = pygame.time.Clock()
    bg_cache = SurfaceScaleCache()
    fog_cache = SurfaceScaleCache()
    image_token = 0
    fog_token = 0
    
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
                bg_cache.clear()
                fog_cache.clear()
                image_token += 1
                fog_token += 1
            except:
                pass
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            mask_orig.fill((0, 0, 0, 255))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
            fog_token += 1
            
        if shared_full_reveal.value:
            shared_full_reveal.value, _cleared = consume_full_reveal(mask_orig, True)
            prev_len = 0
            fog_token += 1

        current_len = len(shared_revealed)
        prev_len = sync_reveal_count(prev_len, current_len)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                if i >= len(shared_revealed):
                    break
                nx, ny, nr = shared_revealed[i]
                x = int(nx * orig_w)
                y = int(ny * orig_h)
                r = int(nr * max(orig_w, orig_h))
                pygame.draw.circle(mask_orig, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
            fog_token += 1
        
        view = map_view(
            orig_w, orig_h, current_zoom,
            shared_camera_nx.value, shared_camera_ny.value,
            screen_w, screen_h,
        )
        draw_x, draw_y = view[0], view[1]
        
        screen.fill((0, 0, 0))
        try:
            layers = blit_map_and_fog(image, mask_orig, view, bg_cache, fog_cache, image_token, fog_token)
        except (ValueError, pygame.error) as e:
            print("Zoom scale error (audience):", e)
            pygame.display.flip()
            clock.tick(60)
            continue
        if layers is not None:
            bg_scaled, mask_scaled, dest_pos = layers
            screen.blit(bg_scaled, dest_pos)
            screen.blit(mask_scaled, dest_pos)
        
        # DM mouse indicator
        if shared_mouse_map_nx.value >= 0:
            mx = shared_mouse_map_nx.value * orig_w * current_zoom
            my = shared_mouse_map_ny.value * orig_h * current_zoom
            ix = int(draw_x + mx)
            iy = int(draw_y + my)
            pygame.draw.circle(screen, (255, 60, 60, 140), (ix, iy), 16, 4)
            pygame.draw.line(screen, (255, 80, 80, 220), (ix - 28, iy), (ix + 28, iy), 5)
            pygame.draw.line(screen, (255, 80, 80, 220), (ix, iy - 28), (ix, iy + 28), 5)
        
        # Markers
        for nx, ny, nr, condition_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (int(draw_x + x), int(draw_y + y))
            color = marker_colors[condition_idx]
            width = max(2, int(r / 10))
            pygame.draw.circle(screen, color, pos, r, width)
            text_radius = r - width * 2
            font_size = max(10, int(r / (len(conditions[condition_idx]) * 0.4)))
            draw_circular_text(screen, conditions[condition_idx], pos, text_radius, (0,0,0), font_size)
        
        draw_shared_shapes(screen, shared_shapes, draw_x, draw_y, orig_w, orig_h, current_zoom)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()