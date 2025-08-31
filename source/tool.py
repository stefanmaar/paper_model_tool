import bpy


class SelectIslandTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'

    # The prefix of the idname should be your add-on name.
    bl_idname = "mesh.pmt_select_island_tool"
    bl_label = "Select Island"
    bl_description = (
        "This is a tooltip\n"
        "with multiple lines"
    )
    bl_icon = "ops.generic.select_circle"
    bl_widget = None
    bl_keymap = (
        ("mesh.pmt_test_operator",
         {"type": 'LEFTMOUSE', "value": 'PRESS'},
         None),
        ("mesh.pmt_highlight_island",
         {"type": 'MOUSEMOVE', "value": 'ANY'},
         None),
    )
