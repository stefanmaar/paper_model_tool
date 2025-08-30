import itertools as itt
import mathutils as mu

from . import uv as pmt_uv


def init_exporter(self, properties):
    self.page_size = mu.Vector((properties.output_size_x, properties.output_size_y))
    self.style = properties.style
    margin = properties.output_margin
    self.margin = mu.Vector((margin, margin))
    self.pure_net = (properties.output_type == 'NONE')
    self.do_create_stickers = properties.do_create_stickers
    self.text_size = properties.sticker_width
    self.angle_epsilon = properties.angle_epsilon

    
class Arrow:
    """Mark in the document: an arrow denoting the number of the edge it points to"""
    __slots__ = ('bounds', 'center', 'rot', 'text', 'size')

    def __init__(self, uvedge, size, index):
        self.text = str(index)
        edge = (uvedge.vb.co - uvedge.va.co) if not uvedge.uvface.flipped else (uvedge.va.co - uvedge.vb.co)
        self.center = (uvedge.va.co + uvedge.vb.co) / 2
        self.size = size
        tangent = edge.normalized()
        cos, sin = tangent
        self.rot = mu.Matrix(((cos, -sin), (sin, cos)))
        normal = mu.Vector((sin, -cos))
        self.bounds = [self.center, self.center + (1.2 * normal + tangent) * size, self.center + (1.2 * normal - tangent) * size]


class NumberAlone:
    """Mark in the document: numbering inside the island denoting edges to be sticked"""
    __slots__ = ('bounds', 'center', 'rot', 'text', 'size')

    def __init__(self, uvedge, index, default_size=0.005):
        """Sticker is directly attached to the given UVEdge"""
        edge = (uvedge.va.co - uvedge.vb.co) if not uvedge.uvface.flipped else (uvedge.vb.co - uvedge.va.co)

        self.size = default_size
        sin, cos = edge.y / edge.length, edge.x / edge.length
        self.rot = mu.Matrix(((cos, -sin), (sin, cos)))
        self.text = index
        self.center = (uvedge.va.co + uvedge.vb.co) / 2 - self.rot @ mu.Vector((0, self.size * 1.2))
        self.bounds = [self.center]


class Sticker:
    """Mark in the document: sticker tab"""
    __slots__ = ('bounds', 'center', 'points', 'rot', 'text', 'width')

    def __init__(self, uvedge, default_width, index, other: pmt_uv.UVEdge):
        """Sticker is directly attached to the given UVEdge"""
        first_vertex, second_vertex = (uvedge.va, uvedge.vb) if not uvedge.uvface.flipped else (uvedge.vb, uvedge.va)
        edge = first_vertex.co - second_vertex.co
        sticker_width = min(default_width, edge.length / 2)
        other_first, other_second = (other.va, other.vb) if not other.uvface.flipped else (other.vb, other.va)
        other_edge = other_second.co - other_first.co

        # angle a is at vertex uvedge.va, b is at uvedge.vb
        cos_a = cos_b = 0.5
        sin_a = sin_b = 0.75**0.5
        # len_a is length of the side adjacent to vertex a, len_b likewise
        len_a = len_b = sticker_width / sin_a

        # fix overlaps with the most often neighbour - its sticking target
        if first_vertex == other_second:
            cos_a = max(cos_a, edge.dot(other_edge) / (edge.length_squared))  # angles between pi/3 and 0
        elif second_vertex == other_first:
            cos_b = max(cos_b, edge.dot(other_edge) / (edge.length_squared))  # angles between pi/3 and 0

        # Fix tabs for sticking targets with small angles
        try:
            other_face_neighbor_left = other.neighbor_left
            other_face_neighbor_right = other.neighbor_right
            other_edge_neighbor_a = other_face_neighbor_left.vb.co - other.vb.co
            other_edge_neighbor_b = other_face_neighbor_right.va.co - other.va.co
            # Adjacent angles in the face
            cos_a = max(cos_a, -other_edge.dot(other_edge_neighbor_a) / (other_edge.length*other_edge_neighbor_a.length))
            cos_b = max(cos_b, other_edge.dot(other_edge_neighbor_b) / (other_edge.length*other_edge_neighbor_b.length))
        except AttributeError:  # neighbor data may be missing for edges with 3+ faces
            pass
        except ZeroDivisionError:
            pass

        # Calculate the lengths of the glue tab edges using the possibly smaller angles
        sin_a = abs(1 - cos_a**2)**0.5
        len_b = min(len_a, (edge.length * sin_a) / (sin_a * cos_b + sin_b * cos_a))
        len_a = 0 if sin_a == 0 else min(sticker_width / sin_a, (edge.length - len_b*cos_b) / cos_a)

        sin_b = abs(1 - cos_b**2)**0.5
        len_a = min(len_a, (edge.length * sin_b) / (sin_a * cos_b + sin_b * cos_a))
        len_b = 0 if sin_b == 0 else min(sticker_width / sin_b, (edge.length - len_a * cos_a) / cos_b)

        v3 = second_vertex.co + mu.Matrix(((cos_b, -sin_b), (sin_b, cos_b))) @ edge * len_b / edge.length
        v4 = first_vertex.co + mu.Matrix(((-cos_a, -sin_a), (sin_a, -cos_a))) @ edge * len_a / edge.length
        if v3 != v4:
            self.points = [second_vertex.co, v3, v4, first_vertex.co]
        else:
            self.points = [second_vertex.co, v3, first_vertex.co]

        sin, cos = edge.y / edge.length, edge.x / edge.length
        self.rot = mu.Matrix(((cos, -sin), (sin, cos)))
        self.width = sticker_width * 0.9
        if index and uvedge.uvface.island is not other.uvface.island:
            self.text = "{}:{}".format(other.uvface.island.abbreviation, index)
        else:
            self.text = index
        self.center = (uvedge.va.co + uvedge.vb.co) / 2 + self.rot @ mu.Vector((0, self.width * 0.2))
        self.bounds = [v3, v4, self.center] if v3 != v4 else [v3, self.center]


