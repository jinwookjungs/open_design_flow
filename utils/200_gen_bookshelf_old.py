# File: gen_bookshelf.py
# Description: Generate a Bookshelf file set (.aux, .nets, .wts, .nodes) from 
#              the given verilog and lef file.
# Author: Jinwook Jung (jinwookjungs@gmail.com)
# Last modification: 09/15/15

from __future__ import print_function, division
from time import gmtime, strftime
from copy import deepcopy
from math import ceil
import sys

M1_LAYER_NAME = 'metal1'
M2_LAYER_NAME = 'metal2'


def parse_cl():
    """ parse and check command line options
    @return: dict - optinos key/value
    """
    import argparse
    from argparse import ArgumentTypeError

    def utilization(x):
        x = float(x)
        if x < 0.1 or x > 0.99:
            raise ArgumentTypeError("Utilization(%r) not in [0.1, 0.99]." % (x))
        return x

    parser = argparse.ArgumentParser(
                description='Generate a set of bookshelf files.')

    parser.add_argument('-i', action="store", dest='src_v', required=True)
    parser.add_argument('--lef', action="store", dest='src_lef', required=True)
    parser.add_argument('--def', action="store", dest='src_def', default=None)
    parser.add_argument('--fix_big_macros', action="store_true",
                         help="Set big block placement as FIXED.")

    parser.add_argument('--clock', action="store", dest='clock_port')
    parser.add_argument('--sdc', action="store", dest='input_sdc')
    parser.add_argument('--remove_clock_port', action="store_true", 
                        help="Doesn't place clock port " \
                             "(remove the port from nodes and pl).")

    parser.add_argument('--util', type=utilization, dest='utilization', 
                        default=0.7, 
                        help="Utilization (in 0.1, 0.99).")

    parser.add_argument('-o', action="store", dest='dest_name',
                        help="Base name of output files")

    opt = parser.parse_args()

    # Find clock port
    if opt.input_sdc is None and opt.clock_port is None:
        parser.error("at least one of --sdc and --clock required.")
        raise SystemExit(-1)

    elif opt.input_sdc is not None:
        try:
            # Example: create_clock [get_port <clock_port>] ...
            create_clock = [x.rstrip() for x in open(opt.input_sdc, 'r') \
                                        if x.startswith('create_clock')][0]
            tokens = create_clock.split()
            opt.clock_port = tokens[tokens.index('[get_ports') + 1][:-1]

        except ValueError:
            parser.error("Cannot find the clock port from %s." % (opt.input_sdc))
            raise SystemExit(-1)
        except TypeError:
            parser.error("Cannot open file %s." % (opt.input_sdc))
            raise SystemExit(-1)

    else:   # opt.clock_port is not None
        pass    # Nothing done.

    if opt.dest_name is None:
        opt.dest_name = opt.src_v[opt.src_v.rfind('/')+1:opt.src_v.find('.v')]

    return opt


# Scale factors to make width/height be the number of metal tracks
# These values are assigned in parse_lef function
WIDTH_DIVIDER = 1.0
HEIGHT_DIVIDER = 1.0


class LefTechInfo(object):
    """ Lef technology information. """
    lef_version = '5.7'
    lef_namescasesensitive= 'ON'
    lef_busbitchars = '[]'
    lef_dividerchar = '/'
    lef_unit_microns = 2000
    lef_manufacturing_grid = 0.0050

    lef_site_name = ''
    lef_site_width = 0.0    # site
    lef_site_height = 0.0

    metal_layer_dict = dict()   # layer name : pitches


class LefSite(object):
    """ Lef Site. """
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


class LefMacro(object):
    """ Lef Macro. """
    def __init__(self, name, width, height, macro_class, pin_list):
        self.name = name
        self.width = width
        self.height = height
        self.macro_class = macro_class
        self.pin_list = pin_list[:]

    def __str__(self):
        pin_str = '\n'.join([p.__str__() for p in self.pin_list])
        return "%s  %.4f  %.4f\n%s\n"  \
               % (self.name, self.width, self.height, pin_str)


