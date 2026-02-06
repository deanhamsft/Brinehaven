import multiprocessing
import pygame
import sys
import os
import tkinter as tk
from tkinter import filedialog

def control_window(image_path, shared_revealed, shared_running, display_index=0):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Control Monitor (Reveal Fog)")
    
    image = pygame.image.load(image_path).convert()
    bg = pygame.transform.smoothscale(image, (screen_w, screen_h))
    
    # Fog overlay for control monitor (semi-transparent)
    fog_overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    fog_overlay.fill((20, 20, 60, 180))  # Dark blue-gray, ~70% opacity (0=transparent, 255=opaque)
    
    clock = pygame.time.Clock()
    reveal_radius = 60          # Slightly larger feel on control
    brush_color = (255, 255, 100, 120)  # Light yellow semi-transparent brush feedback
    
    font = pygame.font.SysFont(None, 36)
    help_text = font.render("Hold LEFT MOUSE to reveal | ESC to quit", True, (255, 255, 100))
    
    prev_len = 0
    
    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shared_running.value = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shared_running.value = False
                
        mouse_pressed = pygame.mouse.get_pressed()[0]
        if mouse_pressed:
            pos = pygame.mouse.get_pos()
            nx = pos[0] / screen_w
            ny = pos[1] / screen_h
            nr = reveal_radius / max(screen_w, screen_h)
            shared_revealed.append((nx, ny, nr))
            
            # Visual feedback while dragging
            pygame.draw.circle(fog_overlay, (0, 0, 0, 0), pos, reveal_radius)
            pygame.draw.circle(screen, brush_color, pos, reveal_radius + 4, 3)  # temporary ring
        
        # Sync new reveals to our local fog overlay (in case of lag or other processes)
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = int(nx * screen_w)
                y = int(ny * screen_h)
                r = int(nr * max(screen_w, screen_h)) + 2  # slight overshoot to avoid edges
                pygame.draw.circle(fog_overlay, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
        
        # Draw everything
        screen.blit(bg, (0, 0))
        screen.blit(fog_overlay, (0, 0))
        
        # Optional: subtle live brush preview even when not clicking
        if not mouse_pressed:
            mx, my = pygame.mouse.get_pos()
            pygame.draw.circle(screen, (255, 255, 180, 80), (mx, my), reveal_radius, 2)
        
        screen.blit(help_text, (20, 20))
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()

def audience_window(image_path, shared_revealed, shared_running, display_index=1):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Audience Monitor")
    
    image = pygame.image.load(image_path).convert()
    bg = pygame.transform.smoothscale(image, (screen_w, screen_h))
    
    mask = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 255))  # full black fog
    
    prev_len = 0
    clock = pygame.time.Clock()
    
    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or \
               (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                shared_running.value = False
        
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = int(nx * screen_w)
                y = int(ny * screen_h)
                r = int(nr * max(screen_w, screen_h))
                pygame.draw.circle(mask, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len
        
        screen.blit(bg, (0, 0))
        screen.blit(mask, (0, 0))
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()

if __name__ == "__main__":
    # ── File selection dialog on PRIMARY / control monitor ──────────────────
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.title(" ")                     # Minimal title
    root.attributes('-topmost', True)   # Keep on top briefly
    root.overrideredirect(True)         # No window decorations (clean look)

    # Position on primary monitor (top-left corner, or center it if preferred)
    # Primary is almost always at (0,0) in X11 coordinates
    root.geometry("200x100+50+50")      # Small window near top-left of primary

    # Optional: center on primary if you know approx size
    # root.update_idletasks()
    # w = root.winfo_reqwidth()
    # h = root.winfo_reqheight()
    # root.geometry(f"{w}x{h}+{50}+{50}")

    # Force focus
    root.focus_force()

    image_path = filedialog.askopenfilename(
        parent=root,                    # ← Key: dialog is transient to this window
        title="Select Map Image for DnD Fog of War",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
                   ("All files", "*.*")]
    )

    root.destroy()                      # Clean up immediately

    if not image_path:
        print("No image selected. Exiting.")
        sys.exit(0)

    print(f"Selected: {image_path}")

    # ── Rest of your multiprocessing setup remains unchanged ───────────────
    manager = multiprocessing.Manager()
    shared_revealed = manager.list()
    shared_running = manager.Value('b', True)

    CONTROL_DISPLAY = 0
    AUDIENCE_DISPLAY = 1

    control_proc = multiprocessing.Process(
        target=control_window,
        args=(image_path, shared_revealed, shared_running, CONTROL_DISPLAY)
    )
    audience_proc = multiprocessing.Process(
        target=audience_window,
        args=(image_path, shared_revealed, shared_running, AUDIENCE_DISPLAY)
    )

    audience_proc.start()
    control_proc.start()

    control_proc.join()
    shared_running.value = False
    audience_proc.join()