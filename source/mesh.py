import bpy
import itertools as itt
import mathutils as mu
import os.path

from . import edge as pmt_edge
from . import island as pmt_island
from . import export as pmt_export
from . import util as pmt_util


class Mesh:
    """Wrapper for Bpy Mesh"""

    def __init__(self, bmesh, matrix):
        self.data = bmesh
        self.matrix = matrix.to_3x3()
        self.looptex = bmesh.loops.layers.uv.new("Unfolded")
        self.edges = {bmedge: pmt_edge.Edge(bmedge) for bmedge in bmesh.edges}
        self.islands = list()
        self.pages = list()
        for edge in self.edges.values():
            edge.choose_main_faces()
            if edge.main_faces:
                edge.calculate_angle()
        self.copy_freestyle_marks()

    def delete_uvmap(self):
        self.data.loops.layers.uv.remove(self.looptex) if self.looptex else None

    def copy_freestyle_marks(self):
        # NOTE: this is a workaround for NotImplementedError on bmesh.edges.layers.freestyle
        mesh = bpy.data.meshes.new("unfolder_temp")
        self.data.to_mesh(mesh)
        for bmedge, edge in self.edges.items():
            edge.freestyle = mesh.edges[bmedge.index].use_freestyle_mark
        bpy.data.meshes.remove(mesh)

    def mark_cuts(self):
        for bmedge, edge in self.edges.items():
            if edge.is_main_cut and not bmedge.is_boundary:
                bmedge.seam = True

    def check_correct(self, epsilon=1e-6):
        """Check for invalid geometry"""
        def is_twisted(face):
            if len(face.verts) <= 3:
                return False
            center = face.calc_center_median()
            plane_d = center.dot(face.normal)
            diameter = max((center - vertex.co).length for vertex in face.verts)
            threshold = 0.01 * diameter
            return any(abs(v.co.dot(face.normal) - plane_d) > threshold for v in face.verts)

        null_edges = {e for e in self.edges.keys() if e.calc_length() < epsilon and e.link_faces}
        null_faces = {f for f in self.data.faces if f.calc_area() < epsilon}
        twisted_faces = {f for f in self.data.faces if is_twisted(f)}
        inverted_scale = self.matrix.determinant() <= 0
        if not (null_edges or null_faces or twisted_faces or inverted_scale):
            return True
        if inverted_scale:
            raise pmt_util.PmtError(
                "The object is flipped inside-out.\n"
                "You can use Object -> Apply -> Scale to fix it. Export failed.")
        disease = [("Remove Doubles", null_edges or null_faces), ("Triangulate", twisted_faces)]
        cure = " and ".join(s for s, k in disease if k)
        raise pmt_util.PmtError(
            "The model contains:\n" +
            (" {} zero-length edge(s)\n".format(len(null_edges)) if null_edges else "") +
            (" {} zero-area face(s)\n".format(len(null_faces)) if null_faces else "") +
            (" {} twisted polygon(s)\n".format(len(twisted_faces)) if twisted_faces else "") +
            "The offenders are selected and you can use {} to fix them. Export failed.".format(cure),
            {"verts": set(), "edges": null_edges, "faces": null_faces | twisted_faces}, self.data)


    def pmt_generate_cuts(self, page_size, priority_effect):
        """Cut the mesh so that it can be unfolded to a flat net."""
        normal_matrix = self.matrix.inverted().transposed()
        islands = {pmt_island.Island(self, face, self.matrix, normal_matrix) for face in self.data.faces}
        uvfaces = {face: uvface for cur_island in islands for face, uvface in cur_island.faces.items()}
        uvedges = {loop: uvedge for cur_island in islands for loop, uvedge in cur_island.edges.items()}
        for loop, uvedge in uvedges.items():
            self.edges[loop.edge].uvedges.append(uvedge)
        # check for edges that are cut permanently
        edges = [edge for edge in self.edges.values() if not edge.force_cut and edge.main_faces]

        if edges:
            average_length = sum(edge.vector.length for edge in edges) / len(edges)
            for edge in edges:
                edge.generate_priority(priority_effect, average_length)
            edges.sort(reverse=False, key=lambda edge: edge.priority)
            for edge in edges:
                if not edge.vector:
                    continue
                edge_a, edge_b = (uvedges[l] for l in edge.main_faces)
                old_island = pmt_edge.join_island(edge_a, edge_b, size_limit=page_size)
                if old_island:
                    islands.remove(old_island)

        self.islands = sorted(islands, reverse=True, key=lambda island: len(island.faces))

        return True

    
    def generate_cuts(self, page_size, priority_effect):
        """Cut the mesh so that it can be unfolded to a flat net."""
        normal_matrix = self.matrix.inverted().transposed()
        islands = {pmt_island.Island(self, face, self.matrix, normal_matrix) for face in self.data.faces}
        uvfaces = {face: uvface for cur_island in islands for face, uvface in cur_island.faces.items()}
        uvedges = {loop: uvedge for cur_island in islands for loop, uvedge in cur_island.edges.items()}
        for loop, uvedge in uvedges.items():
            self.edges[loop.edge].uvedges.append(uvedge)
        # check for edges that are cut permanently
        edges = [edge for edge in self.edges.values() if not edge.force_cut and edge.main_faces]

        if edges:
            average_length = sum(edge.vector.length for edge in edges) / len(edges)
            for edge in edges:
                edge.generate_priority(priority_effect, average_length)
            edges.sort(reverse=False, key=lambda edge: edge.priority)
            for edge in edges:
                if not edge.vector:
                    continue
                edge_a, edge_b = (uvedges[l] for l in edge.main_faces)
                old_island = pmt_edge.join_island(edge_a, edge_b, size_limit=page_size)
                if old_island:
                    islands.remove(old_island)

        self.islands = sorted(islands, reverse=True, key=lambda island: len(island.faces))

        for edge in self.edges.values():
            # some edges did not know until now whether their angle is convex or concave
            if edge.main_faces and (uvfaces[edge.main_faces[0].face].flipped or uvfaces[edge.main_faces[1].face].flipped):
                edge.calculate_angle()
            # ensure that the order of faces corresponds to the order of uvedges
            if edge.main_faces:
                reordered = [None, None]
                for uvedge in edge.uvedges:
                    try:
                        index = edge.main_faces.index(uvedge.loop)
                        reordered[index] = uvedge
                    except ValueError:
                        reordered.append(uvedge)
                edge.uvedges = reordered

        for island in self.islands:
            # if the normals are ambiguous, flip them so that there are more convex edges than concave ones
            if any(uvface.flipped for uvface in island.faces.values()):
                island_edges = {self.edges[uvedge.edge] for uvedge in island.edges}
                balance = sum((+1 if edge.angle > 0 else -1) for edge in island_edges if not edge.is_cut(uvedge.uvface.face))
                if balance < 0:
                    island.is_inside_out = True

            # construct a linked list from each island's boundary
            # uvedge.neighbor_right is clockwise = forward = via uvedge.vb if not uvface.flipped
            neighbor_lookup, conflicts = dict(), dict()
            for uvedge in island.boundary:
                uvvertex = uvedge.va if uvedge.uvface.flipped else uvedge.vb
                if uvvertex not in neighbor_lookup:
                    neighbor_lookup[uvvertex] = uvedge
                else:
                    if uvvertex not in conflicts:
                        conflicts[uvvertex] = [neighbor_lookup[uvvertex], uvedge]
                    else:
                        conflicts[uvvertex].append(uvedge)

            for uvedge in island.boundary:
                uvvertex = uvedge.vb if uvedge.uvface.flipped else uvedge.va
                if uvvertex not in conflicts:
                    # using the 'get' method so as to handle single-connected vertices properly
                    uvedge.neighbor_right = neighbor_lookup.get(uvvertex, uvedge)
                    uvedge.neighbor_right.neighbor_left = uvedge
                else:
                    conflicts[uvvertex].append(uvedge)

            # resolve merged vertices with more boundaries crossing
            def direction_to_float(vector):
                return (1 - vector.x/vector.length) if vector.y > 0 else (vector.x/vector.length - 1)
            for uvvertex, uvedges in conflicts.items():
                def is_inwards(uvedge):
                    return uvedge.uvface.flipped == (uvedge.va is uvvertex)

                def uvedge_sortkey(uvedge):
                    if is_inwards(uvedge):
                        return direction_to_float(uvedge.va.co - uvedge.vb.co)
                    else:
                        return direction_to_float(uvedge.vb.co - uvedge.va.co)

                uvedges.sort(key=uvedge_sortkey)
                for right, left in (
                        zip(uvedges[:-1:2], uvedges[1::2]) if is_inwards(uvedges[0])
                        else zip([uvedges[-1]] + uvedges[1::2], uvedges[:-1:2])):
                    left.neighbor_right = right
                    right.neighbor_left = left
        return True

    def generate_stickers(self, default_width, do_create_numbers=True):
        """Add sticker faces where they are needed."""
        def uvedge_priority(uvedge):
            """Returns whether it is a good idea to stick something on this edge's face"""
            # TODO: it should take into account overlaps with faces and with other stickers
            face = uvedge.uvface.face
            return face.calc_area() / face.calc_perimeter()

        def add_sticker(uvedge, index, target_uvedge):
            uvedge.sticker = pmt_export.Sticker(uvedge, default_width, index, target_uvedge)
            uvedge.uvface.island.add_marker(uvedge.sticker)

        def is_index_obvious(uvedge, target):
            if uvedge in (target.neighbor_left, target.neighbor_right):
                return True
            if uvedge.neighbor_left.loop.edge is target.neighbor_right.loop.edge and uvedge.neighbor_right.loop.edge is target.neighbor_left.loop.edge:
                return True
            return False

        for edge in self.edges.values():
            index = None
            if edge.is_main_cut and len(edge.uvedges) >= 2 and edge.vector.length_squared > 0:
                target, source = edge.uvedges[:2]
                if uvedge_priority(target) < uvedge_priority(source):
                    target, source = source, target
                target_island = target.uvface.island
                if do_create_numbers:
                    for uvedge in [source] + edge.uvedges[2:]:
                        if not is_index_obvious(uvedge, target):
                            # it will not be clear to see that these uvedges should be sticked together
                            # So, create an arrow and put the index on all stickers
                            target_island.sticker_numbering += 1
                            index = str(target_island.sticker_numbering)
                            if pmt_util.is_upsidedown_wrong(index):
                                index += "."
                            target_island.add_marker(pmt_export.Arrow(target, default_width, index))
                            break
                add_sticker(source, index, target)
            elif len(edge.uvedges) > 2:
                target = edge.uvedges[0]
            if len(edge.uvedges) > 2:
                for source in edge.uvedges[2:]:
                    add_sticker(source, index, target)

    def generate_numbers_alone(self, size):
        global_numbering = 0
        for edge in self.edges.values():
            if edge.is_main_cut and len(edge.uvedges) >= 2:
                global_numbering += 1
                index = str(global_numbering)
                if pmt_util.is_upsidedown_wrong(index):
                    index += "."
                for uvedge in edge.uvedges:
                    uvedge.uvface.island.add_marker(pmt_export.NumberAlone(uvedge, index, size))

    def enumerate_islands(self):
        for num, island in enumerate(self.islands, 1):
            island.number = num
            island.generate_label()

    def scale_islands(self, scale):
        for island in self.islands:
            vertices = set(island.vertices.values())
            for point in itt.chain((vertex.co for vertex in vertices), island.fake_vertices):
                point *= scale

    def finalize_islands(self, cage_size, title_height=0):
        for island in self.islands:
            if title_height:
                island.title = "[{}] {}".format(island.abbreviation, island.label)
            points = [vertex.co for vertex in set(island.vertices.values())] + island.fake_vertices
            angle, _ = pmt_util.cage_fit(points, (cage_size.y - title_height) / cage_size.x)
            rot = mu.Matrix.Rotation(angle, 2)
            for point in points:
                point.rotate(rot)
            for marker in island.markers:
                marker.rot = rot @ marker.rot
            bottom_left = mu.Vector((min(v.x for v in points), min(v.y for v in points) - title_height))
            # DEBUG
            # top_right = mu.Vector((max(v.x for v in points), max(v.y for v in points) - title_height))
            # print(f"fitted aspect: {(top_right.y - bottom_left.y) / (top_right.x - bottom_left.x)}")
            for point in points:
                point -= bottom_left
            island.bounding_box = mu.Vector((max(v.x for v in points), max(v.y for v in points)))

    def largest_island_ratio(self, cage_size):
        return max(i / p for island in self.islands for (i, p) in zip(island.bounding_box, cage_size))

    def fit_islands(self, cage_size):
        """Move islands so that they fit onto pages, based on their bounding boxes"""

        def try_emplace(island, page_islands, stops_x, stops_y, occupied_cache):
            """Tries to put island to each pair from stops_x, stops_y
            and checks if it overlaps with any islands present on the page.
            Returns True and positions the given island on success."""
            bbox_x, bbox_y = island.bounding_box.xy
            for x in stops_x:
                if x + bbox_x > cage_size.x:
                    continue
                for y in stops_y:
                    if y + bbox_y > cage_size.y or (x, y) in occupied_cache:
                        continue
                    for i, obstacle in enumerate(page_islands):
                        # if this obstacle overlaps with the island, try another stop
                        if (x + bbox_x > obstacle.pos.x and
                                obstacle.pos.x + obstacle.bounding_box.x > x and
                                y + bbox_y > obstacle.pos.y and
                                obstacle.pos.y + obstacle.bounding_box.y > y):
                            if x >= obstacle.pos.x and y >= obstacle.pos.y:
                                occupied_cache.add((x, y))
                            # just a stupid heuristic to make subsequent searches faster
                            if i > 0:
                                page_islands[1:i+1] = page_islands[:i]
                                page_islands[0] = obstacle
                            break
                    else:
                        # if no obstacle called break, this position is okay
                        island.pos.xy = x, y
                        page_islands.append(island)
                        stops_x.append(x + bbox_x)
                        stops_y.append(y + bbox_y)
                        return True
            return False

        def drop_portion(stops, border, divisor):
            stops.sort()
            # distance from left neighbor to the right one, excluding the first stop
            distances = [right - left for left, right in zip(stops, itt.chain(stops[2:], [border]))]
            quantile = sorted(distances)[len(distances) // divisor]
            return [stop for stop, distance in zip(stops, itt.chain([quantile], distances)) if distance >= quantile]

        if any(island.bounding_box.x > cage_size.x or island.bounding_box.y > cage_size.y for island in self.islands):
            raise pmt_util.PmtError(
                "An island is too big to fit onto page of the given size. "
                "Either downscale the model or find and split that island manually.\n"
                "Export failed, sorry.")
        # sort islands by their diagonal... just a guess
        remaining_islands = sorted(self.islands, reverse=True, key=lambda island: island.bounding_box.length_squared)
        page_num = 1  # TODO delete me

        while remaining_islands:
            # create a new page and try to fit as many islands onto it as possible
            page = pmt_island.Page(page_num)
            page_num += 1
            occupied_cache = set()
            stops_x, stops_y = [0], [0]
            for island in remaining_islands:
                try_emplace(island, page.islands, stops_x, stops_y, occupied_cache)
                # if overwhelmed with stops, drop a quarter of them
                if len(stops_x)**2 > 4 * len(self.islands) + 100:
                    stops_x = drop_portion(stops_x, cage_size.x, 4)
                    stops_y = drop_portion(stops_y, cage_size.y, 4)
            remaining_islands = [island for island in remaining_islands if island not in page.islands]
            self.pages.append(page)

    def save_uv(self, cage_size=mu.Vector((1, 1)), separate_image=False):
        if separate_image:
            for island in self.islands:
                island.save_uv_separate(self.looptex)
        else:
            for island in self.islands:
                island.save_uv(self.looptex, cage_size)

    def save_image(self, page_size_pixels: mu.Vector, filename):
        for page in self.pages:
            image = pmt_util.create_blank_image("Page {}".format(page.name), page_size_pixels, alpha=1)
            image.filepath_raw = page.image_path = "{}_{}.png".format(filename, page.name)
            faces = [face for island in page.islands for face in island.faces]
            self.bake(faces, image)
            image.save()
            image.user_clear()
            bpy.data.images.remove(image)

    def save_separate_images(self, scale, filepath, embed=None):
        for i, island in enumerate(self.islands):
            image_name = "Island {}".format(i)
            image = pmt_util.create_blank_image(image_name, island.bounding_box * scale, alpha=0)
            self.bake(island.faces.keys(), image)
            if embed:
                island.embedded_image = embed(image)
            else:
                from os import makedirs
                image_dir = filepath
                makedirs(image_dir, exist_ok=True)
                image_path = os.path.join(image_dir, "island{}.png".format(i))
                image.filepath_raw = image_path
                image.save()
                island.image_path = image_path
            image.user_clear()
            bpy.data.images.remove(image)

    def bake(self, faces, image):
        if not self.looptex:
            raise pmt_util.PmtError("The mesh has no UV Map slots left. Either delete a UV Map or export the net without textures.")
        ob = bpy.context.active_object
        me = ob.data
        # in Cycles, the image for baking is defined by the active Image Node
        temp_nodes = dict()
        for mat in me.materials:
            mat.use_nodes = True
            img = mat.node_tree.nodes.new('ShaderNodeTexImage')
            img.image = image
            temp_nodes[mat] = img
            mat.node_tree.nodes.active = img
        # move all excess faces to negative numbers (that is the only way to disable them)
        ignored_uvs = [loop[self.looptex].uv for f in self.data.faces if f not in faces for loop in f.loops]
        for uv in ignored_uvs:
            uv *= -1
        bake_type = bpy.context.scene.cycles.bake_type
        sta = bpy.context.scene.render.bake.use_selected_to_active
        try:
            ob.update_from_editmode()
            me.uv_layers.active = me.uv_layers[self.looptex.name]
            bpy.ops.object.bake(type=bake_type, margin=1, use_selected_to_active=sta, cage_extrusion=100, use_clear=False)
        except RuntimeError as e:
            raise pmt_util.PmtError(*e.args)
        finally:
            for mat, node in temp_nodes.items():
                mat.node_tree.nodes.remove(node)
        for uv in ignored_uvs:
            uv *= -1

    def pmt_set_face_attributes(self):
        ''' Set the unfold attributes of the mesh face.
        '''
    
        for cur_island in self.islands:
            print("--- Island ---")
            print(cur_island.label)
            #print(cur_island.faces)
            #print(cur_island.edges)

            # The island number containing the face.
            island_num_layer = self.data.faces.layers.int.get('island_num')
            for cur_face, cur_uv_faces in cur_island.faces.items():
                #print(cur_face)
                #print(cur_uv_faces)
                cur_face[island_num_layer] = cur_island.number


    def pmt_set_edge_attributes(self):
        ''' Set the unfold attributes of the mesh edges.
        '''
        for cur_island in self.islands:
            boundary_layer = self.data.edges.layers.float_vector.get('pmt_boundary_island')

            if cur_island.number == 5:
                pass

            outer_edges = set(cur_island.boundary)
            for cur_boundary_uvedge in outer_edges:
                cur_boundary_edge = cur_boundary_uvedge.loop.edge
                cur_vec = cur_boundary_edge[boundary_layer]
                if cur_vec[0] == -1:
                    cur_vec[0] = cur_island.number
                elif (cur_vec[0] != cur_island.number) and (cur_vec[1] == -1):
                    cur_vec[1] = cur_island.number
                elif (cur_vec[0] != cur_island.number) and (cur_vec[1] != cur_island.number):
                    print("ERROR in pmt_set_edge_attributes.")
                cur_boundary_edge[boundary_layer] = cur_vec
            
        
    def pmt_init_glue_flaps(self):
        ''' Initialize the location of the glue flaps.
        '''
        def uvedge_priority(uvedge):
            """Returns whether it is a good idea to stick something on this edge's face"""
            # TODO: it should take into account overlaps with faces and with other stickers
            flap_priority = 0
            flap_face_source_layer = self.data.edges.layers.int.get('glue_flap_face_source')
            face = uvedge.uvface.face

            flap_face_source = uvedge.loop.edge[flap_face_source_layer]
            print("flap_face_source: {}; face.index: {}".format(flap_face_source, face.index))
            if (flap_face_source != -1) and (flap_face_source == face.index):
                flap_priority = 1
            elif (flap_face_source != -1) and (flap_face_source != face.index):
                flap_priority = 0
            else:
                flap_priority = face.calc_area() / face.calc_perimeter()

            print("flap_priority: {}".format(flap_priority))
            return flap_priority

        def add_sticker(uvedge, index, target_uvedge):
            uvedge.sticker = pmt_export.Sticker(uvedge, default_width, index, target_uvedge)
            uvedge.uvface.island.add_marker(uvedge.sticker)

        def is_index_obvious(uvedge, target):
            if uvedge in (target.neighbor_left, target.neighbor_right):
                return True
            if uvedge.neighbor_left.loop.edge is target.neighbor_right.loop.edge and uvedge.neighbor_right.loop.edge is target.neighbor_left.loop.edge:
                return True
            return False

        flap_island_source_layer = self.data.edges.layers.int.get('glue_flap_island_source')
        flap_island_target_layer = self.data.edges.layers.int.get('glue_flap_island_target')
        flap_face_source_layer = self.data.edges.layers.int.get('glue_flap_face_source')
        flap_face_target_layer = self.data.edges.layers.int.get('glue_flap_face_target')

        for edge in self.edges.values():
            index = None
            if edge.is_main_cut and len(edge.uvedges) >= 2 and edge.vector.length_squared > 0:
                target, source = edge.uvedges[:2]
                if uvedge_priority(target) < uvedge_priority(source):
                    target, source = source, target
                #target_island = target.uvface.island
                #if do_create_numbers:
                #    for uvedge in [source] + edge.uvedges[2:]:
                #        if not is_index_obvious(uvedge, target):
                #            # it will not be clear to see that these uvedges should be sticked together
                #            # So, create an arrow and put the index on all stickers
                #            target_island.sticker_numbering += 1
                #            index = str(target_island.sticker_numbering)
                #            if pmt_util.is_upsidedown_wrong(index):
                #                index += "."
                #            target_island.add_marker(pmt_export.Arrow(target, default_width, index))
                #            break
                #add_sticker(source, index, target)
                source.loop.edge[flap_island_source_layer] = source.uvface.island.number
                source.loop.edge[flap_island_target_layer] = target.uvface.island.number
                source.loop.edge[flap_face_source_layer] = source.uvface.face.index
                source.loop.edge[flap_face_target_layer] = target.uvface.face.index
            elif len(edge.uvedges) > 2:
                target = edge.uvedges[0]
            if len(edge.uvedges) > 2:
                for source in edge.uvedges[2:]:
                    #add_sticker(source, index, target)
                    source.loop.edge[flap_island_source_layer] = source.uvface.island.number
                    source.loop.edge[flap_island_target_layer] = target.uvface.island.number
                    source.loop.edge[flap_face_source_layer] = source.uvface.face.index
                    source.loop.edge[flap_face_target_layer] = target.uvface.face.index
