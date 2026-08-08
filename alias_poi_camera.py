bl_info = {
    "name": "Alias-Style POI Camera Controls",
    "author": "Claude",
    "version": (1, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D, Alt+Shift+LMB/MMB/RMB",
    "description": (
        "Autodesk Alias-style viewport navigation: Alt+Shift+LMB "
        "raycasts onto geometry and tumbles about that Point of "
        "Interest, Alt+Shift+MMB tracks, Alt+Shift+RMB dollies."
    ),
    "category": "3D View",
}

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Quaternion
from bpy_extras import view3d_utils

# ---------------------------------------------------------------------------
# POI marker overlay (drawn only while a tumble/track/dolly is in progress)
# ---------------------------------------------------------------------------

_draw_handle = None
_poi_world = None
_current_poi = None


def _draw_poi():
    if _poi_world is None:
        return
    context = bpy.context
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    co2d = view3d_utils.location_3d_to_region_2d(region, rv3d, _poi_world)
    if co2d is None:
        return

    size = 8
    gap = 3
    coords = [
        (co2d.x - size, co2d.y), (co2d.x - gap, co2d.y),
        (co2d.x + gap, co2d.y), (co2d.x + size, co2d.y),
        (co2d.x, co2d.y - size), (co2d.x, co2d.y - gap),
        (co2d.x, co2d.y + gap), (co2d.x, co2d.y + size),
    ]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINES', {"pos": coords})
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.0)
    shader.bind()
    shader.uniform_float("color", (1.0, 0.6, 0.0, 0.9))
    batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def _show_poi_marker(world_co):
    global _poi_world, _draw_handle
    _poi_world = world_co
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_poi, (), 'WINDOW', 'POST_PIXEL')


def _hide_poi_marker():
    global _poi_world, _draw_handle
    _poi_world = None
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None


# ---------------------------------------------------------------------------
# Raycast helper
# ---------------------------------------------------------------------------

