import sys, os
from time import gmtime, strftime


def parse_cl():
    """ parse and check command line options
    @return:
    """
    import argparse

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--aux', action="store", dest='src_aux', required=True)
    parser.add_argument('--pl', action="store", dest='final_pl')
    parser.add_argument('--lef', action="store", dest='src_lef', required=True)
    parser.add_argument('--verilog', action="store", dest='src_v', required=True)
    parser.add_argument('--def_out', action="store", dest='dest_def', default='out.def')

    opt = parser.parse_args()

    return opt


class Node(object):
    def __init__(self, name, width=0.0, height=0.0, is_terminal=False, 
                    x=0.0, y=0.0, orient='N'):
        # nodes
        self.name = name
        self.width = width
        self.height = height
        self.is_terminal = is_terminal

        # Placement
        self.x = x 
        self.y = y
        self.orient = orient

    def __str__(self):
        return "%s, (%.4f, %.4f), %r, (%.4f, %.4f), %s" % \
                (self.name, self.width, self.height, self.is_terminal,
                 self.x, self.y, self.orient)


class NodePin(Node):
    def __init__(self, name, direction):
        super(self.__class__, self).__init__(name)
        self.is_terminal = True
        self.direction = direction


def print_node_pin(node_pin):
    x = node_pin.x * LefTechInfo.lef_unit_microns * WIDTH_MULTIPLIER
    y = node_pin.y * LefTechInfo.lef_unit_microns * HEIGHT_MULTIPLIER

    return  \
    "  - %s + NET %s\n" \
    "    + DIRECTION %s\n" \
    "    + FIXED ( %d %d ) %s\n" \
    "        + LAYER metal3 ( 0 0 ) ( 380 380 ) ;" % \
    (node_pin.name, node_pin.name, node_pin.direction, x, y, node_pin.orient)


class NodeComponent(Node):
    def __init__(self, name, gate_type):
        super(self.__class__, self).__init__(name)
        self.gate_type = gate_type


def print_node_component(node_comp):
    x = node_comp.x * LefTechInfo.lef_unit_microns * WIDTH_MULTIPLIER 
    y = node_comp.y * LefTechInfo.lef_unit_microns * HEIGHT_MULTIPLIER 

    fixed_placed = "FIXED" if node_comp.is_terminal else "PLACED"
    return  \
    "  - %s %s\n" \
    "    + %s ( %d %d ) %s ;" % \
    (node_comp.name, node_comp.gate_type, fixed_placed, x, y, node_comp.orient)


""" Verilog related """
MODULE_NAME = "CIRCUIT"


def parse_verilog(src_v):
    with open(src_v, 'r') as f:
        # read lines without blank lines
        lines = [l.replace('(', ' ') for l in (line.strip() for line in f) if l]

    lines_iter = iter(lines)
    node_list = dict()
    for l in lines_iter:
        tokens = l.rstrip(';').split()

        if tokens[0] == '//':
            continue

        elif tokens[0] == 'module':
            global MODULE_NAME
            MODULE_NAME = tokens[1]
            
        elif tokens[0] == 'input' or tokens[0] == 'output':
            gate_type = tokens[0].upper()
            gate_name = tokens[1]

            node_list[gate_name] = NodePin(gate_name, gate_type)
            # node_list.append( NodePin(tokens[1][:-1], tokens[0]) )

        elif tokens[0] == 'wire':
            continue

        elif len(tokens) > 3:
            gate_type = tokens[0]
            gate_name = tokens[1]
            node_list[gate_name] = NodeComponent(gate_name, gate_type)
            # node_list.append( NodeComponent(gate_name, gate_type) )

    return node_list
        

def get_pl_and_scl(src_aux):
    with open(src_aux, 'r') as f:
        tokens = [t for l in f for t in l.split() 
                    if t.endswith(('.nodes', '.pl', '.scl'))]

        for t in tokens:
            if t.endswith('.nodes'): nodes = t
            elif t.endswith('.pl'): pl = t
            else: scl = t

    try:
        assert len(tokens) == 3
    except AssertionError:
        sys.stderr.write("Error: invalid aux file.")
        raise SystemExit(-1)

    src_path = os.path.dirname(os.path.abspath(src_aux))

    src_nodes = src_path + '/' + nodes
    src_pl = src_path + '/' + pl
    src_scl = src_path + '/' + scl

    return src_nodes, src_pl, src_scl


