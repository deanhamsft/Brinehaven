import multiprocessing
import pygame
import sys
import os
import tkinter as tk
from tkinter import filedialog

def control_window(image_path, shared_revealed, shared_running, shared_new_image, display_index=0):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("Control Monitor (Reveal Fog)")

    def load_and_scale(path):
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (screen_w, screen_h))

    bg = load_and_scale(image_path)
    current_image_path = image_path

    # Fog overlay (semi-transparent on control)
    fog_overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    fog_overlay.fill((20, 20, 60, 180))  # dark overlay

    clock = pygame.time.Clock()
    reveal_radius = 60
    brush_color = (255, 255, 100, 120)

    font = pygame.font.SysFont(None, 48)
    help_text = font.render("Hold LMB to reveal | F = Load new map | ESC = quit", True, (255, 255, 100))

    selecting = False
    prev_len = 0

    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shared_running.value = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shared_running.value = False
                if event.key == pygame.K_f and not selecting:  # Press F to select new image
                    selecting = True
                    # ── Show overlay message ──
                    overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, 160))  # semi-dark
                    msg = font.render("Selecting new map...", True, (255, 220, 100))
                    msg_rect = msg.get_rect(center=(screen_w//2, screen_h//2))
                    screen.blit(overlay, (0, 0))
                    screen.blit(msg, msg_rect)
                    pygame.display.flip()

                    # ── Tkinter dialog in control process ──
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes('-topmost', True)
                    root.overrideredirect(True)
                    root.geometry("200x100+50+50")  # Near top-left of primary/control monitor
                    root.focus_force()

                    new_path = filedialog.askopenfilename(
                        parent=root,
                        title="Select New Map Image",
                        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
                    )
                    root.destroy()

                    if new_path and new_path != current_image_path:
                        shared_new_image.value = new_path  # Signal to both processes
                        current_image_path = new_path

                    selecting = False

        if not selecting:
            if pygame.mouse.get_pressed()[0]:
                pos = pygame.mouse.get_pos()
                nx = pos[0] / screen_w
                ny = pos[1] / screen_h
                nr = reveal_radius / max(screen_w, screen_h)
                shared_revealed.append((nx, ny, nr))

                pygame.draw.circle(fog_overlay, (0, 0, 0, 0), pos, reveal_radius)
                pygame.draw.circle(screen, brush_color, pos, reveal_radius + 4, 3)

        # Check for new image from shared
        if shared_new_image.value:
            try:
                bg = load_and_scale(shared_new_image.value)
                # Optional: clear reveals on new map? Uncomment if desired:
                # shared_revealed[:] = []
                # fog_overlay.fill((20, 20, 60, 180))
                shared_new_image.value = ""  # Clear signal
            except Exception as e:
                print(f"Failed to load new image: {e}")

        # Sync reveals to local fog overlay
        current_len = len(shared_revealed)
        if current_len > prev_len:
            for i in range(prev_len, current_len):
                nx, ny, nr = shared_revealed[i]
                x = int(nx * screen_w)
                y = int(ny * screen_h)
                r = int(nr * max(screen_w, screen_h)) + 2
                pygame.draw.circle(fog_overlay, (0, 0, 0, 0), (x, y), r)
            prev_len = current_len

        # Draw
        screen.blit(bg, (0, 0))
        screen.blit(fog_overlay, (0, 0))

        # Live brush preview
        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(screen, (255, 255, 180, 80), (mx, my), reveal_radius, 2)

        screen.blit(help_text, (20, 20))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

def audience_window(image_path, shared_revealed, shared_running, shared_new_image, display_index=1):
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.NOFRAME, display=display_index)
    screen_w, screen_h = screen.get_size()

    def load_and_scale(path):
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (screen_w, screen_h))

    bg = load_and_scale(image_path)

    mask = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 255))

    prev_len = 0
    clock = pygame.time.Clock()

    while shared_running.value:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or \
               (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                shared_running.value = False

        # Check for new image
        if shared_new_image.value:
            try:
                bg = load_and_scale(shared_new_image.value)
                # Optional: mask.fill((0, 0, 0, 255))  # reset fog if desired
                shared_new_image.value = ""
            except:
                pass

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
    # Initial file selection (on control monitor)
    
    root = tk.Tk()
    root.title(" ")
    root.attributes('-topmost', True)
    root.overrideredirect(True)
    root.geometry("200x100+50+50")
    root.focus_force()

    image_path = filedialog.askopenfilename(
        parent=root,
        title="Select Map Image for DnD Fog of War",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]
    )
    root.destroy()

    if not image_path:
        print("No image selected. Exiting.")
        sys.exit(0)

    print(f"Selected: {image_path}")

    # Multiprocessing setup
    manager = multiprocessing.Manager()
    shared_revealed = manager.list()
    shared_running = manager.Value('b', True)
    shared_new_image = manager.Value(str, "")  # Shared string for new path signal

    CONTROL_DISPLAY = 0
    AUDIENCE_DISPLAY = 1
    #THIRD_DISPLAY = 2 

    control_proc = multiprocessing.Process(
        target=control_window,
        args=(image_path, shared_revealed, shared_running, shared_new_image, CONTROL_DISPLAY)
    )

    audience_proc = multiprocessing.Process(
        target=audience_window,
        args=(image_path, shared_revealed, shared_running, shared_new_image, AUDIENCE_DISPLAY)
    )

    #third_proc = multiprocessing.Process(
    #    target=audience_window,
    #    args=(image_path, shared_revealed, shared_running, shared_new_image, THIRD_DISPLAY)
    #)
 
    audience_proc.start()
    control_proc.start()
    #third_proc.start()

    control_proc.join()
    shared_running.value = False
    audience_proc.join()
    #third_proc.join()