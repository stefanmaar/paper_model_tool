# Paper Model Tool is based on io_export_paper_model extension.
# https://projects.blender.org/extensions/io_export_paper_model
#
# SPDX-FileCopyrightText: `Adam Dominec <adominec@gmail.com>`
#
# SPDX-License-Identifier: GPL-2.0-or-later

## Code structure
# This file consists of several components, in this order:
# * Unfolding and baking
# * Export (SVG or PDF)
# * User interface
# During the unfold process, the mesh is mirrored into a 2D structure: UVFace, UVEdge, UVVertex.

# Task: split into four files (SVG and PDF separately)
# * does any portion of baking belong into the export module?
# * sketch out the code for GCODE and two-sided export

# TODO:
# QuickSweepline is very much broken -- it throws GeometryError for all nets > ~15 faces
# rotate islands to minimize area -- and change that only if necessary to fill the page size

# check conflicts in island naming and either:
# * append a number to the conflicting names or
# * enumerate faces uniquely within all islands of the same name (requires a check that both label and abbr. equals)


if "bpy" not in locals():
    import bpy
    from . import draw as pmt_draw
    from . import operator as pmt_operator
    from . import properties as pmt_props
    from . import panel as pmt_panel
    from . import preferences as pmt_prefs
    from . import tool as pmt_tool
else:
    import importlib
    importlib.reload(locals()["pmt_draw"])
    importlib.reload(locals()["pmt_operator"])
    importlib.reload(locals()["pmt_props"])
    importlib.reload(locals()["pmt_panel"])
    importlib.reload(locals()["pmt_prefs"])
    importlib.reload(locals()["pmt_tool"])


def menu_func_export(self, context):
    self.layout.operator("export_mesh.paper_model", text="Paper Model (.pdf/.svg)")


def menu_func_unfold(self, context):
    self.layout.operator("mesh.unfold", text="Unfold")
    

module_classes = (
    pmt_operator.Unfold,
    pmt_operator.ExportPaperModel,
    pmt_operator.ClearAllSeams,
    pmt_operator.SelectIsland,
    pmt_operator.InitializeGlueFlaps,
    pmt_operator.HighlightIsland,
    pmt_operator.TestOperator,
    pmt_props.FaceList,
    pmt_props.IslandList,
    pmt_props.PaperModelSettings,
    pmt_panel.DATA_PT_paper_model_islands,
    pmt_panel.VIEW3D_PT_paper_model_tools,
    pmt_panel.VIEW3D_PT_glue_flaps_panel,
    pmt_panel.VIEW3D_PT_paper_model_settings,
    pmt_prefs.PaperAddonPreferences,
)


def register():
    bpy.utils.register_class(pmt_props.PaperModelStyle)
    for cls in module_classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.paper_model = bpy.props.PointerProperty(
        name="Paper Model",
        description="Settings of the Export Paper Model script",
        type=pmt_props.PaperModelSettings, options={'SKIP_SAVE'})
    
    bpy.types.Mesh.paper_island_list = bpy.props.CollectionProperty(
        name="Island List", type=pmt_props.IslandList)
    
    bpy.types.Mesh.paper_island_index = bpy.props.IntProperty(
        name="Island List Index",
        default=-1, min=-1, max=100, options={'SKIP_SAVE'},
        update=pmt_props.island_index_changed)

    bpy.types.Mesh.pmt_highlight_face_id = bpy.props.IntProperty(
        name = "Highlight Face Index",
        default = -1,
        options = {'SKIP_SAVE'})
        
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.VIEW3D_MT_edit_mesh.prepend(menu_func_unfold)
    # Force an update on the panel category properties
    #prefs = bpy.context.preferences.addons[__name__].preferences
    #prefs.unfold_category = prefs.unfold_category
    #prefs.export_category = prefs.export_category

    bpy.utils.register_tool(pmt_tool.SelectIslandTool,
                            after = {"builtin.scale_cage"},
                            separator = True,
                            group = True)

    bpy.types.SpaceView3D.draw_handler_add(pmt_draw.draw,
                                           (),
                                           'WINDOW',
                                           'POST_VIEW')


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.VIEW3D_MT_edit_mesh.remove(menu_func_unfold)
    for cls in reversed(module_classes):
        bpy.utils.unregister_class(cls)
    bpy.utils.unregister_tool(pmt_tool.SelectIslandTool)


if __name__ == "__main__":
    register()
