import bpy

from . import panel as pmt_panel


def factory_update_addon_category(cls, prop):
    def func(self, context):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)
        cls.bl_category = self[prop]
        bpy.utils.register_class(cls)
    return func


class PaperAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    unfold_category: bpy.props.StringProperty(
        name="Unfold Panel Category", description="Category in 3D View Toolbox where the Unfold panel is displayed",
        default="Paper", update=factory_update_addon_category(pmt_panel.VIEW3D_PT_paper_model_tools, 'unfold_category'))
    export_category: bpy.props.StringProperty(
        name="Export Panel Category", description="Category in 3D View Toolbox where the Export panel is displayed",
        default="Paper", update=factory_update_addon_category(pmt_panel.VIEW3D_PT_paper_model_settings, 'export_category'))

    def draw(self, context):
        sub = self.layout.column(align=True)
        sub.use_property_split = True
        sub.label(text="3D View Panel Category:")
        sub.prop(self, "unfold_category", text="Unfold Panel:")
        sub.prop(self, "export_category", text="Export Panel:")
