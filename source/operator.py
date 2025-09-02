import bpy
import bpy_extras
import bpy_extras.view3d_utils
import bmesh
import math
import mathutils as mu

from . import properties as pmt_props
from . import unfold as pmt_unfold
from . import util as pmt_util


class Unfold(bpy.types.Operator):
    """Blender Operator: unfold the selected object."""

    bl_idname = "mesh.unfold"
    bl_label = "Unfold"
    bl_description = "Mark seams so that the mesh can be exported as a paper model"
    bl_options = {'REGISTER', 'UNDO'}
    edit: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    priority_effect_convex: bpy.props.FloatProperty(
        name="Priority Convex", description="Priority effect for edges in convex angles",
        default=pmt_unfold.default_priority_effect['CONVEX'], soft_min=-1, soft_max=10, subtype='FACTOR')
    priority_effect_concave: bpy.props.FloatProperty(
        name="Priority Concave", description="Priority effect for edges in concave angles",
        default=pmt_unfold.default_priority_effect['CONCAVE'], soft_min=-1, soft_max=10, subtype='FACTOR')
    priority_effect_length: bpy.props.FloatProperty(
        name="Priority Length", description="Priority effect of edge length",
        default=pmt_unfold.default_priority_effect['LENGTH'], soft_min=-10, soft_max=1, subtype='FACTOR')
    do_create_uvmap: bpy.props.BoolProperty(
        name="Create UVMap", description="Create a new UV Map showing the islands and page layout", default=False)
    object = None

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.active = not self.object or len(self.object.data.uv_layers) < 8
        col.prop(self.properties, "do_create_uvmap")
        layout.label(text="Edge Cutting Factors:")
        col = layout.column(align=True)
        col.label(text="Face Angle:")
        col.prop(self.properties, "priority_effect_convex", text="Convex")
        col.prop(self.properties, "priority_effect_concave", text="Concave")
        layout.prop(self.properties, "priority_effect_length", text="Edge Length")

    def execute(self, context):
        sce = bpy.context.scene
        settings = sce.paper_model
        recall_mode = context.object.mode
        bpy.ops.object.mode_set(mode='EDIT')

        self.object = context.object
        mesh = self.object.data
        bm = bmesh.from_edit_mesh(mesh)

        # Create the flap_island edge attribute.
        if 'island_num' not in mesh.attributes:
            attribute = mesh.attributes.new(name="island_num",
                                            type="INT",
                                            domain="FACE")

        flap_layer = bm.faces.layers.int.get('island_num')
        for cur_face in bm.faces:
            cur_face[flap_layer] = -1

        cage_size = mu.Vector((settings.output_size_x, settings.output_size_y))
        priority_effect = {
            'CONVEX': self.priority_effect_convex,
            'CONCAVE': self.priority_effect_concave,
            'LENGTH': self.priority_effect_length}
        try:
            unfolder = pmt_unfold.Unfolder(self.object)
            unfolder.do_create_uvmap = self.do_create_uvmap
            scale = sce.unit_settings.scale_length / settings.scale
            #unfolder.prepare(cage_size, priority_effect, scale, settings.limit_by_page)
            unfolder.pmt_unfold(cage_size, priority_effect, scale,
                                settings.limit_by_page)
            unfolder.mesh.mark_cuts()
        except pmt_util.PmtError as error:
            self.report(type={'ERROR_INVALID_INPUT'}, message=error.args[0])
            error.mesh_select()
            bpy.ops.object.mode_set(mode=recall_mode)
            return {'CANCELLED'}
        mesh = self.object.data
        mesh.update()
        if mesh.paper_island_list:
            unfolder.copy_island_names(mesh.paper_island_list)
        island_list = mesh.paper_island_list
        attributes = {item.label: (item.abbreviation, item.auto_label, item.auto_abbrev) for item in island_list}
        island_list.clear()  # remove previously defined islands
        for island in unfolder.mesh.islands:
            # add islands to UI list and set default descriptions
            list_item = island_list.add()
            # add faces' IDs to the island
            for face in island.faces:
                lface = list_item.faces.add()
                lface.id = face.index
            list_item["label"] = island.label
            list_item["abbreviation"], list_item["auto_label"], list_item["auto_abbrev"] = attributes.get(
                island.label,
                (island.abbreviation, True, True))
            pmt_util.island_item_changed(list_item, context)
            mesh.paper_island_index = -1

        del unfolder
        bpy.ops.object.mode_set(mode=recall_mode)
        return {'FINISHED'}


