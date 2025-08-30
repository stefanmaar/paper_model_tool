import bpy


class VIEW3D_PT_paper_model_tools(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Paper'
    bl_label = "Unfold"

    def draw(self, context):
        layout = self.layout
        sce = context.scene
        obj = context.active_object
        mesh = obj.data if obj and obj.type == 'MESH' else None

        layout.operator("mesh.unfold")

        if context.mode == 'EDIT_MESH':
            row = layout.row(align=True)
            row.operator("mesh.mark_seam", text="Mark Seam").clear = False
            row.operator("mesh.mark_seam", text="Clear Seam").clear = True
        else:
            layout.operator("mesh.clear_all_seams")


class VIEW3D_PT_paper_model_settings(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Paper'
    bl_label = "Export"

    def draw(self, context):
        layout = self.layout
        sce = context.scene
        obj = context.active_object
        mesh = obj.data if obj and obj.type == 'MESH' else None

        layout.operator("export_mesh.paper_model")
        props = sce.paper_model
        layout.prop(props, "use_auto_scale")
        sub = layout.row()
        sub.active = not props.use_auto_scale
        sub.prop(props, "scale", text="Model Scale:  1/")

        layout.prop(props, "limit_by_page")
        col = layout.column()
        col.active = props.limit_by_page
        col.prop(props, "page_size_preset")
        sub = col.column(align=True)
        sub.active = props.page_size_preset == 'USER'
        sub.prop(props, "output_size_x")
        sub.prop(props, "output_size_y")


class DATA_PT_paper_model_islands(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_label = "Paper Model Islands"
    COMPAT_ENGINES = {'BLENDER_RENDER', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'}

    def draw(self, context):
        layout = self.layout
        sce = context.scene
        obj = context.active_object
        mesh = obj.data if obj and obj.type == 'MESH' else None

        layout.operator("mesh.unfold", icon='FILE_REFRESH')
        if mesh and mesh.paper_island_list:
            layout.label(
                text="1 island:" if len(mesh.paper_island_list) == 1 else
                "{} islands:".format(len(mesh.paper_island_list)))
            layout.template_list(
                'UI_UL_list', 'paper_model_island_list', mesh,
                'paper_island_list', mesh, 'paper_island_index', rows=1, maxrows=5)
            sub = layout.split(align=True)
            sub.operator("mesh.select_paper_island", text="Select").operation = 'ADD'
            sub.operator("mesh.select_paper_island", text="Deselect").operation = 'REMOVE'
            sub.prop(sce.paper_model, "sync_island", icon='UV_SYNC_SELECT', toggle=True)
            if mesh.paper_island_index >= 0:
                list_item = mesh.paper_island_list[mesh.paper_island_index]
                sub = layout.column(align=True)
                sub.prop(list_item, "auto_label")
                sub.prop(list_item, "label")
                sub.prop(list_item, "auto_abbrev")
                row = sub.row()
                row.active = not list_item.auto_abbrev
                row.prop(list_item, "abbreviation")
        else:
            layout.box().label(text="Not unfolded")