def _raycast_under_mouse(context, event):
    region = context.region
    rv3d = context.region_data
    coord = (event.mouse_region_x, event.mouse_region_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    depsgraph = context.evaluated_depsgraph_get()
    success, location, normal, index, obj, matrix = context.scene.ray_cast(
        depsgraph, origin, direction)
    return location if success else None


def _eye_location(rv3d):
    forward = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    return rv3d.view_location - forward * rv3d.view_distance


def _get_prefs(context):
    return context.preferences.addons[__name__].preferences


# ---------------------------------------------------------------------------
# Preferences (per-axis invert toggles, since "correct" feel is subjective)
# ---------------------------------------------------------------------------

class AliasPOICameraPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    invert_tumble_x: bpy.props.BoolProperty(
        name="Invert Tumble Horizontal", default=True)
    invert_tumble_y: bpy.props.BoolProperty(
        name="Invert Tumble Vertical", default=True)
    invert_dolly: bpy.props.BoolProperty(
        name="Invert Dolly", default=False)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Alt+Shift+LMB Tumble")
        row = layout.row()
        row.prop(self, "invert_tumble_x")
        row.prop(self, "invert_tumble_y")
        layout.label(text="Alt+Shift+RMB Dolly")
        layout.prop(self, "invert_dolly")


# ---------------------------------------------------------------------------
# Modal navigation operator
# ---------------------------------------------------------------------------

class VIEW3D_OT_alias_poi_navigate(bpy.types.Operator):
    """Alias-style Alt+Shift tumble / track / dolly about a Point of Interest"""
    bl_idname = "view3d.alias_poi_navigate"
    bl_label = "Alias POI Navigate"
    bl_options = {'BLOCKING'}

    mode: bpy.props.EnumProperty(
        items=[
            ('TUMBLE', "Tumble", "Orbit about the clicked Point of Interest"),
            ('TRACK', "Track", "Pan the view"),
            ('DOLLY', "Dolly", "Zoom toward/away from the current pivot"),
        ]
    )

    TUMBLE_SENSITIVITY = 0.007
    TRACK_SENSITIVITY = 1.6
    DOLLY_SENSITIVITY = 0.004

    def invoke(self, context, event):
        rv3d = context.region_data
        if rv3d is None:
            return {'CANCELLED'}
        if rv3d.view_perspective == 'CAMERA':
            self.report(
                {'WARNING'},
                "Alias POI navigation is disabled while locked to camera view",
            )
            return {'CANCELLED'}

        self._rv3d = rv3d
        self._last_mouse = Vector((event.mouse_region_x, event.mouse_region_y))

        self._start_view_location = rv3d.view_location.copy()
        self._start_view_rotation = rv3d.view_rotation.copy()
        self._start_view_distance = rv3d.view_distance

        global _current_poi

        if self.mode == 'TUMBLE':
            hit = _raycast_under_mouse(context, event)
            fallback = _current_poi if _current_poi is not None else rv3d.view_location.copy()
            poi = hit if hit is not None else fallback
            _current_poi = poi
            # Record the POI and the current eye/rotation, but do NOT touch
            # rv3d yet - assigning view_location snaps that point to the
            # exact screen centre in Blender's viewport, which would
            # re-centre the framing on every click. Instead we orbit the
            # eye and rotation directly around the (possibly off-centre)
            # POI as the mouse moves, and only then write the result back
            # via view_rotation/view_location. A plain click with no drag
            # therefore leaves the view completely untouched.
            self._poi = poi
            self._start_orbit_rotation = rv3d.view_rotation.copy()
            self._start_orbit_eye = _eye_location(rv3d)
            self._orbit_rotation = self._start_orbit_rotation.copy()
            self._orbit_eye = self._start_orbit_eye.copy()
            self._orbit_distance = rv3d.view_distance
            self._total_yaw = 0.0
            self._total_pitch = 0.0
            _show_poi_marker(poi)
        elif self.mode == 'DOLLY':
            # Dolly toward/away from the last Point of Interest set by an
            # Alt+Shift+LMB click, not the current screen centre - those
            # are generally different points once tumble no longer forces
            # view_location to the clicked point.
            poi = _current_poi if _current_poi is not None else rv3d.view_location.copy()
            self._poi = poi
            self._orbit_eye = _eye_location(rv3d)
            self._orbit_rotation = rv3d.view_rotation.copy()
            self._orbit_distance = rv3d.view_distance
            _show_poi_marker(poi)

        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        rv3d = self._rv3d
        region = context.region

        if event.type == 'MOUSEMOVE':
            cur = Vector((event.mouse_region_x, event.mouse_region_y))
            delta = cur - self._last_mouse
            self._last_mouse = cur

            if self.mode == 'TUMBLE':
                self._tumble(context, rv3d, delta)
            elif self.mode == 'TRACK':
                self._track(rv3d, region, delta)
            elif self.mode == 'DOLLY':
                self._dolly(context, rv3d, delta)

            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        release_button = {
            'TUMBLE': 'LEFTMOUSE',
            'TRACK': 'MIDDLEMOUSE',
            'DOLLY': 'RIGHTMOUSE',
        }[self.mode]

        if event.type == release_button and event.value == 'RELEASE':
            self._finish(context)
            return {'FINISHED'}

        if event.type == 'ESC':
            rv3d.view_location = self._start_view_location
            rv3d.view_rotation = self._start_view_rotation
            rv3d.view_distance = self._start_view_distance
            self._finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _finish(self, context):
        _hide_poi_marker()
        context.area.tag_redraw()

    def _tumble(self, context, rv3d, delta):
        prefs = _get_prefs(context)
        sx = -1.0 if prefs.invert_tumble_x else 1.0
        sy = -1.0 if prefs.invert_tumble_y else 1.0
        # Camera orbits around the POI in the direction of the drag (the
        # object appears to turn away from the cursor) - the standard
        # Alias/Maya/Blender tumble convention.
        self._total_yaw += sx * delta.x * self.TUMBLE_SENSITIVITY
        self._total_pitch += -sy * delta.y * self.TUMBLE_SENSITIVITY

        # Rebuild the rotation from the accumulated yaw/pitch TOTALS
        # against the frozen drag-start orientation every frame, rather
        # than repeatedly multiplying the previous frame's result by a
        # small incremental step. Chaining hundreds of quaternion
        # products across a sustained drag compounds floating point
        # rounding into a slow horizon roll ("drift"); recomputing fresh
        # from fixed start data each frame does not accumulate error.
        yaw_q = Quaternion((0.0, 0.0, 1.0), self._total_yaw)
        yawed = (yaw_q @ self._start_orbit_rotation).normalized()

        right = yawed @ Vector((1.0, 0.0, 0.0))
        pitch_q = Quaternion(right, self._total_pitch)

        self._orbit_rotation = (pitch_q @ yawed).normalized()
        delta_q = pitch_q @ yaw_q
        self._orbit_eye = self._poi + delta_q @ (self._start_orbit_eye - self._poi)

        forward = self._orbit_rotation @ Vector((0.0, 0.0, -1.0))
        rv3d.view_rotation = self._orbit_rotation
        rv3d.view_location = self._orbit_eye + forward * self._orbit_distance

    def _track(self, rv3d, region, delta):
        scale = rv3d.view_distance / max(region.width, 1) * self.TRACK_SENSITIVITY
        right = rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))
        up = rv3d.view_rotation @ Vector((0.0, 1.0, 0.0))
        rv3d.view_location += (-right * delta.x + -up * delta.y) * scale

    def _dolly(self, context, rv3d, delta):
        prefs = _get_prefs(context)
        sz = -1.0 if prefs.invert_dolly else 1.0
        factor = max(0.02, 1.0 - sz * delta.y * self.DOLLY_SENSITIVITY)
        forward = self._orbit_rotation @ Vector((0.0, 0.0, -1.0))

        if rv3d.view_perspective == 'ORTHO':
            # Orthographic projection has no foreshortening, so translating
            # the eye along the view axis (the PERSP approach below) is
            # invisible - zoom has to scale view_distance directly, since
            # that's what actually drives the ortho frustum width. To still
            # converge on the POI rather than the screen centre, project
            # the POI onto the current view plane and slide the pivot
            # toward it by the same fraction the view is zooming in.
            rv3d.view_distance = max(1e-4, rv3d.view_distance * factor)
            poi_on_plane = self._poi - forward * forward.dot(self._poi - rv3d.view_location)
            rv3d.view_location = rv3d.view_location.lerp(poi_on_plane, 1.0 - factor)
        else:
            # Move the eye toward/away from the POI directly, rather than
            # just shrinking view_distance (which zooms toward the screen
            # centre, not necessarily the POI).
            self._orbit_eye = self._poi + (self._orbit_eye - self._poi) * factor
            rv3d.view_location = self._orbit_eye + forward * self._orbit_distance


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (AliasPOICameraPreferences, VIEW3D_OT_alias_poi_navigate)
addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')

        kmi = km.keymap_items.new(
            VIEW3D_OT_alias_poi_navigate.bl_idname, 'LEFTMOUSE', 'PRESS',
            alt=True, shift=True)
        kmi.properties.mode = 'TUMBLE'
        addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new(
            VIEW3D_OT_alias_poi_navigate.bl_idname, 'MIDDLEMOUSE', 'PRESS',
            alt=True, shift=True)
        kmi.properties.mode = 'TRACK'
        addon_keymaps.append((km, kmi))

        kmi = km.keymap_items.new(
            VIEW3D_OT_alias_poi_navigate.bl_idname, 'RIGHTMOUSE', 'PRESS',
            alt=True, shift=True)
        kmi.properties.mode = 'DOLLY'
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
