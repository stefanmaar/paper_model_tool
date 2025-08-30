import bpy

from . import operator as pmt_ops
from . import util as pmt_util


global_paper_sizes = [
    ('USER', "User defined", "User defined paper size"),
    ('A4', "A4", "International standard paper size"),
    ('A3', "A3", "International standard paper size"),
    ('US_LETTER', "Letter", "North American paper size"),
    ('US_LEGAL', "Legal", "North American paper size")
]

def label_changed(self, context):
    """The label of an island was changed"""
    # accessing properties via [..] to avoid a recursive call after the update
    self["auto_label"] = not self.label or self.label.isspace()
    pmt_util.island_item_changed(self, context)


def island_index_changed(self, context):
    """The active island was changed"""
    if context.scene.paper_model.sync_island and pmt_ops.SelectIsland.poll(context):
        bpy.ops.mesh.select_paper_island(operation='REPLACE')


def page_size_preset_changed(self, context):
    """Update the actual document size to correct values"""
    if hasattr(self, "limit_by_page") and not self.limit_by_page:
        return
    if self.page_size_preset == 'A4':
        self.output_size_x = 0.210
        self.output_size_y = 0.297
    elif self.page_size_preset == 'A3':
        self.output_size_x = 0.297
        self.output_size_y = 0.420
    elif self.page_size_preset == 'US_LETTER':
        self.output_size_x = 0.216
        self.output_size_y = 0.279
    elif self.page_size_preset == 'US_LEGAL':
        self.output_size_x = 0.216
        self.output_size_y = 0.356


class FaceList(bpy.types.PropertyGroup):
    id: bpy.props.IntProperty(name="Face ID")


