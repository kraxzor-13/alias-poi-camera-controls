# Alias-Style POI Camera Controls

A Blender 5.2 add-on that brings Autodesk Alias-style viewport navigation to
Blender: **Alt+Shift** + mouse button, driven by a **Point of Interest
(POI)** you set by clicking on geometry, plus an **azimuth twist** for
rolling the camera around that same point.

## Why

Alias navigation revolves around a POI: you click a point on the model, and
tumble/dolly happen around *that* point rather than a fixed screen centre.
Blender's default navigation has no equivalent — this add-on adds it as a
second, independent set of bindings (`Alt+Shift+...`) that sits alongside
Blender's normal `Alt+...` navigation without replacing it.

## Controls

| Input | Action |
|---|---|
| `Alt+Shift+LMB` click | Raycasts under the cursor and sets the Point of Interest. A plain click with no drag only sets the POI — the view doesn't move. |
| `Alt+Shift+LMB` drag | **Tumble** — orbit around the POI. |
| `Alt+Shift+MMB` drag | **Track** — pan the view. |
| `Alt+Shift+RMB` drag, vertical | **Dolly** — zoom toward/away from the POI. |
| `Alt+Shift+RMB` drag, horizontal | **Azimuth twist** — roll the camera around the world-space axis through the eye and the POI, so the POI stays fixed on screen while everything else swings around it. |
| `Esc` (mid-drag) | Cancel and restore the view to before the drag started. |

The Alt+Shift+RMB drag locks to whichever axis (vertical/dolly or
horizontal/twist) dominates in the first few pixels of movement, and holds
that lock for the rest of the drag. This keeps ordinary hand tremor on the
other axis from leaking in as unwanted roll during a zoom, or unwanted zoom
during a twist.

Works in both perspective and orthographic viewports — orthographic zoom and
twist use different math internally since ortho projection has no
perspective foreshortening to drive a "move the eye" style zoom.

## Install

1. Download `alias_poi_camera.py` from this repo.
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk**, select
   the file, then enable its checkbox.

## Preferences

Under the add-on's entry in **Edit → Preferences → Add-ons**, you can invert
any of the three axes independently if the default direction doesn't match
your muscle memory:

- Invert Tumble Horizontal
- Invert Tumble Vertical
- Invert Dolly
- Invert Azimuth Twist

## Notes

- Disabled while the viewport is locked to a scene Camera (`Alt+Shift+...`
  navigation applies to free viewport navigation, not the camera object
  itself).
- A small orange crosshair marks the current POI while a drag is in
  progress.