class LefRectilinearMacro(LefMacro):
    """ Lef rectilinear macro """
    def __init__(self, name, width, height, macro_class, pin_list, obses):
        super(self.__class__, self).__init__(name, width, height, 
                                             macro_class, pin_list)
        self.obses = obses  # list of (llx, lly, widthidth, height)

    def __str__(self):
        pin_str = '\n'.join([p.__str__() for p in self.pin_list])
        obs_str = ""
        
        for obs in self.obses:
            obs_str += ' '.join([str(i) for i in self.obses])

        obs_str += '\n'
        return "%s  %.4f  %.4f\n%s\n%s\n" \
               % (self.name, self.width, self.height, pin_str, obs_str)


class LefPin(object):
    """ Lef Pin """
    def __init__(self, name, direction, ll, ur):
        self.name = name
        self.direction = direction
        (self.llx, self.lly) = ll
        (self.urx, self.ury) = ur
        self.x, self.y = (self.llx + self.urx) / 2, (self.lly + self.ury) / 2

    def __str__(self):
        return ("%s %s (%f, %f)" % \
            (self.name, self.direction, self.x, self.y))

         
def extract_lef_macro(lines_iter, name):
    """ Extract macro information """

    pin_list = list()
    obses = list()  # obses will be a list of (llx, lly, w, h)
    while True:    
        tokens = next(lines_iter).split()
        try:
            if tokens[0] == 'END':
                if tokens[1] == name: 
                    break

            elif tokens[0] == 'CLASS':
                macro_class = tokens[1]

            elif tokens[0] == 'SIZE':
                width, height = float(tokens[1]), float(tokens[3])

            elif tokens[0] == 'PIN':
                """ Pin information """
                pin_name = tokens[1]
        
                # Dummy code for iccad2014 format parsing
                try:
                    if tokens[2] == 'DIRECTION':    # iccad2014 format
                        direction = tokens[3]
                except IndexError:
                    pass

                while True:
                    tokens = next(lines_iter).split()
                    try:
                        if (tokens[0], tokens[1]) == ('END', pin_name):
                            break
                        elif tokens[0] == 'DIRECTION':
                            direction = tokens[1]

                        elif tokens[0] == 'RECT':
                            ll = (float(tokens[1]), float(tokens[2]))
                            ur = (float(tokens[3]), float(tokens[4]))

                        elif tokens[0] == 'POLYGON':
                            coords = [float(t) for t in tokens[1:-1]]
                            x_coords = coords[0::2]
                            y_coords = coords[1::2]
                            ll = (min(x_coords), min(y_coords))
                            ur = (max(x_coords), max(y_coords))

                    except IndexError:
                        pass

                pin_list.append( LefPin(pin_name, direction, ll, ur) )

            elif tokens[0] == 'OBS':
                # OBS extraction
                tokens = next(lines_iter).split()
                assert tokens[0] == 'LAYER' and tokens[1] == M1_LAYER_NAME

                while True:
                    tokens = next(lines_iter).split()
                    if len(tokens) < 6:
                        break

                    # obses: list of (llx, lly, urx, ury)
                    obses.append( tuple([float(t) for t in tokens[1:-1]]) )

        except IndexError:
            pass

    if len(obses) < 2:
        return LefMacro(name, width, height, macro_class, pin_list)

    else:
        return LefRectilinearMacro(name, width, height, 
                                   macro_class, pin_list, obses)


def parse_lef(lef_file_name):
    """ Parse lef and get size of each gate. """

    # read file without blank lines
    with open(lef_file_name, 'r') as f:
        lines = [l for l in (line.strip() for line in f) if l]
    lines_iter = iter(lines)

    site_list = list()
    gates = list()

    site_name, symmetry, site_class, width, height = (None, ) * 5
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
            site_list.append( LefSite(site_name, symmetry, site_class, 
                                      width, height) )
            print ("\tLEF Site: %s" % (site_list[0]))
        
        # MACRO definition
        elif tokens[0] == 'MACRO':
            gate_name = tokens[1]    # Gate name
            gates.append( extract_lef_macro(lines_iter, gate_name) )

    try:
        assert len(site_list) == 1
    except AssertionError:
        sys.stderr.write("Unsupported LEF file - multiple sites defined.\n")
        raise SystemExit(-1)

    LefTechInfo.lef_site_name = site_list[0].name
    LefTechInfo.lef_site_width = site_list[0].width
    LefTechInfo.lef_site_height = site_list[0].height

    # Assign global vlaues
    global WIDTH_DIVIDER, HEIGHT_DIVIDER
    WIDTH_DIVIDER  = LefTechInfo.metal_layer_dict[M2_LAYER_NAME]
    HEIGHT_DIVIDER = LefTechInfo.metal_layer_dict[M1_LAYER_NAME]

    print ("\tM1 pitch (height divisor): %f" % HEIGHT_DIVIDER)
    print ("\tM2 pitch (width divisor) : %f" % WIDTH_DIVIDER)

    #[print (g.__str__() + g.macro_class + '\n') for g in gates]
    return site_list[0], gates