class BookshelfRow(object):
    def __init__(self, row_info):
        (self.coordinate, self.height, self.site_width, self.site_spacing,
        self.site_orient, self.site_symmetry, self.subrow_origin,
        self.num_sites) = row_info


def parse_bookshelf_nodes(node_file_name, node_list):

    with open(node_file_name, 'r') as f:
        # read lines without blank lines
        lines = [l for l in (line.strip() for line in f) if l]

    # Skip the first line: UCLA nodes ...
    lines_iter = iter(lines[1:])

    for l in lines_iter:
        if l.startswith(('#')): continue

        tokens = l.split()
        if tokens[0] == 'NumNodes' or tokens[0] == 'NumTerminals':
            continue

        name, w, h = tokens[0], float(tokens[1]), float(tokens[2])

        n = node_list[name]
        n.width, n.height = w, h
        if n.__class__ == NodeComponent:
            n.is_terminal = True if len(tokens) == 4 else False


def parse_scl(scl_file_name):
    with open(scl_file_name, 'r') as f:
        # read lines without blank lines
        lines = [l for l in (line.strip() for line in f) if l]

    # Skip the first line: UCLA scl ...
    lines_iter = iter(lines[1:])

    row_list = list()
    for l in lines_iter:
        if l.startswith('#'): continue
        
        tokens = l.split()
        if tokens[0] == 'NumRows':
            num_rows = int(tokens[2])

        elif tokens[0] == 'CoreRow':
            try: assert tokens[1] == 'Horizontal'
            except AssertionError:
                sys.stderr.write("Unsupported bookshelf (scl) file.")
                raise SystemExit(-1)

            row_info = [None]*8 
            while True:
                l = next(lines_iter)
                tokens = l.split()
                if tokens[0] == 'Coordinate':
                    row_info[0] = float(tokens[2])

                elif tokens[0] == 'Height':
                    row_info[1] = float(tokens[2])

                elif tokens[0] == 'Sitewidth':
                    row_info[2] = float(tokens[2])

                elif tokens[0] == 'Sitespacing':
                    row_info[3] = float(tokens[2])

                elif tokens[0] == 'Siteorient':
                    row_info[4] = tokens[2]

                elif tokens[0] == 'Sitesymmetry':
                    row_info[5] = tokens[2]
                
                elif tokens[0] == 'SubrowOrigin':
                    row_info[6] = float(tokens[2])
                    assert tokens[3] == 'NumSites'
                    row_info[7] = int(tokens[5])

                elif tokens[0] == 'End':
                    break

            assert len([i for i in row_info if i is None]) == 0

            row = BookshelfRow(row_info)
            row_list.append(row)

    assert len(row_list) == num_rows
    return row_list


def parse_pl(pl_file_name, node_list):
    with open(pl_file_name, 'r') as f:
        # read lines without blank lines
        lines = [l for l in (line.strip() for line in f) if l]

    # Skip the first line: UCLA nodes ...
    lines_iter = iter(lines[1:])
  
    for l in lines_iter:
        if l.startswith('#'): continue

        tokens = l.split()
        assert len(tokens) >= 5

        name, x, y, orient = \
            tokens[0], float(tokens[1]), float(tokens[2]), tokens[4]

        # for ICCAD
        orient = 'N'

        node = node_list[name]
        node.x, node.y, node.orient = x, y, orient


""" LEF related """
WIDTH_MULTIPLIER = 1.0
HEIGHT_MULTIPLIER = 1.0


class LefTechInfo(object):
    lef_version = '5.7'
    lef_namescasesensitive= 'ON'
    lef_busbitchars = '[]'
    lef_dividerchar = '/'
    lef_unit_microns = 2000
    lef_manufacturing_grid = 0.0050

    lef_site_name = ''
    lef_site_width = 0.0    # site
    lef_site_height = 0.0

    metal_layer_dict = dict()   # metal pitches


