import bmesh
import mathutils as mu

from . import island as pmt_island


def z_up_matrix(n):
    """Get a rotation matrix that aligns given vector upwards."""
    b = n.xy.length
    s = n.length
    if b > 0:
        return mu.Matrix((
            (n.x*n.z/(b*s), n.y*n.z/(b*s), -b/s),
            (-n.y/b, n.x/b, 0),
            (0, 0, 0)
        ))
    else:
        # no need for rotation
        return mu.Matrix((
            (1, 0, 0),
            (0, (-1 if n.z < 0 else 1), 0),
            (0, 0, 0)
        ))


class UVVertex:
    """Vertex in 2D"""
    __slots__ = ('co', 'tup')

    def __init__(self, vector):
        self.co = vector.xy
        self.tup = tuple(self.co)


class UVEdge:
    """Edge in 2D"""
    # Every UVEdge is attached to only one UVFace
    # UVEdges are doubled as needed because they both have to point clockwise around their faces
    __slots__ = (
        'va', 'vb', 'uvface', 'loop',
        'min', 'max', 'bottom', 'top',
        'neighbor_left', 'neighbor_right', 'sticker')

    def __init__(self, vertex1: UVVertex, vertex2: UVVertex, uvface, loop):
        self.va = vertex1
        self.vb = vertex2
        self.update()
        self.uvface = uvface
        self.sticker = None
        self.loop = loop

    def update(self):
        """Update data if UVVertices have moved"""
        self.min, self.max = (self.va, self.vb) if (self.va.tup < self.vb.tup) else (self.vb, self.va)
        y1, y2 = self.va.co.y, self.vb.co.y
        self.bottom, self.top = (y1, y2) if y1 < y2 else (y2, y1)

    def is_uvface_upwards(self):
        return (self.va.tup < self.vb.tup) ^ self.uvface.flipped

    def __repr__(self):
        return "({0.va} - {0.vb})".format(self)


class PhantomUVEdge:
    """Temporary 2D Segment for calculations"""
    __slots__ = ('va', 'vb', 'min', 'max', 'bottom', 'top')

    def __init__(self, vertex1: UVVertex, vertex2: UVVertex, flip):
        self.va, self.vb = (vertex2, vertex1) if flip else (vertex1, vertex2)
        self.min, self.max = (self.va, self.vb) if (self.va.tup < self.vb.tup) else (self.vb, self.va)
        y1, y2 = self.va.co.y, self.vb.co.y
        self.bottom, self.top = (y1, y2) if y1 < y2 else (y2, y1)

    def is_uvface_upwards(self):
        return self.va.tup < self.vb.tup

    def __repr__(self):
        return "[{0.va} - {0.vb}]".format(self)


class UVFace:
    """Face in 2D"""
    __slots__ = ('vertices', 'edges', 'face', 'island', 'flipped')

    def __init__(self, face: bmesh.types.BMFace, island: pmt_island.Island, matrix=1, normal_matrix=1):
        self.face = face
        self.island = island
        self.flipped = False  # a flipped UVFace has edges clockwise

        flatten = z_up_matrix(normal_matrix @ face.normal) @ matrix
        self.vertices = {loop: UVVertex(flatten @ loop.vert.co) for loop in face.loops}
        self.edges = {loop: UVEdge(self.vertices[loop], self.vertices[loop.link_loop_next], self, loop) for loop in face.loops}