class DefRow(object):
    def __init__(self, name, site, x, y, orient, m, n, dx, dy):
        self.name = name
        self.site = site
        self.x, self.y = x, y
        self.orient = orient
        self.m, self.n = m, n
        self.dx, self.dy = dx, dy

    def get_bookshelf_row_string(self):
        x_divisor = WIDTH_DIVIDER * LefTechInfo.lef_unit_microns
        y_divisor = HEIGHT_DIVIDER * LefTechInfo.lef_unit_microns

        coordinate = round(self.y / y_divisor)
        height = LefTechInfo.lef_site_height / HEIGHT_DIVIDER
        site_width = LefTechInfo.lef_site_width / WIDTH_DIVIDER
        site_spacing = self.dx / x_divisor

        assert site_width == site_spacing
        subrow_origin = round(self.x / x_divisor)
        num_sites = self.m

        return \
        "CoreRow Horizontal\n"  + \
        "    Coordinate   : %d\n" % (coordinate) + \
        "    Height       : %d\n" % (height) + \
        "    Sitewidth    : %d\n" % (site_width) + \
        "    Sitespacing  : %d\n" % (site_spacing) + \
        "    Siteorient   : N\n" + \
        "    Sitesymmetry : Y\n" + \
        "    SubrowOrigin : %d  NumSites : %d\n" % (subrow_origin, num_sites) + \
        "End\n"


def parse_def(src_def):
    with open(src_def, 'r') as f:
        lines = [l for l in (line.strip() for line in f) if l]

    lines_iter = iter(lines)

    row_list = list()
    component_pl_dict = dict()  # component : (gate_type, is_fixed, (x,y))
    pin_pl_dict = dict()        # pin : (x,y)

    for line in lines_iter:
        tokens = line.split()
        
        if tokens[0] == 'UNITS':
            assert tokens[1] == 'DISTANCE'
            assert tokens[2] == 'MICRONS'
            print (tokens[3])
            assert int(tokens[3]) == LefTechInfo.lef_unit_microns

        elif tokens[0] == 'ROW':
            # ROW name site x y N DO m BY n STEP dx dy
            name = tokens[1]
            site = tokens[2]
            x, y = int(tokens[3]), int(tokens[4])
            orient = tokens[5]
            m, n = int(tokens[7]), int(tokens[9])
            dx, dy = int(tokens[11]), int(tokens[12])
            
            row = DefRow(name, site, x, y, orient, m, n, dx, dy)
            row_list.append(row)

        elif tokens[0] == 'TRACKS':
            # Nothing to do
            pass

        elif tokens[0] == 'GCELLGRID':
            # Nothing to do
            pass

        elif tokens[0] == 'COMPONENTS':
            num_components = int(tokens[1])

            while True:
                tokens = next(lines_iter).split()
                if tokens[0] == 'END' and tokens[1] == 'COMPONENTS':
                    break

                # - name gate_type
                #   + FIXED ( x y ) N ;
                instance_name = tokens[1]
                gate_type = tokens[2]
                
                tokens = next(lines_iter).split()
                is_fixed = True if tokens[1] == 'FIXED' else False
                x, y = (float(tokens[3]), float(tokens[4]))
                orient = tokens[6]

                component_pl_dict[instance_name] = (gate_type, is_fixed, (x,y))

        elif tokens[0] == 'PINS':
            num_pins = int(tokens[1])

            while True:
                tokens = next(lines_iter).split()
                if tokens[0] == 'END' and tokens[1] == 'PINS':
                    break

                # - name + NET net_name
                #   + DIRECTION [INPUT|OUTPUT]
                #   + FIXED ( x y ) N 
                #   + LAYER metal4 ( x y ) ( x y ) ;
                pin_name = tokens[1]
                net_name = tokens[3]

                tokens = next(lines_iter).split()
                direction = tokens[2]

                tokens = next(lines_iter).split()
                is_fixed = True if tokens[1] == 'FIXED' else False
                x, y = (float(tokens[3]), float(tokens[4]))
                orient = tokens[6]
                tokens = next(lines_iter)
                # layer, etc...

                pin_pl_dict[pin_name] = (x, y)

    try:
        assert num_pins == len(pin_pl_dict)
        assert num_components == len(component_pl_dict)
    except AssertionError:
        sys.stderr.write('num_pins != len(pin_pl_dict)\n')
        sys.stderr.write('num_components != len(component_pl_dict)\n')
        raise SystemExit(-1)

    return row_list, component_pl_dict, pin_pl_dict

    