class LefSite(object):
    """ Lef Site """
    def __init__(self, name, symmetry, site_class, width, height):
        self.name = name
        self.symmetry = symmetry
        self.site_class = site_class
        self.width = width
        self.height = height
    
    def __str__(self):
        return ("%s %s %s (%.4f %.4f)" % \
                (self.name, self.symmetry, self.site_class, \
                 self.width, self.height))


def parse_lef(lef_file_name):
    print ("Parsing LEF file.")

    with open(lef_file_name, 'r') as f:
        # read lines without blank lines
        lines = [l for l in (line.strip() for line in f) if l]
    lines_iter = iter(lines)

    site_list = list()
    symmetry = 'Y'
    for line in lines_iter:
        tokens = line.split()
        """ Library information """
        if   tokens[0] == 'VERSION':     LefTechInfo.lef_version = tokens[1]
        elif tokens[0] == 'BUSBITCHARS': LefTechInfo.lef_busbitchars = tokens[1]
        elif tokens[0] == 'DIVDERCHAR':  LefTechInfo.lef_dividerchar = tokens[1]
        elif tokens[0] == 'UNITS':
            tokens = next(lines_iter).split()
            assert tokens[0] == 'DATABASE'
            assert tokens[1] == 'MICRONS'
            LefTechInfo.lef_unit_microns = int(tokens[2])
            assert next(lines_iter).startswith('END UNITS')

        elif tokens[0] == 'MANUFACTURINGGRID':
            LefTechInfo.lef_manufacturinggrid = float(tokens[1])

        # LAYER definition
        elif tokens[0] == 'LAYER':
            layer_name = tokens[1]
            tokens = next(lines_iter).split()
            
            if tokens[0] == 'TYPE':
                while True:
                    # find pitch
                    tokens = next(lines_iter).split()
                    if tokens[0] == 'END':
                        break
                    elif tokens[0] == 'PITCH':
                        pitch = float(tokens[1])
                        LefTechInfo.metal_layer_dict[layer_name] = pitch

            else:
                continue

        # SITE definition
        elif tokens[0] == 'SITE' and tokens[-1] != ';':
            site_name = tokens[1]
            while True:
                tokens = next(lines_iter).split()
                try:
                    if (tokens[0], tokens[1]) == ('END', site_name): break
                    elif tokens[0] == 'SYMMETRY':
                        symmetry = tokens[1]

                    elif tokens[0] == 'CLASS':
                        site_class = tokens[1]

                    elif tokens[0] == 'SIZE':
                        width = float(tokens[1])
                        height = float(tokens[3])

                except IndexError:
                    pass
            site_list.append( LefSite(site_name, symmetry, site_class, width, height) )
            print ("\tLEF Site: %s" % (site_list[0]))

    try:
        assert len(site_list) == 1
    except AssertionError:
        sys.stderr.write("Unsupported LEF file - multiple sites defined.\n")
        raise SystemExit(-1)

    LefTechInfo.lef_site_name = site_list[0].name
    LefTechInfo.lef_site_width = site_list[0].width
    LefTechInfo.lef_site_height = site_list[0].height

    # Assign global vlaues
    global WIDTH_MULTIPLIER, HEIGHT_MULTIPLIER
    WIDTH_MULTIPLIER = LefTechInfo.metal_layer_dict["metal2"]
    HEIGHT_MULTIPLIER = LefTechInfo.metal_layer_dict["metal1"]

    print ("\tM1 pitch (height multiplier): %f" % HEIGHT_MULTIPLIER)
    print ("\tM2 pitch (width multiplier) : %f" % WIDTH_MULTIPLIER)
    print ("\t\tDEF width/height = bookshelf width/height * MULTIPLIER * LEF_UNIT_MICRONS")
                

def gen_def(dest, node_list, row_list):

    f_dest = open(dest, 'w')

    f_dest.write('# Written by write_def.py\n\n')
    f_dest.write('VERSION 5.7 ;\n')
    f_dest.write('DIVIDERCHAR "/" ;\n')
    f_dest.write('BUSBITCHARS "[]" ;\n')
    f_dest.write('DESIGN %s ;\n' % (MODULE_NAME))

    DBU_PER_MICRON = LefTechInfo.lef_unit_microns
    f_dest.write("UNITS DISTANCE MICRONS %d ;\n\n" % (DBU_PER_MICRON))
