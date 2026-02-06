#!/usr/bin/env python3
"""
List all connected displays with their indices using xrandr
"""
import subprocess
import re

def get_displays_xrandr():
    try:
        output = subprocess.check_output(
            ["xrandr", "--current"],
            text=True,
            stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        print("Error running xrandr:", e.output)
        return []
    except FileNotFoundError:
        print("xrandr not found. Is it installed?")
        return []

    displays = []
    current_index = 0

    # Look for lines that start with a connector name followed by connected
    for line in output.splitlines():
        if " connected" in line:
            # Examples:
            # eDP-1 connected primary 1920x1080+0+0 ...
            # HDMI-1 connected 2560x1440+1920+0 ...
            match = re.match(r'^([^\s]+)\s+connected', line)
            if match:
                name = match.group(1)
                is_primary = " primary" in line
                displays.append({
                    "index": current_index,
                    "name": name,
                    "primary": is_primary,
                    "line": line.strip()
                })
                current_index += 1

    return displays


def main():
    displays = get_displays_xrandr()

    if not displays:
        print("No connected displays found or xrandr failed.")
        return

    print("Found displays:\n")
    for disp in displays:
        prefix = "→ " if disp["primary"] else "  "
        print(f"{prefix}[{disp['index']}]  {disp['name']}")
        print(f"    {disp['line']}")
        print()


if __name__ == "__main__":
    main()