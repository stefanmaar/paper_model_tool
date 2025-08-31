import bpy
import bmesh
import gpu
import gpu_extras.batch as gpu_batch

shader = gpu.shader.from_builtin('UNIFORM_COLOR')
g_coords = [(0, 0, 0), (0, 1, 1)]


def draw():
    print("DRAWING")
    print("g_coords: {}".format(g_coords))
    context = bpy.context
    obj = context.active_object
    mesh = obj.data
    bm = bmesh.from_edit_mesh(obj.data)
    highlight_face_id = mesh.pmt_highlight_face_id
    print("face_id: {}".format(highlight_face_id))

    if highlight_face_id >= 0:
        sel_face = bm.faces[highlight_face_id]
        coords = [(0, 0, 0), sel_face.calc_center_median_weighted()]
        batch = gpu_batch.batch_for_shader(shader,
                                           'LINES',
                                           {"pos": coords})
        shader.uniform_float("color", (1, 1, 0, 1))
        batch.draw(shader)