class PaperModelStyle(bpy.types.PropertyGroup):
    line_styles = [
        ('SOLID', "Solid (----)", "Solid line"),
        ('DOT', "Dots (. . .)", "Dotted line"),
        ('DASH', "Short Dashes (- - -)", "Solid line"),
        ('LONGDASH', "Long Dashes (-- --)", "Solid line"),
        ('DASHDOT', "Dash-dotted (-- .)", "Solid line")
    ]
    outer_color: bpy.props.FloatVectorProperty(
        name="Outer Lines", description="Color of net outline",
        default=(0.0, 0.0, 0.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    outer_style: bpy.props.EnumProperty(
        name="Outer Lines Drawing Style", description="Drawing style of net outline",
        default='SOLID', items=line_styles)
    line_width: bpy.props.FloatProperty(
        name="Base Lines Thickness", description="Base thickness of net lines, each actual value is a multiple of this length",
        default=1e-4, min=0, soft_max=5e-3, precision=5, step=1e-2, subtype="UNSIGNED", unit="LENGTH")
    outer_width: bpy.props.FloatProperty(
        name="Outer Lines Thickness", description="Relative thickness of net outline",
        default=3, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')
    use_outbg: bpy.props.BoolProperty(
        name="Highlight Outer Lines", description="Add another line below every line to improve contrast",
        default=True)
    outbg_color: bpy.props.FloatVectorProperty(
        name="Outer Highlight", description="Color of the highlight for outer lines",
        default=(1.0, 1.0, 1.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    outbg_width: bpy.props.FloatProperty(
        name="Outer Highlight Thickness", description="Relative thickness of the highlighting lines",
        default=5, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')

    convex_color: bpy.props.FloatVectorProperty(
        name="Inner Convex Lines", description="Color of lines to be folded to a convex angle",
        default=(0.0, 0.0, 0.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    convex_style: bpy.props.EnumProperty(
        name="Convex Lines Drawing Style", description="Drawing style of lines to be folded to a convex angle",
        default='DASH', items=line_styles)
    convex_width: bpy.props.FloatProperty(
        name="Convex Lines Thickness", description="Relative thickness of concave lines",
        default=2, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')
    concave_color: bpy.props.FloatVectorProperty(
        name="Inner Concave Lines", description="Color of lines to be folded to a concave angle",
        default=(0.0, 0.0, 0.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    concave_style: bpy.props.EnumProperty(
        name="Concave Lines Drawing Style", description="Drawing style of lines to be folded to a concave angle",
        default='DASHDOT', items=line_styles)
    concave_width: bpy.props.FloatProperty(
        name="Concave Lines Thickness", description="Relative thickness of concave lines",
        default=2, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')
    freestyle_color: bpy.props.FloatVectorProperty(
        name="Freestyle Edges", description="Color of lines marked as Freestyle Edge",
        default=(0.0, 0.0, 0.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    freestyle_style: bpy.props.EnumProperty(
        name="Freestyle Edges Drawing Style", description="Drawing style of Freestyle Edges",
        default='SOLID', items=line_styles)
    freestyle_width: bpy.props.FloatProperty(
        name="Freestyle Edges Thickness", description="Relative thickness of Freestyle edges",
        default=2, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')
    use_inbg: bpy.props.BoolProperty(
        name="Highlight Inner Lines", description="Add another line below every line to improve contrast",
        default=True)
    inbg_color: bpy.props.FloatVectorProperty(
        name="Inner Highlight", description="Color of the highlight for inner lines",
        default=(1.0, 1.0, 1.0, 1.0), min=0, max=1, subtype='COLOR', size=4)
    inbg_width: bpy.props.FloatProperty(
        name="Inner Highlight Thickness", description="Relative thickness of the highlighting lines",
        default=2, min=0, soft_max=10, precision=1, step=10, subtype='FACTOR')

    sticker_color: bpy.props.FloatVectorProperty(
        name="Tabs Fill", description="Fill color of sticking tabs",
        default=(0.9, 0.9, 0.9, 1.0), min=0, max=1, subtype='COLOR', size=4)
    text_color: bpy.props.FloatVectorProperty(
        name="Text Color", description="Color of all text used in the document",
        default=(0.0, 0.0, 0.0, 1.0), min=0, max=1, subtype='COLOR', size=4)


class IslandList(bpy.types.PropertyGroup):
    faces: bpy.props.CollectionProperty(
        name="Faces", description="Faces belonging to this island", type=FaceList)
    label: bpy.props.StringProperty(
        name="Label", description="Label on this island",
        default="", update=label_changed)
    abbreviation: bpy.props.StringProperty(
        name="Abbreviation", description="Three-letter label to use when there is not enough space",
        default="", update=pmt_util.island_item_changed)
    auto_label: bpy.props.BoolProperty(
        name="Auto Label", description="Generate the label automatically",
        default=True, update=pmt_util.island_item_changed)
    auto_abbrev: bpy.props.BoolProperty(
        name="Auto Abbreviation", description="Generate the abbreviation automatically",
        default=True, update=pmt_util.island_item_changed)


class PaperModelSettings(bpy.types.PropertyGroup):
    sync_island: bpy.props.BoolProperty(
        name="Sync", description="Keep faces of the active island selected",
        default=False, update=island_index_changed)
    limit_by_page: bpy.props.BoolProperty(
        name="Limit Island Size", description="Do not create islands larger than given dimensions",
        default=False, update=page_size_preset_changed)
    page_size_preset: bpy.props.EnumProperty(
        name="Page Size", description="Maximal size of an island",
        default='A4', update=page_size_preset_changed, items=global_paper_sizes)
    output_size_x: bpy.props.FloatProperty(
        name="Width", description="Maximal width of an island",
        default=0.2, soft_min=0.105, soft_max=0.841, subtype="UNSIGNED", unit="LENGTH")
    output_size_y: bpy.props.FloatProperty(
        name="Height", description="Maximal height of an island",
        default=0.29, soft_min=0.148, soft_max=1.189, subtype="UNSIGNED", unit="LENGTH")
    use_auto_scale: bpy.props.BoolProperty(
        name="Automatic Scale", description="Scale the net automatically to fit on paper",
        default=True)
    scale: bpy.props.FloatProperty(
        name="Scale", description="Divisor of all dimensions when exporting",
        default=1, soft_min=1.0, soft_max=100.0, subtype='FACTOR', precision=1,
        update=lambda settings, _: settings.__setattr__('use_auto_scale', False))
