# File: gen_bookshelf.py
# Description: Create a new DEF given a verilog, lef, pl, and initial DEF.
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
    @return:
    """
    import argparse

    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--lef', action="store", dest='src_lef', required=True)
    parser.add_argument('--def', action="store", dest='src_def', required=True)
    parser.add_argument('--verilog', action="store", dest='src_v', required=True)
    parser.add_argument('--pl', action="store", dest='final_pl')
    parser.add_argument('--def_out', action="store", dest='dest_def', default='out.def')

    opt = parser.parse_args()

    return opt


def parse_pl(pl_file_name):
    """
    Return a dictionary including placement information.
    Key: name, Value: (x, y, orient)
    """
    with open(pl_file_name, 'r') as f:
        # read lines without blank lines
        lines = [l for l in (line.strip() for line in f) if l]

    # Skip the first line: UCLA nodes ...
    lines_iter = iter(lines[1:])
 
    pl_dict = dict()
    for l in lines_iter:
        if l.startswith('#'): continue

        tokens = l.split()
        assert len(tokens) >= 5

        name, x, y, orient = \
            tokens[0], float(tokens[1]), float(tokens[2]), tokens[4]

        # for ICCAD
        orient = 'N'

        pl_dict[name] = (x, y, orient)

    return pl_dict


def write_def(dest_def, src_lef, src_def, src_v, src_pl):

    print ("Parsing LEF: %s" % (src_lef))
    the_lef = lef_parser.Lef()
    the_lef.read_lef(src_lef)
    the_lef.print_stats()
    the_lef.m1_layer_name = 'metal1'
    the_lef.m2_layer_name = 'metal2'

    width_multiplier  = the_lef.metal_layer_dict[the_lef.m2_layer_name]
    height_multiplier = the_lef.metal_layer_dict[the_lef.m1_layer_name]
    dbu_per_micron    = the_lef.units_distance_microns

    print ("Parsing DEF: %s" % (src_def))
    the_def = def_parser.Def()
    the_def.read_def(src_def)
    the_def.print_stats()

    print ("Parsing verilog: %s" % (src_v))
    the_verilog = verilog_parser.Module()
    the_verilog.read_verilog(src_v)
    the_verilog.clock_port = 'iccad_clk'    # clock_port will not be used in this code
    the_verilog.print_stats()

    # Get placement info
    print ("Parsing bookshelf pl: %s" %(src_pl))
    pl_dict = parse_pl(src_pl)    # name : (x, y, orient)

    # Create new def file
    print ("Write def file")
    new_def = deepcopy(the_def)
    new_def.file_name = dest_def
    new_def.components = list()

    for g in the_verilog.instances:
        if g.gate_type in ('PI', 'PO'):
            continue

        name = g.name
        gate_type = g.gate_type
        is_fixed = False
        x, y, orient = pl_dict[name]
        x = x * dbu_per_micron * width_multiplier
        y = y * dbu_per_micron * height_multiplier

        new_def.components.append(
                def_parser.DefComponent(name, gate_type, is_fixed, x, y, orient))

    new_def.print_stats()
    new_def.write_def(dest_def)


if __name__ == '__main__':
    cl_opt = parse_cl()

    src_v = cl_opt.src_v
    src_lef = cl_opt.src_lef
    src_def = cl_opt.src_def
    dest_def = cl_opt.dest_def
    src_pl = cl_opt.final_pl

    print ("LEF         : " + src_lef)
    print ("DEF         : " + src_def)
    print ("Netlist     : " + src_v)
    print ("Bookshelf pl: " + src_pl)
    print ("Output DEF  : " + dest_def)
    print ("")

    write_def(dest_def, src_lef, src_def, src_v, src_pl)
