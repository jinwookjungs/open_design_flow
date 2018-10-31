# File: gen_bookshelf.py
# Description: Generate a Bookshelf file set (.aux, .nets, .wts, .nodes) from 
#              the given verilog and lef file.
# Author: Jinwook Jung (jinwookjungs@gmail.com)
# Last modification: 2016-07-23

from __future__ import print_function, division
from time import gmtime, strftime
from copy import deepcopy
from math import ceil
import sys

import verilog_parser
import def_parser
import lef_parser

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
    parser.add_argument('--fix_big_blocks', action="store_true",
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




def write_bookshelf_nodes(dest, the_verilog, the_lef, the_def, fix_big_blocks):

    gates = [g for g in the_verilog.instances if g.gate_type not in ('PI', 'PO')]
    inputs = the_verilog.inputs
    outputs = the_verilog.outputs

    f_nodes = open(dest + '.nodes', 'w')

    f_nodes.write('UCLA nodes 1.0\n', )
    f_nodes.write('# File header with version information, etc.\n')
    f_nodes.write('# Anything following "#" is a comment, '
                  'and should be ignored\n\n')

    num_inputs    = len(inputs)
    num_outputs   = len(outputs)
    num_big_blocks = len(the_def.big_blocks)

    f_nodes.write("NumNodes\t:\t%d\n" % (len(gates) + num_inputs + num_outputs + num_big_blocks))

    if fix_big_blocks:
        num_terminals = num_inputs + num_outputs + num_big_blocks
    else:
        num_terminals = num_inputs + num_outputs

    f_nodes.write("NumTerminals\t:\t%d\n\n" % (num_terminals))

    # Establish macro dictionary
    lef_macros = the_lef.macros
    big_blocks = {g.name : g for g in lef_macros if g.macro_class.startswith('BLOCK')}
    big_block_set = set(big_blocks.keys())
    std_cells = {g.name : g for g in lef_macros if g.macro_class == 'CORE'}
    std_cells_set = set(std_cells.keys())
    assert len(big_blocks) + len(std_cells) == len(lef_macros)

    # movable node
    total_area_in_bs = 0

    # Standard cells
    width_divider  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
    height_divider = the_lef.metal_layer_dict[the_lef.m1_layer_name]

    min_height = 987654321

    for g in the_verilog.instances:
        # Find width and height from LEF
        if g.gate_type in ('PI', 'PO'):
            continue

        if g.gate_type in std_cells_set:
            lef_macro = std_cells[g.gate_type]

            width_in_bs = ceil(lef_macro.width / width_divider)
            height_in_bs = ceil(lef_macro.height / height_divider)
            # total_width_in_bs += width_in_bs
            total_area_in_bs += width_in_bs * height_in_bs

            f_nodes.write("%-40s %15d %15d\n" % \
                          (g.name, int(width_in_bs), int(height_in_bs)))

            min_height = height_in_bs if min_height > height_in_bs else min_height

        else:
            sys.stderr.write("Cannot find macro definition for %s. \n" % (g))
            raise SystemExit(-1)

    # Big block placement
    for g in the_def.big_blocks:
        try:
            lef_macro = big_blocks[g.gate_type]
        except KeyError:
            sys.stderr.write("Lef doesn't have big block definition (%s)" 
                             % (g.gate_type))
            raise SystemExit(-1)

        width_in_bs = ceil(lef_macro.width / width_divider)
        height_in_bs = ceil(lef_macro.height / height_divider)
        # total_width_in_bs += width_in_bs
        total_area_in_bs += width_in_bs * height_in_bs

        f_nodes.write("%-40s %15d %15d " % \
                      (g.name, int(width_in_bs), int(height_in_bs)))

        if fix_big_blocks:
            f_nodes.write("%15s\n" % ('terminal'))
        else:
            f_nodes.write("\n")

    # Ports
    for t in inputs + outputs:
        f_nodes.write("%-40s %15d %15d %15s\n" % (t, min_height, min_height, 'terminal'))
    
    f_nodes.close()

    # return total_width_in_bs
    return total_area_in_bs


def write_bookshelf_nets(dest, the_verilog, the_lef, the_def):
    # Exclude clock port
    try:
        the_verilog.inputs.remove(clock_port)
    except ValueError:
        sys.stderr.write("Warning: the clock port %s does not exist, "
                         "or it is already removed.\n" % clock_port)

    # Generate bookshelf nets
    f_nets = open(dest + '.nets', 'w')

    f_nets.write('UCLA nets 1.0\n')
    f_nets.write('# File header with version information, etc.\n')
    f_nets.write('# Anything following "#" is a comment, and should be ignored\n\n')

    # NumNets = #inputs + #outputs + #wires - 1 (for clock net)
    gates = [g for g in the_verilog.instances if g.gate_type not in ('PI', 'PO')]
    inputs = the_verilog.inputs
    outputs = the_verilog.outputs
    wires = the_verilog.wires

    nets = inputs + outputs + wires
    f_nets.write("NumNets\t:\t%d\n" % (len(nets)))

    # net dictionary - key: name, val: list( [name, I|O, x_offset, y_offset] )
    net_dict = {n : [[n, 'I', 0.0, 0.0]] for n in inputs}
    net_dict.update( {n : [[n, 'O', 0.0, 0.0]] for n in outputs} )
    net_dict.update( {n : list() for n in wires} )

    num_pins = len(inputs + outputs)

    # For fast lookup
    lef_gate_dict = {lg.name: lg for lg in the_lef.macros}


    width_divider  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
    height_divider = the_lef.metal_layer_dict[the_lef.m1_layer_name]

    for g in gates:
        # lef_gate = [lg for lg in lef_macros if lg.name == g.gate_type][0]
        lef_gate = lef_gate_dict[g.gate_type]
        node_name = g.name
        # Node center
        node_x = (lef_gate.width / width_divider) * 0.5
        node_y = (lef_gate.height / height_divider) * 0.5

        # If you are using Python 3.5:
        # pin_dict = {**g.input_pin_dict, **g.output_pin_dict}
        # Else, please you the following code
        pin_dict = dict(list(g.input_pin_dict.items()) 
                        + list(g.output_pin_dict.items()))

        for k, v in pin_dict.items():
            if v == clock_port: continue
            num_pins += 1
            try:
                lef_pin = [p for p in lef_gate.pin_list if p.name == k][0]
            except IndexError:
                sys.stderr.write('Error: Verilog and LEF do not match:' \
                                 '(v, lef) = (%s, %s)\n' % (g, lef_gate))
                raise SystemExit(-1)

            lef_pin_x = lef_pin.x / width_divider 
            lef_pin_y = lef_pin.y / height_divider 

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


def write_bookshelf_wts(dest, the_verilog, the_lef, the_def):
    f_wts = open(dest + '.wts', 'w')
    f_wts.write('UCLA wts 1.0\n')
    f_wts.write('# File header with version information, etc.\n')
    f_wts.write('# Anything following "#" is a comment, and should be ignored\n\n')

    inputs  = sorted(the_verilog.inputs)
    outputs = sorted(the_verilog.outputs)
    wires   = sorted(the_verilog.wires)

    for net in inputs + outputs + wires:
        f_wts.write("%s %d\n" % (net, 1))

    f_wts.close()


def write_bookshelf_scl(dest, the_lef, the_def):
    """ 
    Write a scl file with pre-defined row list 
    """
  
    try:
        assert the_lef.m1_layer_name is not None
        assert the_lef.m2_layer_name is not None
    except AssertionError:
        sys.std.err.write("Error: Please set m1/m2 layer names properly.\n")
        raise SystemExit(-1)

    with open(dest + '.scl', 'w') as f:
        f = open(dest + '.scl', 'w')
        f.write("UCLA scl 1.0\n\n")
        f.write("NumRows : %d\n\n" % (len(the_def.rows)))

        for row in the_def.rows:
            f.write(row.get_bookshelf_row_string(the_lef))

    return


def create_bookshelf_scl(dest, the_lef, total_area_in_bs, util):
    """
    Create bookshelf scl file with a given utilization
    """
    try:
        width_divider  = the_lef.metal_layer_dict[M2_LAYER_NAME]
        height_divider = the_lef.metal_layer_dict[M1_LAYER_NAME]
    except KeyError:
        sys.stderr.write("Error: Lef file is not read properly.\n")
        raise SystemExit(-1)

    site_width_in_bs = int(ceil(the_lef.site_width / width_divider))
    site_height_in_bs = int(ceil(the_lef.site_height / height_divider))
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


def write_bookshelf_pl(dest, the_lef, the_def, fix_big_blocks):

    f_pl = open(dest+ '.pl', 'w')
    f_pl.write('UCLA pl 1.0\n\n')

    # nodes file - skip the first line
    lines = [x.rstrip() for x in open(dest+ '.nodes', 'r') 
             if not x.startswith('#')][1:]
    lines_iter = iter(lines)

    num_nodes, num_terminals = 0, 0
    terminal_list = list()

    width_divider  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
    height_divider = the_lef.metal_layer_dict[the_lef.m1_layer_name]

    x_divisor = width_divider * the_lef.units_distance_microns
    y_divisor = height_divider * the_lef.units_distance_microns

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

            # Standard cell placement
            if node_name in the_def.component_pl_dict.keys():
                coord = the_def.component_pl_dict[node_name][2]
                x = int(round(coord[0] / x_divisor))
                y = int(round(coord[1] / y_divisor))
                f_pl.write("%s\t%d\t%d\t: N\n" % (node_name, x, y))

            # Big block placement
            elif node_name in the_def.big_block_pl_dict.keys():
                coord = the_def.big_block_pl_dict[node_name][2]
                x = int(round(coord[0] / x_divisor))
                y = int(round(coord[1] / y_divisor))
                f_pl.write("%s\t%d\t%d\t: N" % (node_name, x, y))

                if fix_big_blocks:
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
    for name, coord in sorted(the_def.pin_pl_dict.items()):
        x = int(round(coord[0] / x_divisor))
        y = int(round(coord[1] / y_divisor))
        f_pl.write("%s\t%d\t%d\t: N /FIXED\n" \
                   % (name, x, y))

    f_pl.close()



def create_bookshelf_pl(dest, the_lef, pl_width, pl_height, fix_big_blocks):

    f_pl = open(dest+ '.pl', 'w')
    f_pl.write('UCLA pl 1.0\n\n')

    # nodes file - skip the first line
    lines = [x.rstrip() for x in open(dest+ '.nodes', 'r') 
             if not x.startswith('#')][1:]
    lines_iter = iter(lines)

    num_nodes, num_terminals = 0, 0
    terminal_list = list()

    width_divider  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
    height_divider = the_lef.metal_layer_dict[the_lef.m1_layer_name]

    x_divisor = width_divider * the_lef.units_distance_microns
    y_divisor = height_divider * the_lef.units_distance_microns

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

            if 'terminal' in tokens[1:]:
                terminal_list.append(tokens[0])    
            else:
                f_pl.write("%s\t%d\t%d\t: N\n" % (node_name, 0, 0))


    try: 
        assert len(terminal_list) == num_terminals
    except AssertionError:
        sys.stderr.write("len(terminal_list) (%d) != num_terminals (%d)\n" 
                         % (len(terminal_list), num_terminals))
        raise SystemExit(-1)

    # Pin placement
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


def write_bookshelf_shapes(dest, the_verilog, the_lef, the_def):

    with open(dest + '.shapes', 'w') as f:
        f.write('shapes 1.0\n\n')
        rectilinear_macros = {m.name : m for m in the_lef.macros
                              if m.__class__ == lef_parser.LefRectilinearMacro}

        rectilinear_nodes = dict()

        # If you are using Python 3.5:
        # component_pl_dict = {**the_def.component_pl_dict, **the_def.big_block_pl_dict}
        # Else, please you the following code
        component_pl_dict = dict(list(the_def.component_pl_dict.items())
                                 + list(the_def.big_block_pl_dict.items()))

#        if len(component_pl_dict) == 0:
#            f.write('NumNonRectangularNodes : 0\n\n')

        for k, v in component_pl_dict.items():
            instance_name = k
            gate_type = v[0]
        
            if gate_type in rectilinear_macros.keys():
                macro = rectilinear_macros[gate_type]
                _val = list(v)
                _val.append(macro)
                rectilinear_nodes[instance_name] = _val

        f.write('NumNonRectangularNodes : %d\n\n' % (len(rectilinear_nodes)))

        ##
        width_divider  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
        height_divider = the_lef.metal_layer_dict[the_lef.m1_layer_name]

        x_divisor = width_divider * the_lef.units_distance_microns
        y_divisor = height_divider * the_lef.units_distance_microns

        for k, v in rectilinear_nodes.items():
            # node = [gate_type, is_fixed, (x,y), macro]
            # macro is of LefRectilinearMacro
            name = k

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
                    [i*the_lef.units_distance_microns for i in obs]

                x = int(round(llx / x_divisor)) + x_pl
                y = int(round(lly / y_divisor)) + y_pl
                w = int(round((urx - llx) / x_divisor))
                h = int(round((ury - lly) / y_divisor))

                f.write("    %s %d %d %d %d\n" \
                        % (shape_id, x, y, w, h))


def gen_bookshelf(src_v, src_lef, src_def, fix_big_blocks, 
                  clock_port, remove_clock_port, utilization, dest):
    # Parse verilog and lef
    print ("Parsing verilog: %s" % (src_v))
    the_verilog = verilog_parser.Module()
    the_verilog.read_verilog(src_v)
    the_verilog.clock_port = clock_port
    the_verilog.print_stats()

    if remove_clock_port:
        try:
            the_verilog.inputs.remove(clock_port)
            the_verilog.clock_port = None
        except ValueError:
            sys.stderr.write("Specified clock port doesn't exist.\n")
            raise SystemExit(-1)

    print ("Parsing LEF: %s" % (src_lef))
    the_lef = lef_parser.Lef()
    the_lef.set_m1_layer_name(M1_LAYER_NAME)
    the_lef.set_m2_layer_name(M2_LAYER_NAME)
    the_lef.read_lef(src_lef)
    the_lef.print_stats()

    the_def = def_parser.Def()
    if src_def is not None:
        print ("Parsing DEF.")
        the_def.read_def(src_def)
        the_def.print_stats()

    #---------------------------------------
    # Hyper graph
    #---------------------------------------
    # Generate bookshelf nodes
    print ("Writing nodes.")
    total_area_in_bs = write_bookshelf_nodes(dest, the_verilog, the_lef, 
                                                                the_def, 
                                                                fix_big_blocks)
    
    # Bookshelf nets file - doesn't include the clock net
    print ("Writing nets.")
    write_bookshelf_nets(dest, the_verilog, the_lef, the_def)

    # Generate bookshelf wts
    print ("Writing wts.")
    write_bookshelf_wts(dest, the_verilog, the_lef, the_def)

    # Placement informatoin
    if src_def is not None:
        print ("Writing scl.")
        write_bookshelf_scl(dest, the_lef, the_def)

        print ("Writing pl.")
        write_bookshelf_pl(dest, the_lef, the_def, fix_big_blocks)

    else:
        # Bookshelf scl file
        print ("Writing scl.")
        pl_width, pl_height = create_bookshelf_scl(dest, the_lef, total_area_in_bs, utilization)

        # Bookshelf pl file
        print ("Writing pl.")
        create_bookshelf_pl(dest, the_lef, pl_width, pl_height, fix_big_blocks)

    if src_def is not None:
        print ("Writing shapes.")
        write_bookshelf_shapes(dest, the_verilog, the_lef, the_def)

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
    fix_big_blocks = cl_opt.fix_big_blocks
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
        print ("Fix big macros    :  %r" % (fix_big_blocks))
        print ("--util will be ignored.")
    else:
        print ("Utilization       :  %f" % float(utilization))
        print ("--fix_big_blocks will be ignored.")

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

    gen_bookshelf(src_v, src_lef, src_def, fix_big_blocks, 
                  clock_port, remove_clock_port, utilization, dest)