class ClearAllSeams(bpy.types.Operator):
    """Blender Operator: clear all seams of the active Mesh and all its unfold data"""

    bl_idname = "mesh.clear_all_seams"
    bl_label = "Clear All Seams"
    bl_description = "Clear all the seams and unfolded islands of the active object"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        ob = context.active_object
        mesh = ob.data

        for edge in mesh.edges:
            edge.use_seam = False
        mesh.paper_island_list.clear()

        return {'FINISHED'}


class ExportPaperModel(bpy.types.Operator):
    """Blender Operator: save the selected object's net and optionally bake its texture"""

    bl_idname = "export_mesh.paper_model"
    bl_label = "Export Paper Model"
    bl_description = "Export the selected object's net and optionally bake its texture"
    bl_options = {'PRESET'}

    filepath: bpy.props.StringProperty(
        name="File Path", description="Target file to save the SVG", options={'SKIP_SAVE'})
    filename: bpy.props.StringProperty(
        name="File Name", description="Name of the file", options={'SKIP_SAVE'})
    directory: bpy.props.StringProperty(
        name="Directory", description="Directory of the file", options={'SKIP_SAVE'})
    page_size_preset: bpy.props.EnumProperty(
        name="Page Size", description="Size of the exported document",
        default='A4', update=pmt_props.page_size_preset_changed, items=pmt_props.global_paper_sizes)
    output_size_x: bpy.props.FloatProperty(
        name="Page Width", description="Width of the exported document",
        default=0.210, soft_min=0.105, soft_max=0.841, subtype="UNSIGNED", unit="LENGTH")
    output_size_y: bpy.props.FloatProperty(
        name="Page Height", description="Height of the exported document",
        default=0.297, soft_min=0.148, soft_max=1.189, subtype="UNSIGNED", unit="LENGTH")
    output_margin: bpy.props.FloatProperty(
        name="Page Margin", description="Distance from page borders to the printable area",
        default=0.005, min=0, soft_max=0.1, step=0.1, subtype="UNSIGNED", unit="LENGTH")
    output_type: bpy.props.EnumProperty(
        name="Textures", description="Source of a texture for the model",
        default='NONE', items=[
            ('NONE', "No Texture", "Export the net only"),
            ('TEXTURE', "From Materials", "Render the diffuse color and all painted textures"),
            ('AMBIENT_OCCLUSION', "Ambient Occlusion", "Render the Ambient Occlusion pass"),
            ('RENDER', "Full Render", "Render the material in actual scene illumination"),
            ('SELECTED_TO_ACTIVE', "Selected to Active", "Render all selected surrounding objects as a texture")
        ])
    do_create_stickers: bpy.props.BoolProperty(
        name="Create Tabs", description="Create gluing tabs around the net (useful for paper)",
        default=True)
    do_create_numbers: bpy.props.BoolProperty(
        name="Create Numbers", description="Enumerate edges to make it clear which edges should be sticked together",
        default=True)
    sticker_width: bpy.props.FloatProperty(
        name="Tabs and Text Size", description="Width of gluing tabs and their numbers",
        default=0.005, soft_min=0, soft_max=0.05, step=0.1, subtype="UNSIGNED", unit="LENGTH")
    angle_epsilon: bpy.props.FloatProperty(
        name="Hidden Edge Angle", description="Folds with angle below this limit will not be drawn",
        default=math.pi/360, min=0, soft_max=math.pi/4, step=0.01, subtype="ANGLE", unit="ROTATION")
    output_dpi: bpy.props.FloatProperty(
        name="Resolution (DPI)", description="Resolution of images in pixels per inch",
        default=90, min=1, soft_min=30, soft_max=600, subtype="UNSIGNED")
    bake_samples: bpy.props.IntProperty(
        name="Samples", description="Number of samples to render for each pixel",
        default=64, min=1, subtype="UNSIGNED")
    file_format: bpy.props.EnumProperty(
        name="Document Format", description="File format of the exported net",
        default='PDF', items=[
            ('PDF', "PDF", "Adobe Portable Document Format 1.4"),
            ('SVG', "SVG", "W3C Scalable Vector Graphics"),
        ])
    image_packing: bpy.props.EnumProperty(
        name="Image Packing Method", description="Method of attaching baked image(s) to the SVG",
        default='ISLAND_EMBED', items=[
            ('PAGE_LINK', "Single Linked", "Bake one image per page of output and save it separately"),
            ('ISLAND_LINK', "Linked", "Bake images separately for each island and save them in a directory"),
            ('ISLAND_EMBED', "Embedded", "Bake images separately for each island and embed them into the SVG")
        ])
    scale: bpy.props.FloatProperty(
        name="Scale", description="Divisor of all dimensions when exporting",
        default=1, soft_min=1.0, soft_max=100.0, subtype='FACTOR', precision=1)
    do_create_uvmap: bpy.props.BoolProperty(
        name="Create UVMap",
        description="Create a new UV Map showing the islands and page layout",
        default=False, options={'SKIP_SAVE'})
    ui_expanded_document: bpy.props.BoolProperty(
        name="Show Document Settings Expanded",
        description="Shows the box 'Document Settings' expanded in user interface",
        default=True, options={'SKIP_SAVE'})
    ui_expanded_style: bpy.props.BoolProperty(
        name="Show Style Settings Expanded",
        description="Shows the box 'Colors and Style' expanded in user interface",
        default=False, options={'SKIP_SAVE'})
    style: bpy.props.PointerProperty(type=pmt_props.PaperModelStyle)

    unfolder = None

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def prepare(self, context):
        sce = context.scene
        self.recall_mode = context.object.mode
        bpy.ops.object.mode_set(mode='EDIT')

        self.object = context.active_object
        self.unfolder = pmt_unfold.Unfolder(self.object)
        cage_size = mu.Vector((sce.paper_model.output_size_x, sce.paper_model.output_size_y))
        unfolder_scale = sce.unit_settings.scale_length/self.scale
        self.unfolder.prepare(cage_size, scale=unfolder_scale, limit_by_page=sce.paper_model.limit_by_page)
        if sce.paper_model.use_auto_scale:
            self.scale = math.ceil(self.get_scale_ratio(sce))

    def recall(self):
        if self.unfolder:
            del self.unfolder
        bpy.ops.object.mode_set(mode=self.recall_mode)

    def invoke(self, context, event):
        self.scale = context.scene.paper_model.scale
        try:
            self.prepare(context)
        except pmt_util.PmtError as error:
            self.report(type={'ERROR_INVALID_INPUT'}, message=error.args[0])
            error.mesh_select()
            self.recall()
            return {'CANCELLED'}
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        print("ExportPaperModel operator execute")
        if not self.unfolder:
            self.prepare(context)
        self.unfolder.do_create_uvmap = self.do_create_uvmap
        try:
            if self.object.data.paper_island_list:
                self.unfolder.copy_island_names(self.object.data.paper_island_list)
            self.unfolder.save(self.properties)
            self.report({'INFO'}, "Saved a {}-page document".format(len(self.unfolder.mesh.pages)))
            return {'FINISHED'}
        except pmt_util.PmtError as error:
            self.report(type={'ERROR_INVALID_INPUT'}, message=error.args[0])
            return {'CANCELLED'}
        finally:
            self.recall()

    def get_scale_ratio(self, sce):
        margin = self.output_margin + self.sticker_width
        if min(self.output_size_x, self.output_size_y) <= 2 * margin:
            return False
        output_inner_size = mu.Vector((self.output_size_x - 2*margin, self.output_size_y - 2*margin))
        ratio = self.unfolder.mesh.largest_island_ratio(output_inner_size)
        return ratio * sce.unit_settings.scale_length / self.scale

    def draw(self, context):
        layout = self.layout
        layout.prop(self.properties, "do_create_uvmap")
        layout.prop(self.properties, "scale", text="Scale: 1/")
        scale_ratio = self.get_scale_ratio(context.scene)
        if scale_ratio > 1:
            layout.label(
                text="An island is roughly {:.1f}x bigger than page".format(scale_ratio),
                icon="ERROR")
        elif scale_ratio > 0:
            layout.label(text="Largest island is roughly 1/{:.1f} of page".format(1 / scale_ratio))

        if context.scene.unit_settings.scale_length != 1:
            layout.label(
                text="Unit scale {:.1f} makes page size etc. not display correctly".format(
                    context.scene.unit_settings.scale_length), icon="ERROR")
        box = layout.box()
        row = box.row(align=True)
        row.prop(
            self.properties, "ui_expanded_document", text="",
            icon=('TRIA_DOWN' if self.ui_expanded_document else 'TRIA_RIGHT'), emboss=False)
        row.label(text="Document Settings")

        if self.ui_expanded_document:
            box.prop(self.properties, "file_format", text="Format")
            box.prop(self.properties, "page_size_preset")
            col = box.column(align=True)
            col.active = self.page_size_preset == 'USER'
            col.prop(self.properties, "output_size_x")
            col.prop(self.properties, "output_size_y")
            box.prop(self.properties, "output_margin")
            col = box.column()
            col.prop(self.properties, "do_create_stickers")
            col.prop(self.properties, "do_create_numbers")
            col = box.column()
            col.active = self.do_create_stickers or self.do_create_numbers
            col.prop(self.properties, "sticker_width")
            box.prop(self.properties, "angle_epsilon")

            box.prop(self.properties, "output_type")
            col = box.column()
            col.active = (self.output_type != 'NONE')
            if len(self.object.data.uv_layers) >= 8:
                col.label(text="No UV slots left, No Texture is the only option.", icon='ERROR')
            elif context.scene.render.engine != 'CYCLES' and self.output_type != 'NONE':
                col.label(text="Cycles will be used for texture baking.", icon='ERROR')
            row = col.row()
            row.active = self.output_type in ('AMBIENT_OCCLUSION', 'RENDER', 'SELECTED_TO_ACTIVE')
            row.prop(self.properties, "bake_samples")
            col.prop(self.properties, "output_dpi")
            row = col.row()
            row.active = self.file_format == 'SVG'
            row.prop(self.properties, "image_packing", text="Images")

        box = layout.box()
        row = box.row(align=True)
        row.prop(
            self.properties, "ui_expanded_style", text="",
            icon=('TRIA_DOWN' if self.ui_expanded_style else 'TRIA_RIGHT'), emboss=False)
        row.label(text="Colors and Style")

        if self.ui_expanded_style:
            box.prop(self.style, "line_width", text="Default line width")
            col = box.column()
            col.prop(self.style, "outer_color")
            col.prop(self.style, "outer_width", text="Relative width")
            col.prop(self.style, "outer_style", text="Style")
            col = box.column()
            col.active = self.output_type != 'NONE'
            col.prop(self.style, "use_outbg", text="Outer Lines Highlight:")
            sub = col.column()
            sub.active = self.output_type != 'NONE' and self.style.use_outbg
            sub.prop(self.style, "outbg_color", text="")
            sub.prop(self.style, "outbg_width", text="Relative width")
            col = box.column()
            col.prop(self.style, "convex_color")
            col.prop(self.style, "convex_width", text="Relative width")
            col.prop(self.style, "convex_style", text="Style")
            col = box.column()
            col.prop(self.style, "concave_color")
            col.prop(self.style, "concave_width", text="Relative width")
            col.prop(self.style, "concave_style", text="Style")
            col = box.column()
            col.prop(self.style, "freestyle_color")
            col.prop(self.style, "freestyle_width", text="Relative width")
            col.prop(self.style, "freestyle_style", text="Style")
            col = box.column()
            col.active = self.output_type != 'NONE'
            col.prop(self.style, "use_inbg", text="Inner Lines Highlight:")
            sub = col.column()
            sub.active = self.output_type != 'NONE' and self.style.use_inbg
            sub.prop(self.style, "inbg_color", text="")
            sub.prop(self.style, "inbg_width", text="Relative width")
            col = box.column()
            col.active = self.do_create_stickers
            col.prop(self.style, "sticker_color")
            box.prop(self.style, "text_color")


