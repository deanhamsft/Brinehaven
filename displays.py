    
import pygame
import sys

pygame.init()
num = pygame.display.get_num_displays()
print(f"Detected {num} display(s):")
sizes = pygame.display.get_desktop_sizes()
for i in range(num):
    w, h = sizes[i] if i < len(sizes) else ("unknown", "unknown")
    print(f"  Display {i}: {w} × {h}")
pygame.quit()
sys.exit(0)