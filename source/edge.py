import itertools as itt
import math
import mathutils as mu

from . import util as pmt_util
from . import uv as pmt_uv


def fitting_matrix(v1, v2):
    """Get a matrix that rotates v1 to the same direction as v2"""
    return (1 / v1.length_squared) * mu.Matrix((
        (v1.x*v2.x + v1.y*v2.y, v1.y*v2.x - v1.x*v2.y),
        (v1.x*v2.y - v1.y*v2.x, v1.x*v2.x + v1.y*v2.y)))


def join_island(uvedge_a, uvedge_b, size_limit=None, epsilon=1e-6):
    """
    Try to join other island on given edge
    Returns False if they would overlap
    """

    class Intersection(Exception):
        pass

    class GeometryError(Exception):
        pass

    def is_below(self, other, correct_geometry=True):
        if self is other:
            return False
        if self.top < other.bottom:
            return True
        if other.top < self.bottom:
            return False
        if self.max.tup <= other.min.tup:
            return True
        if other.max.tup <= self.min.tup:
            return False
        self_vector = self.max.co - self.min.co
        min_to_min = other.min.co - self.min.co
        cross_b1 = self_vector.cross(min_to_min)
        cross_b2 = self_vector.cross(other.max.co - self.min.co)
        if cross_b2 < cross_b1:
            cross_b1, cross_b2 = cross_b2, cross_b1
        if cross_b2 > 0 and (cross_b1 > 0 or (cross_b1 == 0 and not self.is_uvface_upwards())):
            return True
        if cross_b1 < 0 and (cross_b2 < 0 or (cross_b2 == 0 and self.is_uvface_upwards())):
            return False
        other_vector = other.max.co - other.min.co
        cross_a1 = other_vector.cross(-min_to_min)
        cross_a2 = other_vector.cross(self.max.co - other.min.co)
        if cross_a2 < cross_a1:
            cross_a1, cross_a2 = cross_a2, cross_a1
        if cross_a2 > 0 and (cross_a1 > 0 or (cross_a1 == 0 and not other.is_uvface_upwards())):
            return False
        if cross_a1 < 0 and (cross_a2 < 0 or (cross_a2 == 0 and other.is_uvface_upwards())):
            return True
        if cross_a1 == cross_b1 == cross_a2 == cross_b2 == 0:
            if correct_geometry:
                raise GeometryError
            elif self.is_uvface_upwards() == other.is_uvface_upwards():
                raise Intersection
            return False
        if self.min.tup == other.min.tup or self.max.tup == other.max.tup:
            return cross_a2 > cross_b2
        raise Intersection

    class QuickSweepline:
        """Efficient sweepline based on binary search, checking neighbors only"""
        def __init__(self):
            self.children = list()

        def add(self, item, cmp=is_below):
            low, high = 0, len(self.children)
            while low < high:
                mid = (low + high) // 2
                if cmp(self.children[mid], item):
                    low = mid + 1
                else:
                    high = mid
            self.children.insert(low, item)

        def remove(self, item, cmp=is_below):
            index = self.children.index(item)
            self.children.pop(index)
            if index > 0 and index < len(self.children):
                # check for intersection
                if cmp(self.children[index], self.children[index-1]):
                    raise GeometryError

    class BruteSweepline:
        """Safe sweepline which checks all its members pairwise"""
        def __init__(self):
            self.children = set()

        def add(self, item, cmp=is_below):
            for child in self.children:
                if child.min is not item.min and child.max is not item.max:
                    cmp(item, child, False)
            self.children.add(item)

        def remove(self, item):
            self.children.remove(item)

    def sweep(sweepline, segments):
        """Sweep across the segments and raise an exception if necessary"""
        # careful, 'segments' may be a use-once iterator
        events_add = sorted(segments, reverse=True, key=lambda uvedge: uvedge.min.tup)
        events_remove = sorted(events_add, reverse=True, key=lambda uvedge: uvedge.max.tup)
        while events_remove:
            while events_add and events_add[-1].min.tup <= events_remove[-1].max.tup:
                sweepline.add(events_add.pop())
            sweepline.remove(events_remove.pop())

    def root_find(value, tree):
        """Find the root of a given value in a forest-like dictionary
        also updates the dictionary using path compression"""
        parent, relink = tree.get(value), list()
        while parent is not None:
            relink.append(value)
            value, parent = parent, tree.get(parent)
        tree.update(dict.fromkeys(relink, value))
        return value

    def slope_from(position):
        def slope(uvedge):
            vec = (uvedge.vb.co - uvedge.va.co) if uvedge.va.tup == position else (uvedge.va.co - uvedge.vb.co)
            return (vec.y / vec.length + 1) if ((vec.x, vec.y) > (0, 0)) else (-1 - vec.y / vec.length)
        return slope

    island_a, island_b = (e.uvface.island for e in (uvedge_a, uvedge_b))
    if island_a is island_b:
        return False
    elif len(island_b.faces) > len(island_a.faces):
        uvedge_a, uvedge_b = uvedge_b, uvedge_a
        island_a, island_b = island_b, island_a
    # check if vertices and normals are aligned correctly
    verts_flipped = uvedge_b.loop.vert is uvedge_a.loop.vert
    flipped = verts_flipped ^ uvedge_a.uvface.flipped ^ uvedge_b.uvface.flipped
    # determine rotation
    # NOTE: if the edges differ in length, the matrix will involve uniform scaling.
    # Such situation may occur in the case of twisted n-gons
    first_b, second_b = (uvedge_b.va, uvedge_b.vb) if not verts_flipped else (uvedge_b.vb, uvedge_b.va)
    if not flipped:
        rot = fitting_matrix(first_b.co - second_b.co, uvedge_a.vb.co - uvedge_a.va.co)
    else:
        flip = mu.Matrix(((-1, 0), (0, 1)))
        rot = fitting_matrix(flip @ (first_b.co - second_b.co), uvedge_a.vb.co - uvedge_a.va.co) @ flip
    trans = uvedge_a.vb.co - rot @ first_b.co
    # preview of island_b's vertices after the join operation
    phantoms = {uvvertex: pmt_uv.UVVertex(rot @ uvvertex.co + trans) for uvvertex in island_b.vertices.values()}

    # check the size of the resulting island
    if size_limit:
        points = [vert.co for vert in itt.chain(island_a.vertices.values(), phantoms.values())]
        left, right, bottom, top = (fn(co[i] for co in points) for i in (0, 1) for fn in (min, max))
        bbox_width = right - left
        bbox_height = top - bottom
        if min(bbox_width, bbox_height)**2 > size_limit.x**2 + size_limit.y**2:
            return False
        if (bbox_width > size_limit.x or bbox_height > size_limit.y) and (bbox_height > size_limit.x or bbox_width > size_limit.y):
            _, height = pmt_util.cage_fit(points, size_limit.y / size_limit.x)
            if height > size_limit.y:
                return False

    distance_limit = uvedge_a.loop.edge.calc_length() * epsilon
    # try and merge UVVertices closer than sqrt(distance_limit)
    merged_uvedges = set()
    merged_uvedge_pairs = list()

    # merge all uvvertices that are close enough using a union-find structure
    # uvvertices will be merged only in cases island_b->island_a and island_a->island_a
    # all resulting groups are merged together to a uvvertex of island_a
    is_merged_mine = False
    shared_vertices = {loop.vert for loop in itt.chain(island_a.vertices, island_b.vertices)}
    for vertex in shared_vertices:
        uvs_a = {island_a.vertices.get(loop) for loop in vertex.link_loops} - {None}
        uvs_b = {island_b.vertices.get(loop) for loop in vertex.link_loops} - {None}
        for a, b in itt.product(uvs_a, uvs_b):
            if (a.co - phantoms[b].co).length_squared < distance_limit:
                phantoms[b] = root_find(a, phantoms)
        for a1, a2 in itt.combinations(uvs_a, 2):
            if (a1.co - a2.co).length_squared < distance_limit:
                a1, a2 = (root_find(a, phantoms) for a in (a1, a2))
                if a1 is not a2:
                    phantoms[a2] = a1
                    is_merged_mine = True
        for source, target in phantoms.items():
            target = root_find(target, phantoms)
            phantoms[source] = target

    for uvedge in (itt.chain(island_a.boundary, island_b.boundary) if is_merged_mine else island_b.boundary):
        for loop in uvedge.loop.link_loops:
            partner = island_b.edges.get(loop) or island_a.edges.get(loop)
            if partner is not None and partner is not uvedge:
                paired_a, paired_b = phantoms.get(partner.vb, partner.vb), phantoms.get(partner.va, partner.va)
                if (partner.uvface.flipped ^ flipped) != uvedge.uvface.flipped:
                    paired_a, paired_b = paired_b, paired_a
                if phantoms.get(uvedge.va, uvedge.va) is paired_a and phantoms.get(uvedge.vb, uvedge.vb) is paired_b:
                    # if these two edges will get merged, add them both to the set
                    merged_uvedges.update((uvedge, partner))
                    merged_uvedge_pairs.append((uvedge, partner))
                    break

    if uvedge_b not in merged_uvedges:
        raise pmt_util.PmtError("Export failed. Please report this error, including the model if you can.")

    boundary_other = [
        pmt_uv.PhantomUVEdge(phantoms[uvedge.va], phantoms[uvedge.vb], flipped ^ uvedge.uvface.flipped)
        for uvedge in island_b.boundary if uvedge not in merged_uvedges]
    # TODO: if is_merged_mine, it might make sense to create a similar list from island_a.boundary as well

    incidence = {vertex.tup for vertex in phantoms.values()}.intersection(vertex.tup for vertex in island_a.vertices.values())
    incidence = {position: list() for position in incidence}  # from now on, 'incidence' is a dict
    for uvedge in itt.chain(boundary_other, island_a.boundary):
        if uvedge.va.co == uvedge.vb.co:
            continue
        for vertex in (uvedge.va, uvedge.vb):
            site = incidence.get(vertex.tup)
            if site is not None:
                site.append(uvedge)
    for position, segments in incidence.items():
        if len(segments) <= 2:
            continue
        segments.sort(key=slope_from(position))
        for right, left in pmt_util.pairs(segments):
            is_left_ccw = left.is_uvface_upwards() ^ (left.max.tup == position)
            is_right_ccw = right.is_uvface_upwards() ^ (right.max.tup == position)
            if is_right_ccw and not is_left_ccw and type(right) is not type(left) and right not in merged_uvedges and left not in merged_uvedges:
                return False
            if (not is_right_ccw and right not in merged_uvedges) ^ (is_left_ccw and left not in merged_uvedges):
                return False

    # check for self-intersections
    try:
        try:
            sweepline = QuickSweepline() if island_a.has_safe_geometry and island_b.has_safe_geometry else BruteSweepline()
            sweep(sweepline, (uvedge for uvedge in itt.chain(boundary_other, island_a.boundary)))
            island_a.has_safe_geometry &= island_b.has_safe_geometry
        except GeometryError:
            sweep(BruteSweepline(), (uvedge for uvedge in itt.chain(boundary_other, island_a.boundary)))
            island_a.has_safe_geometry = False
    except Intersection:
        return False

    # mark all edges that connect the islands as not cut
    for uvedge in merged_uvedges:
        island_a.mesh.edges[uvedge.loop.edge].is_main_cut = False

    # include all transformed vertices as mine
    island_a.vertices.update({loop: phantoms[uvvertex] for loop, uvvertex in island_b.vertices.items()})

    # re-link uvedges and uvfaces to their transformed locations
    for uvedge in island_b.edges.values():
        uvedge.va = phantoms[uvedge.va]
        uvedge.vb = phantoms[uvedge.vb]
        uvedge.update()
    if is_merged_mine:
        for uvedge in island_a.edges.values():
            uvedge.va = phantoms.get(uvedge.va, uvedge.va)
            uvedge.vb = phantoms.get(uvedge.vb, uvedge.vb)
    island_a.edges.update(island_b.edges)

    for uvface in island_b.faces.values():
        uvface.island = island_a
        uvface.vertices = {loop: phantoms[uvvertex] for loop, uvvertex in uvface.vertices.items()}
        uvface.flipped ^= flipped
    if is_merged_mine:
        # there may be own uvvertices that need to be replaced by phantoms
        for uvface in island_a.faces.values():
            if any(uvvertex in phantoms for uvvertex in uvface.vertices):
                uvface.vertices = {loop: phantoms.get(uvvertex, uvvertex) for loop, uvvertex in uvface.vertices.items()}
    island_a.faces.update(island_b.faces)

    island_a.boundary = [
        uvedge for uvedge in itt.chain(island_a.boundary, island_b.boundary)
        if uvedge not in merged_uvedges]

    for uvedge, partner in merged_uvedge_pairs:
        # make sure that main faces are the ones actually merged (this changes nothing in most cases)
        edge = island_a.mesh.edges[uvedge.loop.edge]
        edge.main_faces = uvedge.loop, partner.loop

    # everything seems to be OK
    return island_b