class VerilogGate(object):
    """ Verilog gate information. """
    def __init__(self, gate_type, instance_name):
        self.gate_type = gate_type
        self.instance_name = instance_name
        self.pin_dict = None

    def __str__(self):
        return "%s %s %s" % (self.gate_type, self.instance_name, self.pin_dict) 


def parse_verilog(verilog_file_name):
    """ Parse verilog and get netlist info.
    
    The given verilog must follow the ICCAD/TAU specification
    """

    # read file without blank lines
    with open(verilog_file_name, 'r') as f:
        lines = [l for l in (line.strip() for line in f) if l]
    lines_iter = iter(lines)

    # Get input, output, wire names 
    inputs, outputs, wires = list(), list(), list()
    for line in lines_iter:
        if line.startswith('//'):
            continue

        elif line.startswith('module '):
            while not next(lines_iter).endswith(');'):
                continue# Skip lines
        
        elif line.startswith('input '):
            x = line.split()[1][:-1]  # strip the trailing semicolon
            inputs.append(x)
        
        elif line.startswith('output '):
            x = line.split()[1][:-1]  # strip the trailing semicolon
            outputs.append(x)

        elif line.startswith('wire '):
            while True:
                x = line.split()[1][:-1]  # strip the trailing semicolon
                wires.append(x)
                line = next(lines_iter)

                if not line.startswith('wire '): 
                    break

            break   # stop iteration
       
        elif line.startswith('reg '):
            sys.stderr.write('Error: not a gate-level netlist.\n')
            raise SystemExit(-1)

        else: continue

    # Exclude input and output wires from wires
    wires = list(set(wires) - set(inputs + outputs))

    # Parse gate information
    gates = list()
    for line in lines_iter:
        for c in ['.', ',', '(', ')', ';']:
            line = line.replace(c, ' ')
        
        tokens = line.split()
        if tokens.__len__() < 2 or tokens[0] == '//': continue

        gate_type, instance_name = tokens[0], tokens[1]
        gates.append( VerilogGate(gate_type, instance_name) ) 

        it = iter(tokens[2:])
        gates[-1].pin_dict = {pin : net for (pin, net) in zip(it, it)}

    try:
        assert len(inputs) > 0    
        assert len(outputs) > 0    
        assert len(wires) > 0    
        assert len(gates) > 0
    except AssertionError:
        print ("Error: Verilog parsing...")
        sys.exit(-1)

    return inputs, outputs, wires, gates


