from __future__ import annotations
import multiprocessing
import pygame
import sys
import os
import tkinter as tk
from tkinter import filedialog
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description="DnD Fog of War - Multi-display support")
    parser.add_argument('--control', type=int, default=0,
                        help="Display index for control window (default: 0)")
    parser.add_argument('--audience', type=int, default=1,
                        help="Display index for audience window (default: 1)")
    parser.add_argument('--list-displays', action='store_true',
                        help="List available displays and their resolutions, then exit")
    return parser.parse_args()


def list_displays():
    pygame.init()
    num = pygame.display.get_num_displays()
    print(f"Detected {num} display(s):")
    sizes = pygame.display.get_desktop_sizes()
    for i in range(num):
        w, h = sizes[i] if i < len(sizes) else ("unknown", "unknown")
        print(f"  Display {i}: {w} × {h}")
    pygame.quit()
    sys.exit(0)


def control_window(initial_image_path, shared_revealed, shared_running, shared_image_path,
                   display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset,
                   shared_markers, shared_current_marker_color, shared_current_marker_size):
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
    
    marker_colors = [
        (255, 0, 0, 255),    # Red
        (0, 255, 0, 255),    # Green
        (0, 0, 255, 255),    # Blue
        (255, 255, 0, 255),  # Yellow
        (255, 0, 255, 255),  # Magenta
    ]
    
    marker_sizes = [  # Base screen-space radius when zoom=1.0
        12,   # Small
        24,   # Medium
        40,   # Large
    ]
    
    font = pygame.font.SysFont(None, 36)
    help_text = font.render(
        "LEFT=reveal | Shift+LEFT=pan | Wheel=zoom | F=new image | R=reset fog | "
        "1-5=color | Q/W/E=size | RIGHT=place marker | ESC=quit",
        True, (255, 255, 100)
    )
    status_msg = None
    status_timer = 0
    
    prev_len = 0
    prev_marker_len = 0
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
                if event.key == pygame.K_m:  # ← NEW: reset markers only
                    shared_markers[:] = []
                    status_msg = font.render("Markers cleared", True, (220, 180, 60))
                    status_timer = 120
                # Marker color 1-5
                if pygame.K_1 <= event.key <= pygame.K_5:
                    idx = event.key - pygame.K_1
                    shared_current_marker_color.value = idx
                    status_msg = font.render(f"Marker color: {['Red','Green','Blue','Yellow','Magenta'][idx]}", True, (100, 255, 100))
                    status_timer = 120
                # Marker size Q=small, W=medium, E=large
                if event.key in (pygame.K_q, pygame.K_w, pygame.K_e):
                    if event.key == pygame.K_q: idx = 0
                    elif event.key == pygame.K_w: idx = 1
                    else: idx = 2
                    shared_current_marker_size.value = idx
                    status_msg = font.render(f"Marker size: {['Small','Medium','Large'][idx]}", True, (100, 255, 100))
                    status_timer = 120
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                    current_drag_mode = 'pan' if shift_pressed else 'reveal'
                    prev_pos = event.pos
                if event.button == 3:  # Right-click → place marker
                    pos = pygame.mouse.get_pos()
                    draw_x = screen_w / 2 - (shared_camera_nx.value * orig_w) * current_zoom
                    draw_y = screen_h / 2 - (shared_camera_ny.value * orig_h) * current_zoom
                    map_x = (pos[0] - draw_x) / current_zoom
                    map_y = (pos[1] - draw_y) / current_zoom
                    nx = map_x / orig_w
                    ny = map_y / orig_h
                    # Use selected size, scale relative to zoom at placement time
                    base_r = marker_sizes[shared_current_marker_size.value]
                    nr = base_r / current_zoom / max(orig_w, orig_h)  # normalized
                    color_idx = shared_current_marker_color.value
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
                prev_marker_len = 0
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
        
        # Draw all markers
        for nx, ny, nr, color_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (draw_x + x, draw_y + y)
            pygame.draw.circle(screen, marker_colors[color_idx], pos, r)
        
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
                    shared_markers, shared_current_marker_color, shared_current_marker_size):
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
    
    marker_colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
    ]
    
    marker_sizes = [12, 24, 40]  # Same as control
    
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
        if current_len > prev_len:
            for i in range(prev_len, current_len):
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
        
        # Draw markers
        for nx, ny, nr, color_idx in shared_markers:
            x = int(nx * orig_w * current_zoom)
            y = int(ny * orig_h * current_zoom)
            r = int(nr * max(orig_w, orig_h) * current_zoom)
            pos = (draw_x + x, draw_y + y)
            pygame.draw.circle(screen, marker_colors[color_idx], pos, r)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


if __name__ == "__main__":
    args = parse_arguments()
    
    if args.list_displays:
        list_displays()
    
    root = tk.Tk()
    root.withdraw()
    
    image_path = filedialog.askopenfilename(
        title="Select Map Image for DnD Fog of War",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
    )
    
    if not image_path:
        print("No image selected. Exiting.")
        sys.exit(0)
    
    print(f"Selected image: {image_path}")
    
    pygame.init()
    num_displays = pygame.display.get_num_displays()
    pygame.quit()
    
    control_display = args.control
    audience_display = args.audience
    
    if control_display < 0 or control_display >= num_displays:
        print(f"Warning: Control display {control_display} invalid. Using 0.")
        control_display = 0
    
    if audience_display < 0 or audience_display >= num_displays:
        print(f"Warning: Audience display {audience_display} invalid. Using 1 or 0.")
        audience_display = 1 if num_displays > 1 else 0
    
    if control_display == audience_display:
        print(f"Note: Control & audience on same display {control_display} (overlap possible).")
    
    print(f"Launching:\n  • Control → display {control_display}\n  • Audience → display {audience_display}")
    
    manager = multiprocessing.Manager()
    shared_revealed        = manager.list()
    shared_running         = manager.Value('b', True)
    shared_image_path      = manager.list([image_path])
    shared_zoom_multiplier = manager.Value('f', 1.0)
    shared_camera_nx       = manager.Value('f', 0.5)
    shared_camera_ny       = manager.Value('f', 0.5)
    shared_fog_reset       = manager.Value('i', 0)
    shared_markers         = manager.list()                     # (nx, ny, nr, color_idx)
    shared_current_marker_color = manager.Value('i', 0)         # 0-4
    shared_current_marker_size  = manager.Value('i', 1)         # 0=small, 1=medium, 2=large
    
    control_proc = multiprocessing.Process(
        target=control_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              control_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset, shared_markers,
              shared_current_marker_color, shared_current_marker_size)
    )
    audience_proc = multiprocessing.Process(
        target=audience_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              audience_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset, shared_markers,
              shared_current_marker_color, shared_current_marker_size)
    )
    
    audience_proc.start()
    control_proc.start()
    
    control_proc.join()
    shared_running.value = False
    audience_proc.join()