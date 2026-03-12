from __future__ import annotations
import multiprocessing
import sys
import os
import tkinter as tk
from tkinter import filedialog
import argparse
import traceback
import pygame
import json
from app_core import control_window, audience_window

LOAD_FROM_SAVED_STATE = False

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


def main(load_from_saved=False):
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
    shared_running         = manager.Value('b', True)
    shared_image_path      = manager.list([image_path])
    shared_current_condition_idx = manager.Value('i', 0)
    shared_current_marker_size  = manager.Value('i', 1)         # 0=small, 1=medium, 2=large
    shared_current_shape_type   = manager.Value('i', -1)        # -1 = no shape, 0=Circle, 1=Square, 2=Cone, 3=Line/Rect
    shared_mouse_map_nx = manager.Value('f', -1.0)
    shared_mouse_map_ny = manager.Value('f', -1.0)
    shared_full_reveal = manager.Value('b', False)  # set to True to trigger full reveal on audience side
    shared_revealed         = manager.list()
    shared_zoom_multiplier  = manager.Value('f', 1.0)
    shared_camera_nx        = manager.Value('f', 0.5)
    shared_camera_ny        = manager.Value('f', 0.5)
    shared_fog_reset        = manager.Value('i', 0)
    shared_markers          = manager.list()                     # (nx, ny, nr, condition_idx)
    shared_shapes           = manager.list()  # List of dicts: {'type': int, 'nx': float, 'ny': float, 'size': int, 'condition_idx': int}
    shared_current_rotation = manager.Value('f', 0.0)  # For cone/line direction in degrees
    shared_current_shape_size = manager.Value('f', 0.08)   # normalized size ~8% of map diagonal as default

    if image_path.lower().endswith('.dndstate'):
    # Load saved state
        try:
            with open(image_path, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Update shared image path first (so both processes reload it)
            image_path = state['image_path']

            # Wait a tiny moment for image reload to propagate (optional but helps)
            pygame.time.wait(100)

            # Apply other state
            shared_zoom_multiplier.value = state.get('zoom_multiplier', 1.0)
            shared_camera_nx.value = state.get('camera_nx', 0.5)
            shared_camera_ny.value = state.get('camera_ny', 0.5)
            shared_revealed[:] = state.get('revealed', [])
            shared_markers[:] = state.get('markers', [])
            shared_shapes[:] = state.get('shapes', [])
            shared_current_rotation.value = state.get('current_rotation', 0.0)
            shared_current_shape_size.value = state.get('current_shape_size', 0.08)

            # Force fog/mask reset to apply any cleared reveals
            shared_fog_reset.value += 1
            shared_full_reveal = manager.Value('b', False) # reset full reveal trigger after load
            load_from_saved = True
            print(f"Loaded state from {image_path}")
            
        except Exception as e:
            print("State load error:", e)
            traceback.print_exc()

    control_proc = multiprocessing.Process(
        target=control_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              control_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset, shared_markers,
              shared_current_condition_idx, shared_current_marker_size,
              shared_mouse_map_nx, shared_mouse_map_ny, shared_current_shape_type,
              shared_shapes, shared_current_rotation, shared_current_shape_size,
              shared_full_reveal)
    )
    audience_proc = multiprocessing.Process(
        target=audience_window,
        args=(image_path, shared_revealed, shared_running, shared_image_path,
              audience_display, shared_zoom_multiplier, shared_camera_nx,
              shared_camera_ny, shared_fog_reset, shared_markers,
              shared_current_condition_idx, shared_current_marker_size,
              shared_mouse_map_nx, shared_mouse_map_ny, shared_current_shape_type, 
              shared_shapes, shared_current_rotation, shared_current_shape_size,
              shared_full_reveal)
    )
    
    audience_proc.start()
    control_proc.start()
    
    control_proc.join()
    shared_running.value = False
    audience_proc.join()


if __name__ == "__main__":
    # Critical for multiprocessing in frozen/PyInstaller executables on Windows
    multiprocessing.freeze_support()
    
    # Helps locate resources in one-file PyInstaller bundles
    if getattr(sys, 'frozen', False):
        os.chdir(sys._MEIPASS)
    
    main(False)