class SelectIsland(bpy.types.Operator):
    """Blender Operator: select all faces of the active island"""

    bl_idname = "mesh.select_paper_island"
    bl_label = "Select Island"
    bl_description = "Select an island of the paper model net"

    operation: bpy.props.EnumProperty(
        name="Operation", description="Operation with the current selection",
        default='ADD', items=[
            ('ADD', "Add", "Add to current selection"),
            ('REMOVE', "Remove", "Remove from selection"),
            ('REPLACE', "Replace", "Select only the ")
        ])

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.mode == 'EDIT_MESH'

    def execute(self, context):
        ob = context.active_object
        me = ob.data
        bm = bmesh.from_edit_mesh(me)
        island = me.paper_island_list[me.paper_island_index]
        faces = {face.id for face in island.faces}
        edges = set()
        verts = set()
        if self.operation == 'REPLACE':
            for face in bm.faces:
                selected = face.index in faces
                face.select = selected
                if selected:
                    edges.update(face.edges)
                    verts.update(face.verts)
            for edge in bm.edges:
                edge.select = edge in edges
            for vert in bm.verts:
                vert.select = vert in verts
        else:
            selected = (self.operation == 'ADD')
            for index in faces:
                face = bm.faces[index]
                face.select = selected
                edges.update(face.edges)
                verts.update(face.verts)
            for edge in edges:
                edge.select = any(face.select for face in edge.link_faces)
            for vert in verts:
                vert.select = any(edge.select for edge in vert.link_edges)
        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
        return {'FINISHED'}