class Pdf:
    """Simple PDF exporter"""

    mm_to_pt = 72 / 25.4
    character_width_packed = {
        191: "'", 222: 'ijl\x82\x91\x92', 278: '|¦\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !,./:;I[\\]ft\xa0·ÌÍÎÏìíîï',
        333: '()-`r\x84\x88\x8b\x93\x94\x98\x9b¡¨\xad¯²³´¸¹{}', 350: '\x7f\x81\x8d\x8f\x90\x95\x9d', 365: '"ºª*°', 469: '^', 500: 'Jcksvxyz\x9a\x9eçýÿ', 584: '¶+<=>~¬±×÷', 611: 'FTZ\x8e¿ßø',
        667: '&ABEKPSVXY\x8a\x9fÀÁÂÃÄÅÈÉÊËÝÞ', 722: 'CDHNRUwÇÐÑÙÚÛÜ', 737: '©®', 778: 'GOQÒÓÔÕÖØ', 833: 'Mm¼½¾', 889: '%æ', 944: 'W\x9c', 1000: '\x85\x89\x8c\x97\x99Æ', 1015: '@', }
    character_width = {c: value for (value, chars) in character_width_packed.items() for c in chars}

    def __init__(self, properties):
        init_exporter(self, properties)
        self.styles = dict()

    def text_width(self, text, scale=None):
        return (scale or self.text_size) * sum(self.character_width.get(c, 556) for c in text) / 1000

    def styling(self, name, do_stroke=True):
        s, m, l = (length * self.style.line_width * 1000 for length in (1, 4, 9))
        format_style = {'SOLID': [], 'DOT': [s, m], 'DASH': [m, l], 'LONGDASH': [l, m], 'DASHDOT': [l, m, s, m]}
        style, color, width = (getattr(self.style, f"{name}_{arg}", None) for arg in ("style", "color", "width"))
        style = style or 'SOLID'
        result = ["q"]
        if do_stroke:
            result += [
                "[ " + " ".join("{:.3f}".format(num) for num in format_style[style]) + " ] 0 d",
                "{0:.3f} {1:.3f} {2:.3f} RG".format(*color),
                "{:.3f} w".format(self.style.line_width * 1000 * width),
                ]
        else:
            result.append("{0:.3f} {1:.3f} {2:.3f} rg".format(*color))
        if color[3] < 1:
            style_name = "R{:03}".format(round(1000 * color[3]))
            result.append("/{} gs".format(style_name))
            if style_name not in self.styles:
                self.styles[style_name] = {"CA": color[3], "ca": color[3]}
        return result

    @classmethod
    def encode_image(cls, bpy_image):
        data = bytes(int(255 * px) for (i, px) in enumerate(bpy_image.pixels) if i % 4 != 3)
        image = {
            "Type": "XObject", "Subtype": "Image", "Width": bpy_image.size[0], "Height": bpy_image.size[1],
            "ColorSpace": "DeviceRGB", "BitsPerComponent": 8, "Interpolate": True,
            "Filter": ["ASCII85Decode", "FlateDecode"], "stream": data}
        return image

    def write(self, mesh, filename):
        def format_dict(obj, refs=tuple()):
            content = "".join("/{} {}\n".format(key, format_value(value, refs)) for (key, value) in obj.items())
            return f"<< {content} >>"

        def line_through(seq):
            fmt = "{0.x:.6f} {0.y:.6f} {1} ".format
            return "".join(fmt(1000*co, cmd) for (co, cmd) in zip(seq, itt.chain("m", itt.repeat("l"))))

        def format_value(value, refs=tuple()):
            if value in refs:
                return "{} 0 R".format(refs.index(value) + 1)
            elif type(value) is dict:
                return format_dict(value, refs)
            elif type(value) in (list, tuple):
                return "[ " + " ".join(format_value(item, refs) for item in value) + " ]"
            elif type(value) is int:
                return str(value)
            elif type(value) is float:
                return "{:.6f}".format(value)
            elif type(value) is bool:
                return "true" if value else "false"
            else:
                return "/{}".format(value)  # this script can output only PDF names, no strings

        def write_object(index, obj, refs, f, stream=None):
            byte_count = f.write("{} 0 obj\n".format(index).encode())
            if type(obj) is not dict:
                stream, obj = obj, dict()
            elif "stream" in obj:
                stream = obj.pop("stream")
            if stream:
                obj["Filter"] = "FlateDecode"
                stream = encode(stream)
                obj["Length"] = len(stream)
            byte_count += f.write(format_dict(obj, refs).encode())
            if stream:
                byte_count += f.write(b"\nstream\n")
                byte_count += f.write(stream)
                byte_count += f.write(b"\nendstream")
            return byte_count + f.write(b"\nendobj\n")

        def encode(data):
            from zlib import compress
            if hasattr(data, "encode"):
                data = data.encode()
            return compress(data)

        page_size_pt = 1000 * self.mm_to_pt * self.page_size
        reset_style = ["Q"]  # graphic command for later use
        root = {"Type": "Pages", "MediaBox": [0, 0, page_size_pt.x, page_size_pt.y], "Kids": list()}
        catalog = {"Type": "Catalog", "Pages": root}
        font = {
            "Type": "Font", "Subtype": "Type1", "Name": "F1",
            "BaseFont": "Helvetica", "Encoding": "MacRomanEncoding"}
        objects = [root, catalog, font]

        for page in mesh.pages:
            commands = ["{0:.6f} 0 0 {0:.6f} 0 0 cm".format(self.mm_to_pt)]
            resources = {"Font": {"F1": font}, "ExtGState": self.styles, "ProcSet": ["PDF"]}
            if any(island.embedded_image for island in page.islands):
                resources["XObject"] = dict()
                resources["ProcSet"].append("ImageC")
            for island in page.islands:
                commands.append("q 1 0 0 1 {0.x:.6f} {0.y:.6f} cm".format(1000*(self.margin + island.pos)))
                if island.embedded_image:
                    identifier = "I{}".format(len(resources["XObject"]) + 1)
                    commands.append(self.command_image.format(1000 * island.bounding_box, identifier))
                    objects.append(island.embedded_image)
                    resources["XObject"][identifier] = island.embedded_image

                if island.title:
                    commands += self.styling("text", do_stroke=False)
                    commands.append(self.command_label.format(
                        size=1000*self.text_size,
                        x=500 * (island.bounding_box.x - self.text_width(island.title)),
                        y=1000 * 0.2 * self.text_size,
                        label=island.title))
                    commands += reset_style

                data_markers, data_stickerfill = list(), list()
                for marker in island.markers:
                    if isinstance(marker, Sticker):
                        data_stickerfill.append(line_through(marker.points) + "f")
                        if marker.text:
                            data_markers.append(self.command_sticker.format(
                                label=marker.text,
                                pos=1000*marker.center,
                                mat=marker.rot,
                                align=-500 * self.text_width(marker.text, marker.width),
                                size=1000*marker.width))
                    elif isinstance(marker, Arrow):
                        size = 1000 * marker.size
                        position = 1000 * (marker.center + marker.size * marker.rot @ mu.Vector((0, -0.9)))
                        data_markers.append(self.command_arrow.format(
                            index=marker.text,
                            arrow_pos=1000 * marker.center,
                            pos=position - 1000 * mu.Vector((0.5 * self.text_width(marker.text), 0.4 * self.text_size)),
                            mat=size * marker.rot,
                            size=size))
                    elif isinstance(marker, NumberAlone):
                        data_markers.append(self.command_number.format(
                            label=marker.text,
                            pos=1000*marker.center,
                            mat=marker.rot,
                            size=1000*marker.size))

                data_outer, data_convex, data_concave, data_freestyle = (list() for i in range(4))
                outer_edges = set(island.boundary)
                while outer_edges:
                    data_loop = list()
                    uvedge = outer_edges.pop()
                    while 1:
                        if uvedge.sticker:
                            data_loop.extend(uvedge.sticker.points[1:])
                        else:
                            vertex = uvedge.vb if uvedge.uvface.flipped else uvedge.va
                            data_loop.append(vertex.co)
                        uvedge = uvedge.neighbor_right
                        try:
                            outer_edges.remove(uvedge)
                        except KeyError:
                            break
                    data_outer.append(line_through(data_loop) + "s")

                for loop, uvedge in island.edges.items():
                    edge = mesh.edges[loop.edge]
                    if edge.is_cut(uvedge.uvface.face) and not uvedge.sticker:
                        continue
                    data_uvedge = line_through((uvedge.va.co, uvedge.vb.co)) + "S"
                    if edge.freestyle:
                        data_freestyle.append(data_uvedge)
                    # each uvedge exists in two opposite-oriented variants; we want to add each only once
                    if uvedge.sticker or uvedge.uvface.flipped != (id(uvedge.va) > id(uvedge.vb)):
                        if edge.angle > self.angle_epsilon:
                            data_convex.append(data_uvedge)
                        elif edge.angle < -self.angle_epsilon:
                            data_concave.append(data_uvedge)
                if island.is_inside_out:
                    data_convex, data_concave = data_concave, data_convex

                if data_stickerfill and self.style.sticker_color[3] > 0:
                    commands += itt.chain(self.styling("sticker", do_stroke=False), data_stickerfill, reset_style)
                if data_freestyle:
                    commands += itt.chain(self.styling("freestyle"), data_freestyle, reset_style)
                if (data_convex or data_concave) and not self.pure_net and self.style.use_inbg:
                    commands += itt.chain(self.styling("inbg"), data_convex, data_concave, reset_style)
                if data_convex:
                    commands += itt.chain(self.styling("convex"), data_convex, reset_style)
                if data_concave:
                    commands += itt.chain(self.styling("concave"), data_concave, reset_style)
                if data_outer:
                    if not self.pure_net and self.style.use_outbg:
                        commands += itt.chain(self.styling("outbg"), data_outer, reset_style)
                    commands += itt.chain(self.styling("outer"), data_outer, reset_style)
                if data_markers:
                    commands += itt.chain(self.styling("text", do_stroke=False), data_markers, reset_style)
                commands += reset_style  # return from island to page coordinates
            content = "\n".join(commands)
            page = {"Type": "Page", "Parent": root, "Contents": content, "Resources": resources}
            root["Kids"].append(page)
            objects += page, content
            objects.extend(self.styles.values())

        root["Count"] = len(root["Kids"])
        with open(filename, "wb+") as f:
            xref_table = list()
            position = 0
            position += f.write(b"%PDF-1.4\n")
            position += f.write(b"%\xde\xad\xbe\xef\n")
            for index, obj in enumerate(objects, 1):
                xref_table.append(position)
                position += write_object(index, obj, objects, f)
            xref_pos = position
            f.write("xref\n0 {}\n".format(len(xref_table) + 1).encode())
            f.write("{:010} {:05} f\r\n".format(0, 65535).encode())
            for position in xref_table:
                f.write("{:010} {:05} n\r\n".format(position, 0).encode())
            f.write(b"trailer\n")
            f.write(format_dict({"Size": len(xref_table) + 1, "Root": catalog}, objects).encode())
            f.write("\nstartxref\n{}\n%%EOF\n".format(xref_pos).encode())

    command_label = "q /F1 {size:.6f} Tf BT {x:.6f} {y:.6f} Td ({label}) Tj ET Q"
    command_image = "q {0.x:.6f} 0 0 {0.y:.6f} 0 0 cm 1 0 0 -1 0 1 cm /{1} Do Q"
    command_sticker = "q /F1 {size:.6f} Tf {mat[0][0]:.6f} {mat[1][0]:.6f} {mat[0][1]:.6f} {mat[1][1]:.6f} {pos.x:.6f} {pos.y:.6f} cm BT {align:.6f} 0 Td ({label}) Tj ET Q"
    command_arrow = "q /F1 {size:.6f} Tf BT {pos.x:.6f} {pos.y:.6f} Td ({index}) Tj ET {mat[0][0]:.6f} {mat[1][0]:.6f} {mat[0][1]:.6f} {mat[1][1]:.6f} {arrow_pos.x:.6f} {arrow_pos.y:.6f} cm 0 0 m 1 -1 l 0 -0.25 l -1 -1 l f Q"
    command_number = "q /F1 {size:.6f} Tf {mat[0][0]:.6f} {mat[1][0]:.6f} {mat[0][1]:.6f} {mat[1][1]:.6f} {pos.x:.6f} {pos.y:.6f} cm BT ({label}) Tj ET Q"