#
    # Note:
    #   Bookshelf width  = LEF width  / METAL pitch
    #   Bookshelf height = LEF height / METAL pitch
    #   DEF width = LEF width * DBU_PER_MICRON
    #             = Bookshelf width * METAL pitch * DBU_PER_MICRON
    #   DEF height = LEF height * DBU_PER_MICRON
    #              = Bookshelf height * METAL pitch * DBU_PER_MICRON

    die_llx, die_lly = 0, 0
    die_urx, die_ury = -1, -1

    site_name = LefTechInfo.lef_site_name
    def_row_string = list()
    for i, r in enumerate(row_list):
        llx_in_def = r.subrow_origin * DBU_PER_MICRON * WIDTH_MULTIPLIER
        lly_in_def = r.coordinate * DBU_PER_MICRON * HEIGHT_MULTIPLIER

        width_in_def = r.site_width * DBU_PER_MICRON * WIDTH_MULTIPLIER
        height_in_def = r.height * DBU_PER_MICRON * HEIGHT_MULTIPLIER
        site_spacing_in_def = r.site_spacing * DBU_PER_MICRON * WIDTH_MULTIPLIER

        urx_in_def = llx_in_def + (width_in_def * r.num_sites)
        ury_in_def = lly_in_def + (height_in_def * 1)

        # Calculat the DIEAREA
        die_urx = urx_in_def if urx_in_def > die_urx else die_urx
        die_ury = ury_in_def if ury_in_def > die_ury else die_ury
        
        height_in_def = r.height * DBU_PER_MICRON * HEIGHT_MULTIPLIER

        def_row_string.append(
                "ROW %s_SITE_ROW_%d %s %d %d %s DO %d BY %d STEP %d %d ;" \
                % (site_name, i, site_name, llx_in_def, lly_in_def, 
                r.site_orient, r.num_sites, 1, int(site_spacing_in_def), 0))

    f_dest.write("DIEAREA ( 0 0 ) ( %d %d ) ; \n\n" % (die_urx, die_ury))
    f_dest.write('\n'.join(def_row_string))
    f_dest.write("\n\n")

    # PINS
    _node_list = list(node_list.values())
    pins       = [n for n in _node_list if n.__class__ is NodePin]
    components = [n for n in _node_list if n.__class__ is NodeComponent]

    pins       = sorted(pins, key=lambda p : p.name)
    components = sorted(components, key=lambda c : c.name)

    f_dest.write("PINS %d ;\n" % (len(pins)))
    [f_dest.write(print_node_pin(p) + "\n") for p in pins]
    f_dest.write("END PINS\n\n")

    # COMPONENTS
    f_dest.write("COMPONENTS %d ;\n" % (len(components)))
    [f_dest.write(print_node_component(c) + "\n") for c in components]

    f_dest.write("END COMPONENTS\n\n")

    f_dest.write('END DESIGN\n')


def write_def(src_aux, final_pl, src_lef, src_v, dest_def):
    nodes, pl, scl = get_pl_and_scl(src_aux)
    if final_pl is not None:
        pl = final_pl

    print ("Parsing verilog: %s" % (src_v))
    node_list = parse_verilog(src_v)

    print ("Parsing bookshelf nodes: %s" % (nodes))
    parse_bookshelf_nodes(nodes, node_list)

    print ("Parsing bookshelf scl: %s" % (scl))
    row_list = parse_scl(scl)

    print ("Parsing lef: %s" % (src_lef))
    parse_lef(src_lef)

    # Get placement info
    print ("Parsing bookshelf pl: %s" %(pl))
    parse_pl(pl, node_list)

    print ("Write def file")
    gen_def(dest_def, node_list, row_list)


if __name__ == '__main__':
    cl_opt = parse_cl()

    src_aux = cl_opt.src_aux
    final_pl = cl_opt.final_pl
    src_v = cl_opt.src_v
    src_lef = cl_opt.src_lef
    dest_def = cl_opt.dest_def

    print ("Bookshelf  : " + src_aux)
    if final_pl is not None:
        print ("Using pl   : " + final_pl)

    print ("LEF        : " + src_lef)
    print ("Netlist    : " + src_v)
    print ("Output DEF : " + dest_def)
    print ("")

    write_def(src_aux, final_pl, src_lef, src_v, dest_def)