class Edge:
    """Wrapper for BPy Edge"""
    __slots__ = (
        'data', 'va', 'vb', 'main_faces', 'uvedges',
        'vector', 'angle',
        'is_main_cut', 'force_cut', 'priority', 'freestyle')

    def __init__(self, edge):
        self.data = edge
        self.va, self.vb = edge.verts
        self.vector = self.vb.co - self.va.co
        # if self.main_faces is set, then self.uvedges[:2] must correspond to self.main_faces, in their order
        # this constraint is assured at the time of finishing mesh.generate_cuts
        self.uvedges = list()

        self.force_cut = edge.seam  # such edges will always be cut
        self.main_faces = None  # two faces that may be connected in the island
        # is_main_cut defines whether the two main faces are connected
        # all the others will be assumed to be cut
        self.is_main_cut = True
        self.priority = None
        self.angle = None
        self.freestyle = False

    def choose_main_faces(self):
        """Choose two main faces that might get connected in an island"""

        def score(pair):
            return abs(pair[0].face.normal.dot(pair[1].face.normal))

        loops = self.data.link_loops
        if len(loops) == 2:
            self.main_faces = list(loops)
        elif len(loops) > 2:
            # find (with brute force) the pair of indices whose loops have the most similar normals
            self.main_faces = max(itt.combinations(loops, 2), key=score)
        if self.main_faces and self.main_faces[1].vert == self.va:
            self.main_faces = self.main_faces[::-1]

    def calculate_angle(self):
        """Calculate the angle between the main faces"""
        loop_a, loop_b = self.main_faces
        normal_a, normal_b = (l.face.normal for l in self.main_faces)
        if not normal_a or not normal_b:
            self.angle = -3  # just a very sharp angle
        else:
            s = normal_a.cross(normal_b).dot(self.vector.normalized())
            s = max(min(s, 1.0), -1.0)  # deal with rounding errors
            self.angle = math.asin(s)
            if loop_a.link_loop_next.vert != loop_b.vert or loop_b.link_loop_next.vert != loop_a.vert:
                self.angle = abs(self.angle)

    def generate_priority(self, priority_effect, average_length):
        """Calculate the priority value for cutting"""
        angle = self.angle
        if angle > 0:
            self.priority = priority_effect['CONVEX'] * angle / math.pi
        else:
            self.priority = priority_effect['CONCAVE'] * (-angle) / math.pi
        self.priority += (self.vector.length / average_length) * priority_effect['LENGTH']

    def is_cut(self, face):
        """Return False if this edge will the given face to another one in the resulting net
        (useful for edges with more than two faces connected)"""
        # Return whether there is a cut between the two main faces
        if self.main_faces and face in {loop.face for loop in self.main_faces}:
            return self.is_main_cut
        # All other faces (third and more) are automatically treated as cut
        else:
            return True

    def other_uvedge(self, this):
        """Get an uvedge of this edge that is not the given one
        causes an IndexError if case of less than two adjacent edges"""
        return self.uvedges[1] if this is self.uvedges[0] else self.uvedges[0]
