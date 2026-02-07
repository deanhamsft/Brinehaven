import multiprocessing
import sys

# Must be first thing - protects against fork + GUI libraries
if sys.platform in ('darwin', 'linux'):
    multiprocessing.set_start_method('spawn', force=True)

import pygame
import os
import tkinter as tk
from tkinter import filedialog
import argparse
from screeninfo import get_monitors

# Helper function to create a hidden root on a specific display
def create_positioned_root_for_dialog(display_index):
    """
    Creates a tiny, topmost, almost-invisible Tk root positioned roughly centered
    on the target display index (from pygame.set_mode(display=...)).
    Returns the root so you can use it as parent= in filedialog.
    """
    root = tk.Tk()
    root.overrideredirect(True)           # no title bar
    root.attributes('-alpha', 0.01)       # nearly transparent
    root.attributes('-topmost', True)     # force above everything briefly

    try:
        monitors = get_monitors()
        if 0 <= display_index < len(monitors):
            mon = monitors[display_index]
            # Center a small window on this monitor's bounds
            x = mon.x + (mon.width // 2) - 5
            y = mon.y + (mon.height // 2) - 5
            root.geometry(f"10x10+{x}+{y}")
            print(f"Positioning dialog helper on monitor {display_index}: "
                  f"at ({x}, {y}) on monitor bounds ({mon.x}, {mon.y}, {mon.width}, {mon.height})")
        else:
            root.geometry("10x10+100+100")  # fallback to primary-ish
    except Exception as e:
        print(f"Monitor detection failed: {e} → using fallback position")
        root.geometry("10x10+100+100")

    root.update_idletasks()   # apply geometry immediately
    root.focus_force()        # push focus to this tiny window
    root.lift()               # bring to front
    return root

def parse_arguments():
    parser = argparse.ArgumentParser(description="DnD Fog of War - Multi-display support")
    parser.add_argument('--c', type=int, default=0,
                        help="Display index for control window (default: 0)")
    parser.add_argument('--a', type=int, default=1,
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
                   display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset):
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
    
    font = pygame.font.SysFont(None, 36)
    help_text = font.render("Hold LEFT to reveal | Shift+LEFT drag to pan | Wheel=zoom | F=new image | R=reset fog | ESC=quit", True, (255, 255, 100))
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
                    root = create_positioned_root_for_dialog(display_index)  # display_index is the control one
                    new_path = filedialog.askopenfilename(
                        parent=root,
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
                    shared_fog_reset.value += 1
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # left mouse
                    shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                    current_drag_mode = 'pan' if shift_pressed else 'reveal'
                    prev_pos = event.pos
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
        
        # Check for new image load
        if shared_image_path and shared_image_path[0] != current_path:
            try:
                current_path = shared_image_path[0]
                image = pygame.image.load(current_path).convert()
                orig_w, orig_h = image.get_size()
                base_zoom = min(screen_w / orig_w, screen_h / orig_h)
                fog_orig = pygame.Surface((orig_w, orig_h), pygame.SRCALPHA)
                fog_orig.fill((20, 20, 60, 180))
                shared_revealed[:] = []
                shared_zoom_multiplier.value = 1.0
                shared_camera_nx.value = 0.5
                shared_camera_ny.value = 0.5
                shared_fog_reset.value += 1
                prev_len = 0
                local_fog_reset = shared_fog_reset.value
            except Exception as e:
                print("Failed to load new image:", e)
        
        current_zoom = base_zoom * shared_zoom_multiplier.value
        
        # Handle fog reset
        if shared_fog_reset.value > local_fog_reset:
            fog_orig.fill((20, 20, 60, 180))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        
        # Sync reveals to fog layer
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = nx * orig_w
                y = ny * orig_h
                r = nr * max(orig_w, orig_h)
                pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(x), int(y)), int(r))
            prev_len = current_len
        
        # Handle mouse dragging (reveal or pan)
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
                    # Immediate feedback on control
                    pygame.draw.circle(fog_orig, (0, 0, 0, 0), (int(map_x), int(map_y)), int(map_r))
                    pygame.draw.circle(screen, brush_color, pos, reveal_radius + 4, 3)
            prev_pos = pos
        
        # Calculate draw position & size
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
        
        # Brush preview when not dragging
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
                    display_index, shared_zoom_multiplier, shared_camera_nx, shared_camera_ny, shared_fog_reset):
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
    
    prev_len = 0
    local_fog_reset = shared_fog_reset.value
    clock = pygame.time.Clock()
    
    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or \
               (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                shared_running.value = False
        
        # New image check
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
        
        # Fog reset
        if shared_fog_reset.value > local_fog_reset:
            mask_orig.fill((0, 0, 0, 255))
            local_fog_reset = shared_fog_reset.value
            prev_len = 0
        
        # Apply reveals
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
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()


if __name__ == "__main__":
    args = parse_arguments()
    
    if args.list_displays:
        list_displays()
    
    root = tk.Tk()
    root.withdraw()
    
    # Initial selection (in __main__)
    root = create_positioned_root_for_dialog(args.c)   # or args.control
    image_path = filedialog.askopenfilename(
        parent=root,   # ← important
        title="Select Map Image for DnD Fog of War",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
    )
    root.destroy()   # clean up
    
    if not image_path:
        print("No image selected. Exiting.")
        sys.exit(0)
    
    print(f"Selected image: {image_path}")
    
    # ────────────────────────────────────────────────────────────────
    # Determine display indices (defaults to 0 and 1 if no args given)
    # ────────────────────────────────────────────────────────────────
    pygame.init()
    num_displays = pygame.display.get_num_displays()
    pygame.quit()
    
    control_display = args.c
    audience_display = args.a
    
    if control_display < 0 or control_display >= num_displays:
        print(f"Warning: Control display {control_display} invalid "
              f"(only {num_displays} displays). Falling back to 0.")
        control_display = 0
    
    if audience_display < 0 or audience_display >= num_displays:
        print(f"Warning: Audience display {audience_display} invalid "
              f"(only {num_displays} displays). Falling back to 1 or 0.")
        audience_display = 1 if num_displays > 1 else 0
    
    if control_display == audience_display:
        print(f"Note: Control & audience both on display {control_display} "
              "(windows will overlap unless moved).")
    
    print(f"Launching:")
    print(f"  • Control  window → display {control_display}")
    print(f"  • Audience window → display {audience_display}")
    if num_displays > 2:
        print(f"  (found {num_displays} displays — use --control N --audience M to choose others)")
    
    # ────────────────────────────────────────────────────────────────
    # Shared multiprocessing state
    # ────────────────────────────────────────────────────────────────
    manager = multiprocessing.Manager()
    shared_revealed        = manager.list()
    shared_running         = manager.Value('b', True)
    shared_image_path      = manager.list([image_path])
    shared_zoom_multiplier = manager.Value('f', 1.0)
    shared_camera_nx       = manager.Value('f', 0.5)
    shared_camera_ny       = manager.Value('f', 0.5)
    shared_fog_reset       = manager.Value('i', 0)
    
    # ────────────────────────────────────────────────────────────────
    # Launch windows in separate processes
    # ────────────────────────────────────────────────────────────────
    control_proc = multiprocessing.Process(
        target=control_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              control_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset)
    )
    audience_proc = multiprocessing.Process(
        target=audience_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              audience_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset)
    )
    
    audience_proc.start()
    control_proc.start()
    
    control_proc.join()
    shared_running.value = False
    audience_proc.join()