def write_bookshelf_nodes(dest, gates, inputs, outputs, 
                          lef_macros, fix_big_macros):

    f_nodes = open(dest + '.nodes', 'w')

    f_nodes.write('UCLA nodes 1.0\n', )
    f_nodes.write('# File header with version information, etc.\n')
    f_nodes.write('# Anything following "#" is a comment, '
                  'and should be ignored\n\n')
    f_nodes.write("NumNodes\t:\t%d\n" % (len(gates + inputs + outputs)))

    num_terminals = len(inputs + outputs)

    # Establish macro dictionary
    big_macros = {g.name : g for g in lef_macros if g.macro_class == 'BLOCK'}
    big_block_set = set(big_macros.keys())
    std_cells = {g.name : g for g in lef_macros if g.macro_class == 'CORE'}
    std_cells_set = set(std_cells.keys())
    assert len(big_macros) + len(std_cells) == len(lef_macros)

    if fix_big_macros:
        num_terminals += len([g for g in gates if g.gate_type in big_macros])
    f_nodes.write("NumTerminals\t:\t%d\n\n" % (num_terminals))

    # movable node
    total_area_in_bs = 0

    # Standard cells
    for g in gates:
        # Find width and height from LEF
        if g.gate_type in std_cells_set:
            lef_macro = std_cells[g.gate_type]

            width_in_bs = ceil(lef_macro.width / WIDTH_DIVIDER)
            height_in_bs = ceil(lef_macro.height / HEIGHT_DIVIDER)
            # total_width_in_bs += width_in_bs
            total_area_in_bs += width_in_bs * height_in_bs

            f_nodes.write("%-40s %15d %15d\n" % \
                          (g.instance_name, int(width_in_bs), int(height_in_bs)))

        elif g.gate_type in big_block_set:
            lef_macro = big_macros[g.gate_type]

            width_in_bs = ceil(lef_macro.width / WIDTH_DIVIDER)
            height_in_bs = ceil(lef_macro.height / HEIGHT_DIVIDER)
            # total_width_in_bs += width_in_bs
            total_area_in_bs += width_in_bs * height_in_bs

            f_nodes.write("%-40s %15d %15d " % \
                          (g.instance_name, int(width_in_bs), int(height_in_bs)))

            if fix_big_macros:
                f_nodes.write("%15s\n" % ('terminal'))
            else:
                f_nodes.write("\n")

        else:
            sys.stderr.write("Cannot find macro definition for %s. \n" % (g))
            raise SystemExit(-1)

    # Ports
    for t in inputs + outputs:
        f_nodes.write("%15s %15d %15d %15s\n" % (t, 1, 1, 'terminal'))
    
    f_nodes.close()

    # return total_width_in_bs
    return total_area_in_bs


def write_bookshelf_nets(dest, inputs, outputs, wires, clock_port, gates, lef_macros):
    # Exclude clock port
    try:
        inputs.remove(clock_port)
    except ValueError:
        sys.stderr.write("Warning: the clock port %s does not exist, "
                         "or it is already removed.\n" % clock_port)

    # Generate bookshelf nets
    f_nets = open(dest + '.nets', 'w')

    f_nets.write('UCLA nets 1.0\n')
    f_nets.write('# File header with version information, etc.\n')
    f_nets.write('# Anything following "#" is a comment, and should be ignored\n\n')

    # NumNets = #inputs + #outputs + #wires - 1 (for clock net)
    nets = inputs + outputs + wires
    f_nets.write("NumNets\t:\t%d\n" % (len(nets)))

    # net dictionary - key: name, val: list( [name, I|O, x_offset, y_offset] )
    net_dict = {n : [[n, 'I', 0.0, 0.0]] for n in inputs}
    net_dict.update( {n : [[n, 'O', 0.0, 0.0]] for n in outputs} )
    net_dict.update( {n : list() for n in wires} )

    num_pins = len(inputs + outputs)

    # For fast lookup
    lef_gate_dict = {lg.name: lg for lg in lef_macros}
    for g in gates:
        # lef_gate = [lg for lg in lef_macros if lg.name == g.gate_type][0]
        lef_gate = lef_gate_dict[g.gate_type]
        node_name = g.instance_name
        # Node center
        node_x = (lef_gate.width / WIDTH_DIVIDER) * 0.5
        node_y = (lef_gate.height / HEIGHT_DIVIDER) * 0.5

        for k, v in g.pin_dict.items():
            if v == clock_port: continue
            num_pins += 1
            try:
                lef_pin = [p for p in lef_gate.pin_list if p.name == k][0]
            except IndexError:
                sys.stderr.write('Error: Verilog and LEF do not match:' \
                                 '(v, lef) = (%s, %s)\n' % (g, lef_gate))
                raise SystemExit(-1)

            lef_pin_x = lef_pin.x / WIDTH_DIVIDER 
            lef_pin_y = lef_pin.y / HEIGHT_DIVIDER 

            direction = lef_pin.direction
            x_offset = lef_pin_x - node_x
            y_offset = lef_pin_y - node_y

            net_dict[v].append([node_name, direction, x_offset, y_offset])
        
    f_nets.write("NumPins\t:\t%d\n" % (num_pins))
    for net, pins in sorted(net_dict.items()):
        f_nets.write("NetDegree : %d  %s\n" % (len(pins), net))
        for p in pins:
            f_nets.write("        %s  %s : %11.4f %11.4f\n" % (p[0], p[1][0], p[2], p[3]))
        f_nets.write("")
                    
    f_nets.close()