class InitializeGlueFlaps(bpy.types.Operator):
    """Initialize the glue flaps of an unfolded mesh"""

    bl_idname = "mesh.pmt_init_glue_flaps"
    bl_label = "Initialize Glue Flaps"
    bl_description = "Initialize the glue flaps of an unfolded mesh."

    def execute(self, context):
        print("Execute pmt_init_glue_flaps.")
        return {'FINISHED'}
   
    def invoke(self, context, event):
        print("Invoke pmg_init_glue_flaps.")
        print(event)
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)

        # Create the flap_island edge attribute.
        attribute = mesh.attributes.new(name="glue_flap_island",
                                        type="INT",
                                        domain="EDGE")

        flap_layer = bm.edges.layers.int.get('glue_flap_island')
        for cur_edge in bm.edges:
            cur_edge[flap_layer] = -1
        
        seam_edges = [x for x in bm.edges if x.seam]
        sel_edges = [x for x in bm.edges if x.select]
        sel_faces = [x for x in bm.faces if x.select]
        print(seam_edges)
        print(sel_edges)
        for cur_face in sel_faces:
            print(cur_face.calc_center_median_weighted())

        island_list = mesh.paper_island_list
        for k, cur_island in enumerate(island_list):
            for cur_island_edge in cur_island.edges:
                if cur_island_edge.data[flap_layer] == -1:
                    cur_island_edge.data[flap_layer] = k
        
        return {'FINISHED'}

