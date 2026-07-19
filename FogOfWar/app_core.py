from __future__ import annotations
import pygame
import math
import os
import json
import tkinter as tk
from PIL import Image, ImageSequence
from collections import deque


def load_gif_frames(path):
    try:
        img = Image.open(path)
        if not img.format == 'GIF' or not img.is_animated:
            # fallback to static
            return [pygame.image.load(path).convert_alpha()], [100]

        frames = []
        durations = []

        for frame in ImageSequence.Iterator(img):
            rgba = frame.convert("RGBA")
            # Convert PIL → Pygame surface
            pg_surf = pygame.image.fromstring(
                rgba.tobytes(), rgba.size, rgba.mode
            ).convert_alpha()
            frames.append(pg_surf)
            durations.append(frame.info.get('duration', 100))

        return frames, durations
    except Exception as e:
        print(f"GIF load error: {e}")
        return [], []


def get_current_gif_frame(animated_gifs, path, current_time_ms):
    if path not in animated_gifs:
        return None
    anim = animated_gifs[path]
    if not anim['frames']:
        return None
        
    elapsed = current_time_ms - anim['start_ms']
    total = anim['total_dur']
    if total == 0:
        total = 100 * len(anim['frames'])
        
    pos = elapsed % total
    cumulative = 0
    for i, dur in enumerate(anim['durations']):
        if pos < cumulative + dur:
            return anim['frames'][i]
        cumulative += dur
    return anim['frames'][0]   # fallback


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
                   shared_mouse_map_nx, shared_mouse_map_ny, shared_current_shape_type,
                   shared_shapes, shared_current_rotation, shared_current_shape_size,
                   shared_full_reveal, shared_animated_effects):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Control Monitor (Reveal Fog)")
    
    print(f"current image path: {initial_image_path}")
    current_path = initial_image_path
    animated_gifs = {}  # path → {'frames': list[Surface], 'durations': list[int], 'total_dur': int, 'start_time': int}

    if current_path.lower().endswith('.gif'):
        frames, durations = load_gif_frames(current_path)
        if frames:
            animated_gifs[current_path] = {
                'frames': frames,
                'durations': durations,
                'total_dur': sum(durations),
                'start_ms': pygame.time.get_ticks()
            }

    image = pygame.image.load(current_path).convert()
    orig_w, orig_h = image.get_size()
    base_zoom = min(screen_w / orig_w, screen_h / orig_h)
    fog_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
    fog_orig.fill((20, 20, 60, 180))
    
    clock = pygame.time.Clock()
    reveal_radius = 60
    base_reveal_screen_px = 60 
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
    
    marker_sizes = [16, 31, 52]
    
    shapes = ["Circle", "Square", "Cone", "Line/Rect"]
    
    font = pygame.font.SysFont(None, 36)
    menu_font = pygame.font.SysFont(None, 24)
    
    # -------------------------------- Menu geometry
    MENU_HEIGHT = 160
    menu_area = pygame.Rect(0, screen_h - MENU_HEIGHT, screen_w, MENU_HEIGHT)
    menu_bg = pygame.Surface((screen_w, MENU_HEIGHT), pygame.SRCALPHA)
    menu_bg.fill((30, 30, 50, 180))
    
    # -------------------------------- Save button rect (bottom left)
    save_button_rect = pygame.Rect(20, screen_h - 40, 120, 30)
    back_button_rect = pygame.Rect(160, screen_h - 40, 100, 30)  # Back button

    display_help_key = font.render("Press H for help", True, (255, 255, 180))
    status_msg = None
    status_timer = 0
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    current_drag_mode = None
    prev_pos = None
    
    min_zoom_mult = 0.1
    max_zoom_mult = 20.0

    # ====================== PERSISTENT BACKSTACK ======================
    MAX_BACKSTACK = 5
    backstack = deque(maxlen=MAX_BACKSTACK)

    def capture_current_state():
        """Capture a complete snapshot for history / saving."""
        return {
            'image_path': current_path,
            'zoom_multiplier': shared_zoom_multiplier.value,
            'camera_nx': shared_camera_nx.value,
            'camera_ny': shared_camera_ny.value,
            'revealed': list(shared_revealed),
            'markers': list(shared_markers),
            'shapes': [dict(s) for s in shared_shapes],
            'current_rotation': shared_current_rotation.value,
            'current_shape_size': shared_current_shape_size.value,
        }
    # ================================================================

    while shared_running.value:
        
        if shared_image_path[0] != current_path:
            try:
                current_path = shared_image_path[0]
                image = pygame.image.load(current_path).convert()
                animated_gifs.clear()  # remove old animation
                if current_path.lower().endswith('.gif'):
                    frames, durations = load_gif_frames(current_path)
                    if frames:
                        animated_gifs[current_path] = {
                            'frames': frames,
                            'durations': durations,
                            'total_dur': sum(durations),
                            'start_ms': pygame.time.get_ticks()
                        }
                orig_w, orig_h = image.get_size()
                base_zoom = min(screen_w / orig_w, screen_h / orig_h)
                fog_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
                fog_orig.fill((20, 20, 60, 180))
                prev_len = 0
                local_fog_reset = shared_fog_reset.value
                print(f"Control: loaded new map {current_path} — new base_zoom = {base_zoom:.4f}")
            except Exception as e:
                print("Control image load failed:", e)

        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shared_running.value = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shared_running.value = False
                if event.key == pygame.K_h:
                    show_help = not show_help
                
                # -------------------------------- Hotkeys
                if event.key == pygame.K_f:
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    filename = filedialog.askopenfilename(
                        title="Select Map Image or State"
                    )
                    root.destroy()
                    if filename:
                        if filename.endswith('.dndstate'):
                            # Auto-save current state to backstack before loading new state
                            if current_path:
                                state = capture_current_state()
                                backstack.append(state)

                            try:
                                with open(filename, 'r') as f:
                                    state = json.load(f)
                                shared_image_path[:] = [state['image_path']]
                                shared_zoom_multiplier.value = state['zoom_multiplier']
                                shared_camera_nx.value = state['camera_nx']
                                shared_camera_ny.value = state['camera_ny']
                                shared_revealed[:] = state.get('revealed', [])
                                shared_markers[:] = state.get('markers', [])
                                shared_shapes[:] = state.get('shapes', [])
                                shared_current_rotation.value = state.get('current_rotation', 0.0)
                                shared_current_shape_size.value = state.get('current_shape_size', 0.08)

                                # Restore persistent backstack
                                loaded_backstack = state.get('backstack', [])
                                backstack.clear()
                                for item in loaded_backstack[-MAX_BACKSTACK:]:
                                    if isinstance(item, dict):
                                        backstack.append(item)

                                shared_fog_reset.value += 1
                                status_msg = font.render("State + history loaded", True, (100, 255, 100))
                            except Exception as e:
                                status_msg = font.render(f"Load failed: {str(e)}", True, (220, 100, 100))
                            status_timer = 180
                        else:
                            # Regular image load - auto-save current to backstack
                            if current_path and current_path != filename:
                                state = capture_current_state()
                                backstack.append(state)

                            shared_image_path[:] = [filename]
                            shared_revealed[:] = []
                            shared_markers[:] = []
                            shared_shapes[:] = []
                            shared_fog_reset.value += 1
                            status_msg = font.render("New map loaded", True, (100, 255, 100))
                            status_timer = 180
                            image = pygame.image.load(shared_image_path[0]).convert()
                            orig_w, orig_h = image.get_size()
                            base_zoom = min(screen_w / orig_w, screen_h / orig_h)

                if event.key == pygame.K_r:
                    shared_revealed[:] = []
                    shared_markers[:] = []
                    shared_shapes[:] = []
                    shared_fog_reset.value += 1
                    status_msg = font.render("Everything reset", True, (220, 100, 100))
                    status_timer = 120
                if event.key == pygame.K_o and (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]):
                    shared_full_reveal.value = True
                    shared_revealed[:] = []
                    status_msg = font.render("Full reveal sent to audience", True, (100, 255, 100))
                    status_timer = 120
                if event.key == pygame.K_m:
                    if shared_markers:
                        shared_markers.pop()
                        status_msg = font.render("Last marker removed", True, (220, 180, 60))
                        status_timer = 120
                
                # Condition hotkeys
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
                
                # Marker size hotkeys
                if event.key in (pygame.K_q, pygame.K_w, pygame.K_e):
                    idx = {pygame.K_q:0, pygame.K_w:1, pygame.K_e:2}[event.key]
                    shared_current_marker_size.value = idx
                    status_msg = font.render(f"Size: {['Small','Medium','Large'][idx]}", True, (100, 255, 100))
                    status_timer = 120
                
                # Shape rotation
                if shared_current_shape_type.value != -1:
                    if event.key == pygame.K_q:
                        shared_current_rotation.value = (shared_current_rotation.value - 15) % 360
                        status_msg = font.render(f"Rotation: {int(shared_current_rotation.value)}°", True, (180, 220, 255))
                        status_timer = 90
                    elif event.key == pygame.K_e:
                        shared_current_rotation.value = (shared_current_rotation.value + 15) % 360
                        status_msg = font.render(f"Rotation: {int(shared_current_rotation.value)}°", True, (180, 220, 255))
                        status_timer = 90
                    elif event.key == pygame.K_r and (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]):
                        shared_current_rotation.value = 0.0
                        status_msg = font.render("Rotation reset to 0°", True, (220, 180, 100))
                        status_timer = 90
                
                if event.key == pygame.K_SPACE:
                    shared_current_shape_type.value = -1
                    status_msg = font.render("Shape deselected", True, (220, 180, 100))
                    status_timer = 90
                
                # Ctrl + B → Back to previous map
                if event.key == pygame.K_b and (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]):
                    if backstack:
                        prev_state = backstack.pop()
                        shared_image_path[:] = [prev_state['image_path']]
                        shared_zoom_multiplier.value = prev_state['zoom_multiplier']
                        shared_camera_nx.value = prev_state['camera_nx']
                        shared_camera_ny.value = prev_state['camera_ny']
                        shared_revealed[:] = prev_state['revealed']
                        shared_markers[:] = prev_state['markers']
                        shared_shapes[:] = prev_state['shapes']
                        shared_current_rotation.value = prev_state.get('current_rotation', 0.0)
                        shared_current_shape_size.value = prev_state.get('current_shape_size', 0.08)
                        shared_fog_reset.value += 1
                        status_msg = font.render("Returned to previous map", True, (100, 255, 100))
                        status_timer = 120
                    else:
                        status_msg = font.render("No previous map in history", True, (255, 200, 100))
                        status_timer = 90

                # Ctrl + S → Save with backstack
                if event.key == pygame.K_s and (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]):
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    filename = filedialog.asksaveasfilename(
                        title="Save D&D State",
                        defaultextension=".dndstate",
                        filetypes=[("D&D State", "*.dndstate")]
                    )
                    root.destroy()
                    if filename:
                        try:
                            state = {
                                'image_path': shared_image_path[0],
                                'zoom_multiplier': shared_zoom_multiplier.value,
                                'camera_nx': shared_camera_nx.value,
                                'camera_ny': shared_camera_ny.value,
                                'revealed': shared_revealed[:],
                                'markers': shared_markers[:],
                                'shapes': shared_shapes[:],
                                'current_rotation': shared_current_rotation.value,
                                'current_shape_size': shared_current_shape_size.value,
                                'backstack': list(backstack),
                            }
                            with open(filename, 'w') as f:
                                json.dump(state, f, indent=4)
                            status_msg = font.render("State saved (with history)", True, (100, 255, 100))
                        except Exception as e:
                            status_msg = font.render(f"Save failed: {str(e)}", True, (220, 100, 100))
                        status_timer = 180
            
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
                    elif rel_y >= 120 and rel_y < 160:
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
                    
                    # Save button
                    if save_button_rect.collidepoint(mx, my):
                        from tkinter import filedialog
                        root = tk.Tk()
                        root.withdraw()
                        filename = filedialog.asksaveasfilename(
                            title="Save D&D State",
                            defaultextension=".dndstate",
                            filetypes=[("D&D State", "*.dndstate")]
                        )
                        root.destroy()
                        if filename:
                            try:
                                state = {
                                    'image_path': shared_image_path[0],
                                    'zoom_multiplier': shared_zoom_multiplier.value,
                                    'camera_nx': shared_camera_nx.value,
                                    'camera_ny': shared_camera_ny.value,
                                    'revealed': shared_revealed[:],
                                    'markers': shared_markers[:],
                                    'shapes': shared_shapes[:],
                                    'current_rotation': shared_current_rotation.value,
                                    'current_shape_size': shared_current_shape_size.value,
                                    'backstack': list(backstack),
                                }
                                with open(filename, 'w') as f:
                                    json.dump(state, f, indent=4)
                                status_msg = font.render("State saved (with history)", True, (100, 255, 100))
                            except Exception as e:
                                status_msg = font.render(f"Save failed: {str(e)}", True, (220, 100, 100))
                            status_timer = 180
                    
                    # Back button click
                    if back_button_rect.collidepoint(mx, my):
                        if backstack:
                            prev_state = backstack.pop()
                            shared_image_path[:] = [prev_state['image_path']]
                            shared_zoom_multiplier.value = prev_state['zoom_multiplier']
                            shared_camera_nx.value = prev_state['camera_nx']
                            shared_camera_ny.value = prev_state['camera_ny']
                            shared_revealed[:] = prev_state['revealed']
                            shared_markers[:] = prev_state['markers']
                            shared_shapes[:] = prev_state['shapes']
                            shared_current_rotation.value = prev_state.get('current_rotation', 0.0)
                            shared_current_shape_size.value = prev_state.get('current_shape_size', 0.08)
                            shared_fog_reset.value += 1
                            status_msg = font.render("Returned to previous map", True, (100, 255, 100))
                            status_timer = 120
                        else:
                            status_msg = font.render("No previous map in history", True, (255, 200, 100))
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
        
        # Image/state reload
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            fog_orig.fill((20, 20, 60, 180))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = int(nx * orig_w)
                y = int(ny * orig_h)
                r = int(nr * max(orig_w, orig_h))
                pygame.draw.circle(fog_orig, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
        
        # Dragging
        mouse_pressed = pygame.mouse.get_pressed()[0]
        if mouse_pressed and current_drag_mode:
            pos = pygame.mouse.get_pos()
            if prev_pos is not None:
                current_zoom = base_zoom * shared_zoom_multiplier.value
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
                    reveal_radius = base_reveal_screen_px
                    map_x = (pos[0] - draw_x) / current_zoom
                    map_y = (pos[1] - draw_y) / current_zoom
                    map_r = reveal_radius / current_zoom
                    nx = map_x / orig_w
                    ny = map_y / orig_h
                    nr = map_r / max(orig_w, orig_h)
                    shared_revealed.append((nx, ny, nr))
                    pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(map_x), int(map_y)), int(map_r))
            prev_pos = pos
        
        # Shared mouse position
        mx, my = pygame.mouse.get_pos()
        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
        if draw_x <= mx < draw_x + orig_w * current_zoom and draw_y <= my < draw_y + orig_h * current_zoom:
            map_x = (mx - draw_x) / current_zoom
            map_y = (my - draw_y) / current_zoom
            shared_mouse_map_nx.value = map_x / orig_w
            shared_mouse_map_ny.value = map_y / orig_h
        else:
            shared_mouse_map_nx.value = -1.0
            shared_mouse_map_ny.value = -1.0
        
        # Rendering 
        scaled_w = int(orig_w * current_zoom)
        scaled_h = int(orig_h * current_zoom)
        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
        
        current_time_ms = pygame.time.get_ticks()

        # Background (GIF or static)
        if current_path.lower().endswith('.gif') and current_path in animated_gifs:
            frame_surf = get_current_gif_frame(animated_gifs, current_path, current_time_ms)
            if frame_surf:
                bg_scaled = pygame.transform.smoothscale(frame_surf, (scaled_w, scaled_h))
            else:
                bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))
        else:
            bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))

        try:
            fog_scaled = pygame.transform.smoothscale(fog_orig, (scaled_w, scaled_h))
        except ValueError as e:
            print("Zoom scale error:", e)
            continue

        screen.fill((0, 0, 0))
        screen.blit(bg_scaled, (draw_x, draw_y))
        screen.blit(fog_scaled, (draw_x, draw_y))
        
        # Animated effects
        for effect in shared_animated_effects:
            if not effect.get('visible', True):
                continue
            frames, durations = effect['frames'], effect['durations']
            if not frames:
                continue

            elapsed = current_time_ms - effect.get('start_ms', current_time_ms)
            total_dur = sum(durations)
            if total_dur == 0:
                total_dur = 100 * len(frames)

            pos_in_anim = elapsed % total_dur
            cumulative = 0
            frame_idx = 0
            for i, dur in enumerate(durations):
                if pos_in_anim < cumulative + dur:
                    frame_idx = i
                    break
                cumulative += dur

            frame_surf = frames[frame_idx]
            base_w, base_h = frame_surf.get_size()
            scaled_w = int(base_w * current_zoom * effect.get('scale', 1.0))
            scaled_h = int(base_h * current_zoom * effect.get('scale', 1.0))
            scaled = pygame.transform.smoothscale(frame_surf, (scaled_w, scaled_h))

            px = int(draw_x + effect['nx'] * orig_w * current_zoom - scaled_w // 2)
            py = int(draw_y + effect['ny'] * orig_h * current_zoom - scaled_h // 2)
            screen.blit(scaled, (px, py))

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
        
        # Shapes 
        for sh in shared_shapes:
            nx, ny = sh['nx'], sh['ny']
            size_norm = sh['size']
            rotation = sh.get('rotation', 0.0)
            x_screen = draw_x + nx * orig_w * current_zoom
            y_screen = draw_y + ny * orig_h * current_zoom
            pos = (int(x_screen), int(y_screen))
            color = (200, 220, 255)
            width = 3
            
            base_size_pixels = size_norm * max(orig_w, orig_h) * current_zoom
            angle_rad = math.radians(rotation)
            
            shape_type = sh['type']
            if shape_type == 0:  # Circle
                radius = base_size_pixels / 2
                pygame.draw.circle(screen, color, pos, int(radius), width)
            elif shape_type == 1:  # Square
                half = base_size_pixels / 2
                surf = pygame.Surface((base_size_pixels, base_size_pixels), pygame.SRCALPHA)
                pygame.draw.rect(surf, color, (0, 0, base_size_pixels, base_size_pixels), width)
                rotated = pygame.transform.rotate(surf, rotation)
                rect = rotated.get_rect(center=pos)
                screen.blit(rotated, rect)
            elif shape_type == 2:  # Cone
                length = base_size_pixels * 1.4
                apex_angle = 60
                left_angle = angle_rad - math.radians(apex_angle / 2)
                right_angle = angle_rad + math.radians(apex_angle / 2)
                apex = pos
                left = (apex[0] + length * math.cos(left_angle), apex[1] + length * math.sin(left_angle))
                right = (apex[0] + length * math.cos(right_angle), apex[1] + length * math.sin(right_angle))
                points = [apex, left, right]
                pygame.draw.polygon(screen, color, points, width)
            elif shape_type == 3:  # Line/Rect
                w = base_size_pixels * 1.8
                h = base_size_pixels * 0.45
                surf = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(surf, color, (0, 0, w, h), width)
                rotated = pygame.transform.rotate(surf, rotation)
                rect = rotated.get_rect(center=pos)
                screen.blit(rotated, rect)
        
        # Shape preview 
        shape_idx = shared_current_shape_type.value
        if shape_idx != -1 and not mouse_pressed and not menu_area.collidepoint(pygame.mouse.get_pos()):
            mx, my = pygame.mouse.get_pos()
            preview_color = (200, 220, 255, 140)
            preview_width = 3
            
            base_preview_norm = shared_current_shape_size.value
            preview_pixels = base_preview_norm * max(orig_w, orig_h) * current_zoom
            
            angle_rad = math.radians(shared_current_rotation.value)
            center = (mx, my)
            
            if shapes[shape_idx] == "Circle":
                radius = preview_pixels / 2
                pygame.draw.circle(screen, preview_color, center, int(radius), preview_width)
            elif shapes[shape_idx] == "Square":
                side = preview_pixels
                surf = pygame.Surface((side, side), pygame.SRCALPHA)
                pygame.draw.rect(surf, preview_color, (0, 0, side, side), preview_width)
                rotated = pygame.transform.rotate(surf, shared_current_rotation.value)
                rect = rotated.get_rect(center=center)
                screen.blit(rotated, rect)
            elif shapes[shape_idx] == "Cone":
                length = preview_pixels * 1.4
                apex_angle = 60
                left_angle = angle_rad - math.radians(apex_angle / 2)
                right_angle = angle_rad + math.radians(apex_angle / 2)
                apex = center
                left = (mx + length * math.cos(left_angle), my + length * math.sin(left_angle))
                right = (mx + length * math.cos(right_angle), my + length * math.sin(right_angle))
                points = [apex, left, right]
                pygame.draw.polygon(screen, preview_color, points, preview_width)
            elif shapes[shape_idx] == "Line/Rect":
                w = preview_pixels * 1.8
                h = preview_pixels * 0.45
                surf = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(surf, preview_color, (0, 0, w, h), preview_width)
                rotated = pygame.transform.rotate(surf, shared_current_rotation.value)
                rect = rotated.get_rect(center=center)
                screen.blit(rotated, rect)
        
        # Brush preview 
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
        
        # Save State button
        pygame.draw.rect(screen, (80, 140, 80), save_button_rect, border_radius=6)
        save_txt = menu_font.render("Save State", True, (255,255,255))
        screen.blit(save_txt, (save_button_rect.x + 10, save_button_rect.y + 5))
        
        # Back button + history count
        pygame.draw.rect(screen, (100, 140, 200), back_button_rect, border_radius=6)
        back_txt = menu_font.render("Back", True, (255,255,255))
        screen.blit(back_txt, (back_button_rect.x + 25, back_button_rect.y + 5))
        if backstack:
            count_txt = menu_font.render(f"({len(backstack)})", True, (200, 220, 255))
            screen.blit(count_txt, (back_button_rect.right + 8, back_button_rect.y + 5))
        
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
                "Mouse wheel: zoom map",
                "Shift + wheel: rotate shape",
                "Q / E: rotate shape 15°",
                "Ctrl + R: reset rotation",
                "SPACE: deselect shape",
                "F: load map or state",
                "R: reset everything",
                "M: remove last marker",
                "1-9,0,A,S,D,G: condition",
                "Q/W/E: marker size",
                "Ctrl + B or Back button: return to previous map",
                "History auto-saves when you load a new map (max 5)",
                "Ctrl + S: save state + history",
                "H: toggle help",
                "ESC: quit",
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
                   shared_full_reveal, shared_animated_effects):
    
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    pygame.time.wait(500)
    sizes = pygame.display.get_desktop_sizes()
    if display_index < len(sizes):
        w, h = sizes[display_index]
    else:
        w, h = 1920, 1080  # fallback
    screen = pygame.display.set_mode((w, h), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Audience Monitor")
    
    current_path = initial_image_path
    animated_gifs = {}

    if current_path.lower().endswith('.gif'):
        frames, durations = load_gif_frames(current_path)
        if frames:
            animated_gifs[current_path] = {
                'frames': frames,
                'durations': durations,
                'total_dur': sum(durations),
                'start_ms': pygame.time.get_ticks()
            }

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
    
    marker_sizes = [16, 31, 52]
    
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
                animated_gifs.clear()
                if current_path.lower().endswith('.gif'):
                    frames, durations = load_gif_frames(current_path)
                    if frames:
                        animated_gifs[current_path] = {
                            'frames': frames,
                            'durations': durations,
                            'total_dur': sum(durations),
                            'start_ms': pygame.time.get_ticks()
                        }
                orig_w, orig_h = image.get_size()

                base_zoom = min(screen_w / orig_w, screen_h / orig_h)

                mask_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
                mask_orig.fill((0, 0, 0, 255))

                prev_len = 0
                local_fog_reset = shared_fog_reset.value

                shared_camera_nx.value = 0.5
                shared_camera_ny.value = 0.5

                print(f"Audience: loaded new map {current_path} — new base_zoom = {base_zoom:.4f}")

            except Exception as e:
                print("Audience image load failed:", e)
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        if shared_fog_reset.value > local_fog_reset:
            mask_orig.fill((0, 0, 0, 255))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        if shared_full_reveal.value:
            mask_orig.fill((0, 0, 0, 0))
            shared_full_reveal.value = False
            prev_len = 0

        current_len = len(shared_revealed)
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
        
        scaled_w = int(orig_w * current_zoom)
        scaled_h = int(orig_h * current_zoom)
        draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
        draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
        
        current_time_ms = pygame.time.get_ticks()

        if current_path.lower().endswith('.gif') and current_path in animated_gifs:
            frame_surf = get_current_gif_frame(animated_gifs, current_path, current_time_ms)
            if frame_surf:
                bg_scaled = pygame.transform.smoothscale(frame_surf, (scaled_w, scaled_h))
            else:
                bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))
        else:
            bg_scaled = pygame.transform.smoothscale(image, (scaled_w, scaled_h))

        try:
            mask_scaled = pygame.transform.smoothscale(mask_orig, (scaled_w, scaled_h))
        except ValueError as e:
            print("Zoom scale error (audience):", e)
            continue

        screen.fill((0, 0, 0))
        screen.blit(bg_scaled, (draw_x, draw_y))
        screen.blit(mask_scaled, (draw_x, draw_y))

        for effect in shared_animated_effects:
            if not effect.get('visible', True):
                continue

            frames, durations = effect['frames'], effect['durations']
            if not frames:
                continue

            elapsed = current_time_ms - effect.get('start_ms', current_time_ms)
            total_dur = sum(durations)
            if total_dur == 0:
                total_dur = 100 * len(frames)

            pos_in_anim = elapsed % total_dur
            cumulative = 0
            frame_idx = 0
            for i, dur in enumerate(durations):
                if pos_in_anim < cumulative + dur:
                    frame_idx = i
                    break
                cumulative += dur

            frame_surf = frames[frame_idx]

            base_w, base_h = frame_surf.get_size()
            scaled_w = int(base_w * current_zoom * effect.get('scale', 1.0))
            scaled_h = int(base_h * current_zoom * effect.get('scale', 1.0))
            scaled = pygame.transform.smoothscale(frame_surf, (scaled_w, scaled_h))

            px = int(draw_x + effect['nx'] * orig_w * current_zoom - scaled_w // 2)
            py = int(draw_y + effect['ny'] * orig_h * current_zoom - scaled_h // 2)

            screen.blit(scaled, (px, py))

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
        
        # Shapes 
        for sh in shared_shapes:
            nx, ny = sh['nx'], sh['ny']
            size_norm = sh['size']
            rotation = sh.get('rotation', 0.0)
            x_screen = draw_x + nx * orig_w * current_zoom
            y_screen = draw_y + ny * orig_h * current_zoom
            pos = (int(x_screen), int(y_screen))
            color = (200, 220, 255)
            width = 3
            
            base_size_pixels = size_norm * max(orig_w, orig_h) * current_zoom
            angle_rad = math.radians(rotation)
            
            shape_type = sh['type']
            if shape_type == 0:  # Circle
                radius = base_size_pixels / 2
                pygame.draw.circle(screen, color, pos, int(radius), width)
            elif shape_type == 1:  # Square
                half = base_size_pixels / 2
                surf = pygame.Surface((base_size_pixels, base_size_pixels), pygame.SRCALPHA)
                pygame.draw.rect(surf, color, (0, 0, base_size_pixels, base_size_pixels), width)
                rotated = pygame.transform.rotate(surf, rotation)
                rect = rotated.get_rect(center=pos)
                screen.blit(rotated, rect)
            elif shape_type == 2:  # Cone
                length = base_size_pixels * 1.4
                apex_angle = 60
                left_angle = angle_rad - math.radians(apex_angle / 2)
                right_angle = angle_rad + math.radians(apex_angle / 2)
                apex = pos
                left = (apex[0] + length * math.cos(left_angle), apex[1] + length * math.sin(left_angle))
                right = (apex[0] + length * math.cos(right_angle), apex[1] + length * math.sin(right_angle))
                points = [apex, left, right]
                pygame.draw.polygon(screen, color, points, width)
            elif shape_type == 3:  # Line/Rect
                w = base_size_pixels * 1.8
                h = base_size_pixels * 0.45
                surf = pygame.Surface((w, h), pygame.SRCALPHA)
                pygame.draw.rect(surf, color, (0, 0, w, h), width)
                rotated = pygame.transform.rotate(surf, rotation)
                rect = rotated.get_rect(center=pos)
                screen.blit(rotated, rect)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()