def write_bookshelf_wts(dest, inputs, outputs, wires):
    f_wts = open(dest + '.wts', 'w')
    f_wts.write('UCLA wts 1.0\n')
    f_wts.write('# File header with version information, etc.\n')
    f_wts.write('# Anything following "#" is a comment, and should be ignored\n\n')

    inputs  = sorted(inputs)
    outputs = sorted(outputs)
    wires   = sorted(wires)
    for net in inputs + outputs + wires:
        f_wts.write("%s %d\n" % (net, 1))

    f_wts.close()


def write_bookshelf_scl(dest, total_area_in_bs, util=0.7, row_list=None):

    if row_list is not None:
        """ Write a scl file with pre-defined row list """
        
        with open(dest + '.scl', 'w') as f:
            f = open(dest + '.scl', 'w')
            f.write("UCLA scl 1.0\n\n")
            f.write("NumRows : %d\n\n" % (len(row_list)))

            for row in row_list:
                f.write(row.get_bookshelf_row_string())

        return

    site_height_in_bs = int(ceil(LefTechInfo.lef_site_height / HEIGHT_DIVIDER))
    site_width_in_bs = int(ceil(LefTechInfo.lef_site_width / WIDTH_DIVIDER))
    site_spacing = site_width_in_bs

    # placement_area = total_width_in_bs * site_height_in_bs / util
    placement_area = total_area_in_bs / util
    x_length = ceil(placement_area**0.5)
    y_length = ceil(x_length / site_height_in_bs) * site_height_in_bs
    num_row = ceil(x_length / site_height_in_bs)
   
    site_orient = 'N'
    site_symmetry = 'Y'
    subrow_origin = 0

    f_scl = open(dest + '.scl', 'w')
    f_scl.write("UCLA scl 1.0\n\n")
    f_scl.write("NumRows : %d\n\n" % (num_row))

    for i in range(num_row):
        f_scl.write("CoreRow Horizontal\n")
        f_scl.write("    Coordinate     : %d\n" % (i*site_height_in_bs))
        f_scl.write("    Height         : %d\n" % (site_height_in_bs))
        f_scl.write("    Sitewidth      : %d\n" % (site_width_in_bs))
        f_scl.write("    Sitespacing    : %d\n" % (site_width_in_bs))
        f_scl.write("    Siteorient     : N\n")
        f_scl.write("    Sitesymmetry   : Y\n")
        f_scl.write("    SubrowOrigin   : 0    ")
        f_scl.write("    NumSites : %d\n" % (int(x_length)))
        f_scl.write("End\n")

    f_scl.close()

    return x_length, y_length  


