import bpy
import bmesh
import itertools as itt
import mathutils as mu
import math
import re


def store_rna_properties(*datablocks):
    return [{prop.identifier: getattr(data, prop.identifier) for prop in data.rna_type.properties if not prop.is_readonly} for data in datablocks]


def apply_rna_properties(memory, *datablocks):
    for recall, data in zip(memory, datablocks):
        for key, value in recall.items():
            setattr(data, key, value)


def is_upsidedown_wrong(name):
    """Tell if the string would get a different meaning if written upside down"""
    chars = set(name)
    mistakable = set("69NZMWpbqd")
    rotatable = set("80oOxXIl").union(mistakable)
    return chars.issubset(rotatable) and not chars.isdisjoint(mistakable)


def pairs(sequence):
    """Generate consecutive pairs throughout the given sequence; at last, it gives elements last, first."""
    i = iter(sequence)
    previous = first = next(i)
    for this in i:
        yield previous, this
        previous = this
    yield this, first


def first_letters(text):
    """Iterator over the first letter of each word"""
    for match in first_letters.pattern.finditer(text):
        yield text[match.start()]


first_letters.pattern = re.compile(r"((?<!\w)\w)|\d")


def island_item_changed(self, context):
    """The labelling of an island was changed"""
    def increment(abbrev, collisions):
        letters = "ABCDEFGHIJKLMNPQRSTUVWXYZ123456789"
        while abbrev in collisions:
            abbrev = abbrev.rstrip(letters[-1])
            abbrev = abbrev[:2] + letters[letters.find(abbrev[-1]) + 1 if len(abbrev) == 3 else 0]
        return abbrev

    # accessing properties via [..] to avoid a recursive call after the update
    island_list = context.active_object.data.paper_island_list
    if self.auto_label:
        self["label"] = ""  # avoid self-conflict
        number = 1
        while any(item.label == "Island {}".format(number) for item in island_list):
            number += 1
        self["label"] = "Island {}".format(number)
    if self.auto_abbrev:
        self["abbreviation"] = ""  # avoid self-conflict
        abbrev = "".join(first_letters(self.label))[:3].upper()
        self["abbreviation"] = increment(abbrev, {item.abbreviation for item in island_list})
    elif len(self.abbreviation) > 3:
        self["abbreviation"] = self.abbreviation[:3]
    self.name = "[{}] {} ({} {})".format(
        self.abbreviation, self.label, len(self.faces), "faces" if len(self.faces) > 1 else "face")


def cage_fit(points, aspect):
    """Find rotation for a minimum bounding box with a given aspect ratio
    returns a tuple: rotation angle, box height"""
    def guesses(polygon):
        """Yield all tentative extrema of the bounding box height wrt. polygon rotation"""
        for a, b in pairs(polygon):
            if a == b:
                continue
            direction = (b - a).normalized()
            sinx, cosx = -direction.y, direction.x
            rot = mu.Matrix(((cosx, -sinx), (sinx, cosx)))
            rot_polygon = [rot @ p for p in polygon]
            left, right = [fn(rot_polygon, key=lambda p: p.to_tuple()) for fn in (min, max)]
            bottom, top = [fn(rot_polygon, key=lambda p: p.yx.to_tuple()) for fn in (min, max)]
            horz, vert = right - left, top - bottom
            # solve (rot * a).y == (rot * b).y
            yield max(aspect * horz.x, vert.y), sinx, cosx
            # solve (rot * a).x == (rot * b).x
            yield max(horz.x, aspect * vert.y), -cosx, sinx
            # solve aspect * (rot * (right - left)).x == (rot * (top - bottom)).y
            # using substitution t = tan(rot / 2)
            q = aspect * horz.x - vert.y
            r = vert.x + aspect * horz.y
            t = ((r**2 + q**2)**0.5 - r) / q if q != 0 else 0
            t = -1 / t if abs(t) > 1 else t  # pick the positive solution
            siny, cosy = 2 * t / (1 + t**2), (1 - t**2) / (1 + t**2)
            rot = mu.Matrix(((cosy, -siny), (siny, cosy)))
            for p in rot_polygon:
                p[:] = rot @ p  # note: this also modifies left, right, bottom, top
            if left.x < right.x and bottom.y < top.y and all(left.x <= p.x <= right.x and bottom.y <= p.y <= top.y for p in rot_polygon):
                yield max(aspect * (right - left).x, (top - bottom).y), sinx*cosy + cosx*siny, cosx*cosy - sinx*siny
    polygon = [points[i] for i in mu.geometry.convex_hull_2d(points)]
    height, sinx, cosx = min(guesses(polygon))
    return math.atan2(sinx, cosx), height


def create_blank_image(image_name, dimensions, alpha=1):
    """Create a new image and assign white color to all its pixels"""
    image_name = image_name[:64]
    width, height = int(dimensions.x), int(dimensions.y)
    image = bpy.data.images.new(image_name, width, height, alpha=True)
    if image.users > 0:
        raise PmtError(
            "There is something wrong with the material of the model. "
            "Please report this on the BlenderArtists forum. Export failed.")
    image.pixels = [1, 1, 1, alpha] * (width * height)
    image.file_format = 'PNG'
    return image


class PmtError(ValueError):
    def mesh_select(self):
        if len(self.args) > 1:
            elems, bm = self.args[1:3]
            bpy.context.tool_settings.mesh_select_mode = [bool(elems[key]) for key in ("verts", "edges", "faces")]
            for elem in itt.chain(bm.verts, bm.edges, bm.faces):
                elem.select = False
            for elem in itt.chain(*elems.values()):
                elem.select_set(True)
            bmesh.update_edit_mesh(bpy.context.object.data, loop_triangles=False, destructive=False)