class Svg:
    """Simple SVG exporter"""

    def __init__(self, properties):
        util.init_exporter(self, properties)

    @classmethod
    def encode_image(cls, bpy_image):
        import tempfile
        import base64
        with tempfile.TemporaryDirectory() as directory:
            filename = directory + "/i.png"
            bpy_image.filepath_raw = filename
            bpy_image.save()
            return base64.encodebytes(open(filename, "rb").read()).decode('ascii')

    def format_vertex(self, vector):
        """Return a string with both coordinates of the given vertex."""
        return "{:.6f} {:.6f}".format((vector.x + self.margin.x) * 1000, (self.page_size.y - vector.y - self.margin.y) * 1000)

    def write(self, mesh, filename):
        """Write data to a file given by its name."""
        line_through = " L ".join  # used for formatting of SVG path data
        rows = "\n".join

        dl = ["{:.2f}".format(length * self.style.line_width * 1000) for length in (2, 5, 10)]
        format_style = {
            'SOLID': "none", 'DOT': "{0},{1}".format(*dl), 'DASH': "{1},{2}".format(*dl),
            'LONGDASH': "{2},{1}".format(*dl), 'DASHDOT': "{2},{1},{0},{1}".format(*dl)}

        def format_color(vec):
            return "#{:02x}{:02x}{:02x}".format(round(vec[0] * 255), round(vec[1] * 255), round(vec[2] * 255))

        def format_matrix(matrix):
            return " ".join("{:.6f}".format(cell) for column in matrix for cell in column)

        def path_convert(string, relto=os.path.dirname(filename)):
            string = os.path.relpath(string, relto)
            if os.path.sep != '/':
                string = string.replace(os.path.sep, '/')
            return string

        styleargs = {
            name: format_color(getattr(self.style, name)) for name in (
                "outer_color", "outbg_color", "convex_color", "concave_color", "freestyle_color",
                "inbg_color", "sticker_color", "text_color")}
        styleargs.update({
            name: format_style[getattr(self.style, name)] for name in
            ("outer_style", "convex_style", "concave_style", "freestyle_style")})
        styleargs.update({
            name: getattr(self.style, attr)[3] for name, attr in (
                ("outer_alpha", "outer_color"), ("outbg_alpha", "outbg_color"),
                ("convex_alpha", "convex_color"), ("concave_alpha", "concave_color"),
                ("freestyle_alpha", "freestyle_color"),
                ("inbg_alpha", "inbg_color"), ("sticker_alpha", "sticker_color"),
                ("text_alpha", "text_color"))})
        styleargs.update({
            name: getattr(self.style, name) * self.style.line_width * 1000 for name in
            ("outer_width", "convex_width", "concave_width", "freestyle_width", "outbg_width", "inbg_width")})
        for num, page in enumerate(mesh.pages):
            page_filename = "{}_{}.svg".format(filename[:filename.rfind(".svg")], page.name) if len(mesh.pages) > 1 else filename
            with open(page_filename, 'w') as f:
                print(self.svg_base.format(width=self.page_size.x*1000, height=self.page_size.y*1000), file=f)
                print(self.css_base.format(**styleargs), file=f)
                if page.image_path:
                    print(
                        self.image_linked_tag.format(
                            pos="{0:.6f} {0:.6f}".format(self.margin.x*1000),
                            width=(self.page_size.x - 2 * self.margin.x)*1000,
                            height=(self.page_size.y - 2 * self.margin.y)*1000,
                            path=path_convert(page.image_path)),
                        file=f)
                if len(page.islands) > 1:
                    print("<g>", file=f)

                for island in page.islands:
                    print("<g>", file=f)
                    if island.image_path:
                        print(
                            self.image_linked_tag.format(
                                pos=self.format_vertex(island.pos + mu.Vector((0, island.bounding_box.y))),
                                width=island.bounding_box.x*1000,
                                height=island.bounding_box.y*1000,
                                path=path_convert(island.image_path)),
                            file=f)
                    elif island.embedded_image:
                        print(
                            self.image_embedded_tag.format(
                                pos=self.format_vertex(island.pos + mu.Vector((0, island.bounding_box.y))),
                                width=island.bounding_box.x*1000,
                                height=island.bounding_box.y*1000,
                                path=island.image_path),
                            island.embedded_image, "'/>",
                            file=f, sep="")
                    if island.title:
                        print(
                            self.text_tag.format(
                                size=1000 * self.text_size,
                                x=1000 * (island.bounding_box.x*0.5 + island.pos.x + self.margin.x),
                                y=1000 * (self.page_size.y - island.pos.y - self.margin.y - 0.2 * self.text_size),
                                label=island.title),
                            file=f)

                    data_markers, data_stickerfill = list(), list()
                    for marker in island.markers:
                        if isinstance(marker, Sticker):
                            data_stickerfill.append("M {} Z".format(
                                line_through(self.format_vertex(co + island.pos) for co in marker.points)))
                            if marker.text:
                                data_markers.append(self.text_transformed_tag.format(
                                    label=marker.text,
                                    pos=self.format_vertex(marker.center + island.pos),
                                    mat=format_matrix(marker.rot),
                                    size=marker.width * 1000))
                        elif isinstance(marker, Arrow):
                            size = marker.size * 1000
                            position = marker.center + marker.size * marker.rot @ mu.Vector((0, -0.9))
                            data_markers.append(self.arrow_marker_tag.format(
                                index=marker.text,
                                arrow_pos=self.format_vertex(marker.center + island.pos),
                                scale=size,
                                pos=self.format_vertex(position + island.pos - marker.size*mu.Vector((0, 0.4))),
                                mat=format_matrix(size * marker.rot)))
                        elif isinstance(marker, NumberAlone):
                            data_markers.append(self.text_transformed_tag.format(
                                label=marker.text,
                                pos=self.format_vertex(marker.center + island.pos),
                                mat=format_matrix(marker.rot),
                                size=marker.size * 1000))
                    if data_stickerfill and self.style.sticker_color[3] > 0:
                        print("<path class='sticker' d='", rows(data_stickerfill), "'/>", file=f)

                    data_outer, data_convex, data_concave, data_freestyle = (list() for i in range(4))
                    outer_edges = set(island.boundary)
                    while outer_edges:
                        data_loop = list()
                        uvedge = outer_edges.pop()
                        while 1:
                            if uvedge.sticker:
                                data_loop.extend(self.format_vertex(co + island.pos) for co in uvedge.sticker.points[1:])
                            else:
                                vertex = uvedge.vb if uvedge.uvface.flipped else uvedge.va
                                data_loop.append(self.format_vertex(vertex.co + island.pos))
                            uvedge = uvedge.neighbor_right
                            try:
                                outer_edges.remove(uvedge)
                            except KeyError:
                                break
                        data_outer.append("M {} Z".format(line_through(data_loop)))

                    visited_edges = set()
                    for loop, uvedge in island.edges.items():
                        edge = mesh.edges[loop.edge]
                        if edge.is_cut(uvedge.uvface.face) and not uvedge.sticker:
                            continue
                        data_uvedge = "M {}".format(
                            line_through(self.format_vertex(v.co + island.pos) for v in (uvedge.va, uvedge.vb)))
                        if edge.freestyle:
                            data_freestyle.append(data_uvedge)
                        # each uvedge is in two opposite-oriented variants; we want to add each only once
                        vertex_pair = frozenset((uvedge.va, uvedge.vb))
                        if vertex_pair not in visited_edges:
                            visited_edges.add(vertex_pair)
                            if edge.angle > self.angle_epsilon:
                                data_convex.append(data_uvedge)
                            elif edge.angle < -self.angle_epsilon:
                                data_concave.append(data_uvedge)
                    if island.is_inside_out:
                        data_convex, data_concave = data_concave, data_convex

                    if data_freestyle:
                        print("<path class='freestyle' d='", rows(data_freestyle), "'/>", file=f)
                    if (data_convex or data_concave) and not self.pure_net and self.style.use_inbg:
                        print("<path class='inner_background' d='", rows(data_convex + data_concave), "'/>", file=f)
                    if data_convex:
                        print("<path class='convex' d='", rows(data_convex), "'/>", file=f)
                    if data_concave:
                        print("<path class='concave' d='", rows(data_concave), "'/>", file=f)
                    if data_outer:
                        if not self.pure_net and self.style.use_outbg:
                            print("<path class='outer_background' d='", rows(data_outer), "'/>", file=f)
                        print("<path class='outer' d='", rows(data_outer), "'/>", file=f)
                    if data_markers:
                        print(rows(data_markers), file=f)
                    print("</g>", file=f)

                if len(page.islands) > 1:
                    print("</g>", file=f)
                print("</svg>", file=f)

    image_linked_tag = "<image transform='translate({pos})' width='{width:.6f}' height='{height:.6f}' xlink:href='{path}'/>"
    image_embedded_tag = "<image transform='translate({pos})' width='{width:.6f}' height='{height:.6f}' xlink:href='data:image/png;base64,"
    text_tag = "<text transform='translate({x} {y})' style='font-size:{size:.2f}'><tspan>{label}</tspan></text>"
    text_transformed_tag = "<text transform='matrix({mat} {pos})' style='font-size:{size:.2f}'><tspan>{label}</tspan></text>"
    arrow_marker_tag = "<g><path transform='matrix({mat} {arrow_pos})' class='arrow' d='M 0 0 L 1 1 L 0 0.25 L -1 1 Z'/>" \
        "<text transform='translate({pos})' style='font-size:{scale:.2f}'><tspan>{index}</tspan></text></g>"

    svg_base = """<?xml version='1.0' encoding='UTF-8' standalone='no'?>
    <svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' version='1.1'
    width='{width:.2f}mm' height='{height:.2f}mm' viewBox='0 0 {width:.2f} {height:.2f}'>"""

    css_base = """<style type="text/css">
    path {{
        fill: none;
        stroke-linecap: butt;
        stroke-linejoin: bevel;
        stroke-dasharray: none;
    }}
    path.outer {{
        stroke: {outer_color};
        stroke-dasharray: {outer_style};
        stroke-dashoffset: 0;
        stroke-width: {outer_width:.2};
        stroke-opacity: {outer_alpha:.2};
    }}
    path.convex {{
        stroke: {convex_color};
        stroke-dasharray: {convex_style};
        stroke-dashoffset:0;
        stroke-width:{convex_width:.2};
        stroke-opacity: {convex_alpha:.2}
    }}
    path.concave {{
        stroke: {concave_color};
        stroke-dasharray: {concave_style};
        stroke-dashoffset: 0;
        stroke-width: {concave_width:.2};
        stroke-opacity: {concave_alpha:.2}
    }}
    path.freestyle {{
        stroke: {freestyle_color};
        stroke-dasharray: {freestyle_style};
        stroke-dashoffset: 0;
        stroke-width: {freestyle_width:.2};
        stroke-opacity: {freestyle_alpha:.2}
    }}
    path.outer_background {{
        stroke: {outbg_color};
        stroke-opacity: {outbg_alpha};
        stroke-width: {outbg_width:.2}
    }}
    path.inner_background {{
        stroke: {inbg_color};
        stroke-opacity: {inbg_alpha};
        stroke-width: {inbg_width:.2}
    }}
    path.sticker {{
        fill: {sticker_color};
        stroke: none;
        fill-opacity: {sticker_alpha:.2};
    }}
    path.arrow {{
        fill: {text_color};
    }}
    text {{
        font-style: normal;
        fill: {text_color};
        fill-opacity: {text_alpha:.2};
        stroke: none;
    }}
    text, tspan {{
        text-anchor:middle;
    }}
    </style>"""