def write_bookshelf_pl(dest, pl_width, pl_height, 
                       component_pl_dict=None, pin_pl_dict=None,
                       fix_big_macros=False):

    f_pl = open(dest+ '.pl', 'w')
    f_pl.write('UCLA pl 1.0\n\n')

    # nodes file - skip the first line
    lines = [x.rstrip() for x in open(dest+ '.nodes', 'r') 
             if not x.startswith('#')][1:]
    lines_iter = iter(lines)

    num_nodes, num_terminals = 0, 0
    terminal_list = list()

    x_divisor = WIDTH_DIVIDER * LefTechInfo.lef_unit_microns
    y_divisor = HEIGHT_DIVIDER * LefTechInfo.lef_unit_microns

    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue

        elif tokens[0] == 'NumNodes':
            num_nodes = int(tokens[2])

        elif tokens[0] == 'NumTerminals':
            num_terminals = int(tokens[2])

        # Node definitions
        else:
            try: 
                assert len(tokens) in [3,4]

            except AssertionError:
                sys.stderr.write("len(tokens) not in [3,4]\n")
                raise SystemExit(-1)

            node_name = tokens[0]

            if component_pl_dict is not None \
                and node_name in component_pl_dict.keys():
                coord = component_pl_dict[node_name][2]
                x = int(round(coord[0] / x_divisor))
                y = int(round(coord[1] / y_divisor))
                f_pl.write("%s\t%d\t%d\t: N" % (node_name, x, y))

                if fix_big_macros:
                    f_pl.write(" /FIXED\n")
                    assert tokens[-1] == 'terminal'
                    terminal_list.append(tokens[0])    

                else:
                    f_pl.write("\n")

            elif 'terminal' in tokens[1:]:
                terminal_list.append(tokens[0])    

            else:
                f_pl.write("%s\t%d\t%d\t: N\n" % (node_name, 0, 0))


    try: 
        assert len(terminal_list) == num_terminals
    except AssertionError:
        sys.stderr.write("len(terminal_list) != num_terminals\n")
        raise SystemExit(-1)

    # Pin placement
    if pin_pl_dict is not None:

        for name, coord in sorted(pin_pl_dict.items()):
            x = int(round(coord[0] / x_divisor))
            y = int(round(coord[1] / y_divisor))
            f_pl.write("%s\t%d\t%d\t: N /FIXED\n" \
                       % (name, x, y))

    # If initial pin placement is not given, generate
    else:
        # determine num_ports in each edge.    
        max_ports_in_edge = ceil(len(terminal_list) / 4)
        num_ports = [max_ports_in_edge] * 4

        diff = max_ports_in_edge * 4 - len(terminal_list)
        for i in range(diff):
            num_ports[3-i] -= 1

        south = [(i*(pl_width / num_ports[0]), 0.0) 
                 for i in range(num_ports[0])]
        east  = [(pl_width, i*(pl_height / num_ports[1])) 
                 for i in range(num_ports[1])]
        north = [(pl_width - i*(pl_width / num_ports[2]), pl_height) 
                 for i in range(num_ports[2])]
        west  = [(0.0, pl_height - i*(pl_height / num_ports[3])) 
                 for i in range(num_ports[3])]

        coords = south + east + north + west
        for terminal, p in zip(terminal_list, coords):
            f_pl.write("%s\t%d\t%d\t: N\n" \
                       % (terminal, round(p[0]), round(p[1])))
                        
    f_pl.close()


def write_bookshelf_shapes(dest, lef_macros, component_pl_dict=None):

    with open(dest + '.shapes', 'w') as f:
        f.write('shapes 1.0\n\n')
        macros = {m.name : m for m in lef_macros 
                  if m.__class__ == LefRectilinearMacro}

        rectilinear_nodes = dict()

        if component_pl_dict is None:
            f.write('NumNonRectangularNodes : 0\n\n')

        for k, v in component_pl_dict.items():
            instance_name = k
            gate_type = v[0]
        
            if gate_type in macros.keys():
                macro = macros[gate_type]
                _val = list(v)
                _val.append(macro)
                rectilinear_nodes[instance_name] = _val

        f.write('NumNonRectangularNodes : %d\n\n' % (len(rectilinear_nodes)))

        for k, v in rectilinear_nodes.items():
            # node = [gate_type, is_fixed, (x,y), macro]
            # macro is of LefRectilinearMacro
            name = k

            x_divisor = WIDTH_DIVIDER * LefTechInfo.lef_unit_microns
            y_divisor = HEIGHT_DIVIDER * LefTechInfo.lef_unit_microns

            x_pl, y_pl = v[2]
            x_pl /= x_divisor
            y_pl /= y_divisor

            macro = v[3]
            num_obs = len(macro.obses)

            f.write("%s : %d\n" % (name, num_obs))
            for i in range(num_obs):
                shape_id = 'Shape_%d' % (i)
                obs = macro.obses[i]

                # llx, lly, urx, ury = obs    # in LEF unit

                # in DEF unit
                llx, lly, urx, ury = \
                    [i*LefTechInfo.lef_unit_microns for i in obs]

                x = int(round(llx / x_divisor)) + x_pl
                y = int(round(lly / y_divisor)) + y_pl
                w = int(round((urx - llx) / x_divisor))
                h = int(round((ury - lly) / y_divisor))

                f.write("    %s %d %d %d %d\n" \
                        % (shape_id, x, y, w, h))


