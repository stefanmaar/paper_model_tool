import mathutils as mu

from . import uv as pmt_uv
from . import util as pmt_util


class Page:
    """Container for several Islands"""
    __slots__ = ('islands', 'name', 'image_path')

    def __init__(self, num=1):
        self.islands = list()
        self.name = "page{}".format(num)  # note: this is only used in svg files naming
        self.image_path = None


class Island:
    """Part of the net to be exported"""
    __slots__ = (
        'mesh', 'faces', 'edges', 'vertices', 'fake_vertices', 'boundary', 'markers',
        'pos', 'bounding_box',
        'image_path', 'embedded_image',
        'number', 'label', 'abbreviation', 'title',
        'has_safe_geometry', 'is_inside_out',
        'sticker_numbering')

    def __init__(self, mesh, face, matrix, normal_matrix):
        """Create an Island from a single Face"""
        self.mesh = mesh
        self.faces = dict()  # face -> uvface
        self.edges = dict()  # loop -> uvedge
        self.vertices = dict()  # loop -> uvvertex
        self.fake_vertices = list()
        self.markers = list()
        self.label = None
        self.abbreviation = None
        self.title = None
        self.pos = mu.Vector((0, 0))
        self.image_path = None
        self.embedded_image = None
        self.is_inside_out = False  # swaps concave <-> convex edges
        self.has_safe_geometry = True
        self.sticker_numbering = 0

        uvface = pmt_uv.UVFace(face, self, matrix, normal_matrix)
        self.vertices.update(uvface.vertices)
        self.edges.update(uvface.edges)
        self.faces[face] = uvface
        # UVEdges on the boundary
        self.boundary = list(self.edges.values())

    def add_marker(self, marker):
        self.fake_vertices.extend(marker.bounds)
        self.markers.append(marker)

    def generate_label(self, label=None, abbreviation=None):
        """Assign a name to this island automatically"""
        abbr = abbreviation or self.abbreviation or str(self.number)
        # TODO: dots should be added in the last instant when outputting any text
        if pmt_util.is_upsidedown_wrong(abbr):
            abbr += "."
        self.label = label or self.label or "Island {}".format(self.number)
        self.abbreviation = abbr

    def save_uv(self, tex, cage_size):
        """Save UV Coordinates of all UVFaces to a given UV texture
        tex: UV Texture layer to use (BMLayerItem)
        page_size: size of the page in pixels (vector)"""
        scale_x, scale_y = 1 / cage_size.x, 1 / cage_size.y
        for loop, uvvertex in self.vertices.items():
            uv = uvvertex.co + self.pos
            loop[tex].uv = uv.x * scale_x, uv.y * scale_y

    def save_uv_separate(self, tex):
        """Save UV Coordinates of all UVFaces to a given UV texture, spanning from 0 to 1
        tex: UV Texture layer to use (BMLayerItem)
        page_size: size of the page in pixels (vector)"""
        scale_x, scale_y = 1 / self.bounding_box.x, 1 / self.bounding_box.y
        for loop, uvvertex in self.vertices.items():
            loop[tex].uv = uvvertex.co.x * scale_x, uvvertex.co.y * scale_y
