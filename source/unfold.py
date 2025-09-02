import bpy
import bmesh
import mathutils as mu

from . import mesh as pmt_mesh
from . import util as pmt_util
from . import export as pmt_exp

default_priority_effect = {
    'CONVEX': 0.5,
    'CONCAVE': 1,
    'LENGTH': -0.05
}


class Unfolder:
    def __init__(self, ob):
        self.do_create_uvmap = False
        bm = bmesh.from_edit_mesh(ob.data)
        self.mesh = pmt_mesh.Mesh(bm, ob.matrix_world)
        self.mesh.check_correct()

    def __del__(self):
        if not self.do_create_uvmap:
            self.mesh.delete_uvmap()


    def pmt_unfold(self, cage_size=None, priority_effect=default_priority_effect, scale=1, limit_by_page=False):
        self.mesh.generate_cuts(cage_size / scale if limit_by_page and cage_size else None, priority_effect)
        self.mesh.finalize_islands(cage_size or mu.Vector((1, 1)))
        self.mesh.enumerate_islands()
        self.mesh.pmt_set_face_properties()
        
    
    def prepare(self, cage_size=None, priority_effect=default_priority_effect, scale=1, limit_by_page=False):
        """Create the islands of the net"""
        self.mesh.generate_cuts(cage_size / scale if limit_by_page and cage_size else None, priority_effect)
        self.mesh.finalize_islands(cage_size or mu.Vector((1, 1)))
        self.mesh.enumerate_islands()
        self.mesh.save_uv()

    def copy_island_names(self, island_list):
        """Copy island label and abbreviation from the best matching island in the list"""
        orig_islands = [{face.id for face in item.faces} for item in island_list]
        matching = list()
        for i, island in enumerate(self.mesh.islands):
            islfaces = {face.index for face in island.faces}
            matching.extend((len(islfaces.intersection(item)), i, j) for j, item in enumerate(orig_islands))
        matching.sort(reverse=True)
        available_new = [True for island in self.mesh.islands]
        available_orig = [True for item in island_list]
        for face_count, i, j in matching:
            if available_new[i] and available_orig[j]:
                available_new[i] = available_orig[j] = False
                self.mesh.islands[i].label = island_list[j].label
                self.mesh.islands[i].abbreviation = island_list[j].abbreviation

    def save(self, properties):
        """Export the document"""
        # Note about scale: input is directly in blender length
        # Mesh.scale_islands multiplies everything by a user-defined ratio
        # exporters (SVG or PDF) multiply everything by 1000 (output in millimeters)
        Exporter = pmt_exp.Svg if properties.file_format == 'SVG' else pmt_exp.Pdf
        filepath = properties.filepath
        extension = properties.file_format.lower()
        filepath = bpy.path.ensure_ext(filepath, "." + extension)
        # page size in meters
        page_size = mu.Vector((properties.output_size_x, properties.output_size_y))
        # printable area size in meters
        printable_size = page_size - 2 * properties.output_margin * mu.Vector((1, 1))
        unit_scale = bpy.context.scene.unit_settings.scale_length
        ppm = properties.output_dpi * 100 / 2.54  # pixels per meter

        # after this call, all dimensions will be in meters
        self.mesh.scale_islands(unit_scale/properties.scale)
        if properties.do_create_stickers:
            self.mesh.generate_stickers(properties.sticker_width, properties.do_create_numbers)
        elif properties.do_create_numbers:
            self.mesh.generate_numbers_alone(properties.sticker_width)

        text_height = properties.sticker_width if (properties.do_create_numbers and len(self.mesh.islands) > 1) else 0
        # title height must be somewhat larger that text size, glyphs go below the baseline
        self.mesh.finalize_islands(printable_size, title_height=text_height * 1.2)
        self.mesh.fit_islands(printable_size)

        if properties.output_type != 'NONE':
            # bake an image and save it as a PNG to disk or into memory
            image_packing = properties.image_packing if properties.file_format == 'SVG' else 'ISLAND_EMBED'
            use_separate_images = image_packing in ('ISLAND_LINK', 'ISLAND_EMBED')
            self.mesh.save_uv(cage_size=printable_size, separate_image=use_separate_images)

            sce = bpy.context.scene
            rd = sce.render
            bk = rd.bake
            recall = pmt_util.store_rna_properties(rd, bk, sce.cycles)
            rd.engine = 'CYCLES'
            for p in ('color', 'diffuse', 'direct', 'emit', 'glossy', 'indirect', 'transmission'):
                setattr(bk, f"use_pass_{p}", (properties.output_type != 'TEXTURE'))
            lookup = {'TEXTURE': 'DIFFUSE', 'AMBIENT_OCCLUSION': 'AO', 'RENDER': 'COMBINED', 'SELECTED_TO_ACTIVE': 'COMBINED'}
            sce.cycles.bake_type = lookup[properties.output_type]
            bk.use_selected_to_active = (properties.output_type == 'SELECTED_TO_ACTIVE')
            bk.margin, bk.cage_extrusion, bk.use_cage, bk.use_clear = 1, 10, False, False
            if properties.output_type == 'TEXTURE':
                bk.use_pass_direct, bk.use_pass_indirect, bk.use_pass_color = False, False, True
                sce.cycles.samples = 1
            else:
                sce.cycles.samples = properties.bake_samples
            if sce.cycles.bake_type == 'COMBINED':
                bk.use_pass_direct, bk.use_pass_indirect = True, True
                bk.use_pass_diffuse, bk.use_pass_glossy, bk.use_pass_transmission, bk.use_pass_emit = True, False, False, True

            if image_packing == 'PAGE_LINK':
                self.mesh.save_image(printable_size * ppm, filepath)
            elif image_packing == 'ISLAND_LINK':
                image_dir = filepath[:filepath.rfind(".")]
                self.mesh.save_separate_images(ppm, image_dir)
            elif image_packing == 'ISLAND_EMBED':
                self.mesh.save_separate_images(ppm, filepath, embed=Exporter.encode_image)

            pmt_util.apply_rna_properties(recall, rd, bk, sce.cycles)

        exporter = Exporter(properties)
        exporter.write(self.mesh, filepath)