def gen_bookshelf(src_v, src_lef, src_def, fix_big_macros, 
                  clock_port, remove_clock_port, utilization, dest):
    # Parse verilog and lef
    print ("Parsing Verilog.")
    inputs, outputs, wires, gates = parse_verilog(src_v)

    if remove_clock_port:
        try:
            inputs.remove(clock_port)
        except ValueError:
            sys.stderr.write("Specified clock port doesn't exist.\n")
            raise SystemExit(-1)

    print ("Parsing LEF.")
    lef_site, lef_macros = parse_lef(src_lef)

    if src_def is not None:
        print ("Parsing DEF.")
        row_list, component_pl_dict, pin_pl_dict = parse_def(src_def)

    # Hyper graph
    # Generate bookshelf nodes
    print ("Writing nodes.")
    # total_width_in_bs = write_bookshelf_nodes(dest, gates, inputs, outputs, lef_macros)
    total_area_in_bs = write_bookshelf_nodes(dest, gates, inputs, outputs, 
                                             lef_macros, fix_big_macros)
    
    # Bookshelf nets file - doesn't include the clock net
    print ("Writing nets.")
    write_bookshelf_nets(dest, inputs, outputs, wires, clock_port, \
                            gates, lef_macros)

    # Generate bookshelf wts
    print ("Writing wts.")
    write_bookshelf_wts(dest, inputs, outputs, wires)

    # Placement informatoin
    if src_def is not None:
        print ("Writing scl.")
        write_bookshelf_scl(dest, None, None, row_list)

        print ("Writing pl.")
        write_bookshelf_pl(dest, None, None, 
                          component_pl_dict, pin_pl_dict, fix_big_macros)

    else:
        # Bookshelf scl file
        print ("Writing scl.")
        pl_width, pl_height = write_bookshelf_scl(dest, total_area_in_bs, utilization)

        # Bookshelf pl file
        print ("Writing pl.")
        write_bookshelf_pl(dest, pl_width, pl_height)

    if src_def is not None:
        print ("Writing shapes.")
        write_bookshelf_shapes(dest, lef_macros, component_pl_dict)

    print ("Writing aux.")
    # bookshelf aux
    f_aux = open(dest + '.aux', 'w')
    f_aux.write("RowBasedPlacement : " \
                "%s.nodes %s.nets %s.wts %s.pl %s.scl %s.shapes" \
                % (dest, dest, dest, dest, dest, dest))
    f_aux.close()
    print ("Done.\n")


if __name__ == '__main__':
    cl_opt = parse_cl()

    src_v = cl_opt.src_v
    src_lef = cl_opt.src_lef
    src_def = cl_opt.src_def
    fix_big_macros = cl_opt.fix_big_macros
    clock_port = cl_opt.clock_port
    remove_clock_port = cl_opt.remove_clock_port
    src_sdc = cl_opt.input_sdc
    utilization = cl_opt.utilization
    dest = cl_opt.dest_name

    # Command line parameter checking
    print ("Input Verilog     :  %s" % (src_v))
    print ("Input LEF         :  %s" % (src_lef))

    if src_def is not None:
        print ("Input DEF         :  %s" % (src_def))
        print ("Fix big macros    :  %r" % (fix_big_macros))
        print ("--util will be ignored.")
    else:
        print ("Utilization       :  %f" % float(utilization))
        print ("--fix_big_macros will be ignored.")

    if src_sdc is not None:
        print ("Input SDC         :  %s" % (src_sdc))
        print ("Clock port        :  %s" % (clock_port))
        print ("\t Clock port was extracted from the input SDC.")
    else:
        print ("Clock port        :  %s" % (clock_port))

    if remove_clock_port:
        print ("Remove clock port :  %r" % (remove_clock_port))
        print ("\tBookshelf file will not have the clock port.")
    print ("Output file       :  %s" % (dest))
    print ("")

    gen_bookshelf(src_v, src_lef, src_def, fix_big_macros, 
                  clock_port, remove_clock_port, utilization, dest)