class TestOperator(bpy.types.Operator):
    """Test Operator"""

    bl_idname = "mesh.pmt_test_operator"
    bl_label = "Test Operator"
    bl_description = "Testing blender operator"

    def execute(self, context):
        print("Hello Test Operator.")
        return {'FINISHED'}
   
    def invoke(self, context, event):
        print("Invoke in Test Operator.")
        print(event)
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        sel_edges = [x for x in bm.edges if x.select and x.seam]
        sel_faces = [x for x in bm.faces if x.select]
        for cur_face in sel_faces:
            print(cur_face.calc_center_median_weighted())
        print(sel_edges)
        return {'FINISHED'}


class HighlightIsland(bpy.types.Operator):
    """Highlight Operator"""

    bl_idname = "mesh.pmt_highlight_island"
    bl_label = "Highlight Island Operator"
    bl_description = "Testing face highlighting."

    def excute(self, context):
        print("Hello Highlighter.")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        print("Invoke in Highlighter.")
        print(event)
        
        if((context.mode != 'EDIT_MESH') or (context.space_data.type != 'VIEW_3D')):
            return{'CANCELLED'}
              
        obj = context.active_object
        print(obj)
        mesh = obj.data
        print(mesh)
        bm = bmesh.from_edit_mesh(obj.data)
        region = bpy.context.region
        region_3d = bpy.context.space_data.region_3d
        mouse_pos = [event.mouse_region_x, event.mouse_region_y]
        
        # Compute the BVHTree of the mesh.
        # This should be computed only if the mesh has changed to save resources.
        print("Computing the tree.")
        tree = mu.bvhtree.BVHTree.FromBMesh(bm)
        print("done.")
        
        # Convert 2d region mouse coordingates to 3d coordinates of the 
        # ray origin and the ray direction.
        ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region,
                                                                    region_3d,
                                                                    mouse_pos)           
        ray_direction = bpy_extras.view3d_utils.region_2d_to_vector_3d(region,
                                                                       region_3d,
                                                                       mouse_pos)
        
        #ray_origin = mathutils.Vector((0, 0, 5))
        #ray_direction = mathutils.Vector((0, 0, -1))
                
        # Translate the ray_origin coordinates to object related coordinates.
        # bvhtree.ray_cast uses object related coordinates.
        world2obj = obj.matrix_world.inverted()
        ray_origin_obj = world2obj @ ray_origin
        
        # The obj.ray_cast function is not working as expected.
        # Switched to using bvhtree.ray_cast instead.
        #raycast_res = obj.ray_cast(ray_origin, ray_direction)
        
        raycast_res = tree.ray_cast(ray_origin_obj, ray_direction)
        
        print("raycast_res: {}".format(raycast_res))
        print("ray_origin: {}".format(ray_origin))
        print("ray_origin_obj: {}".format(ray_origin_obj))
        print("ray_direction: {}".format(ray_direction))
        
        hit_face_id = raycast_res[2]
        if hit_face_id is not None:
            mesh.pmt_highlight_face_id = hit_face_id

            sel_faces = [x for x in bm.faces if x.select]
            for cur_face in sel_faces:
                print("cur_face.index: {}".format(cur_face.index))
                print("cur_face center: {}".format(cur_face.calc_center_median_weighted()))
        else:
            mesh.pmt_highlight_face_id = -1
        
        #closest_face.select = True
        #bmesh.update_edit_mesh(obj.data)
        context.area.tag_redraw()
                
        return {'FINISHED'}
    
    def modal(self, context, event):
        print("Modal in Highlighter.")
        print(event)
        return {'RUNNING_MODAL'}
