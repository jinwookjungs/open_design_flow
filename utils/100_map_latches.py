#!/usr/bin/env python
""" Provides the LatchMapper class to generate a netlist with all lates mapped.

Given the verilog output from the ABC, LatchMapper generates a netlist in which 
all latches are mapped to the specified library cell.
"""

__author__ = "Jinwook Jung"
__email__ = "jinwookjungs@gmail.com"
__date__ = "08/27/15"

from time import gmtime, strftime
from textwrap import wrap
import sys, math, argparse

def parse_cl():
    """ Parse command line and return dictionary. """
    parser = argparse.ArgumentParser(
                description='Map all latches of the ABC synthesis result.')

    # Add arguments
    parser.add_argument(
            '-i', action="store", dest='src_v', required=True)
    parser.add_argument(
            '--latch', action="store", dest='latch_cell', required=True)
    parser.add_argument(
            '--clock', action="store", dest='clock_port')
    parser.add_argument(
            '--sdc', action="store", dest='input_sdc')
    parser.add_argument(
            '-o', action="store", dest='dest_v', default='out_lmapped.v')
    parser.add_argument(
            '--remove_source_verilog', action="store_true")

    opt = parser.parse_args()

    if opt.input_sdc is None and opt.clock_port is None:
        parser.error("At least one of --sdc and -c required.")
        raise SystemExit(-1)

    elif opt.input_sdc is not None:
        try:
            # Example: create_clock [get_port <clock_port>] ...
            create_clock = [x.rstrip() for x in open(opt.input_sdc, 'r') \
                                        if x.startswith('create_clock')][0]
            tokens = create_clock.split()
            opt.clock_port = tokens[tokens.index('[get_ports') + 1][:-1]

        except ValueError:
            parser.error("Cannot find the clock port in %s." % (opt.input_sdc))
            raise SystemExit(-1)

        except TypeError:
            parser.error("Cannot open file %s." % (opt.input_sdc))
            raise SystemExit(-1)

    else:   # opt.clock_port is not None
        pass    # Nothing done.

    return opt


class Latch(object):
    """ Contain information about a latch cell. """
    def __init__(self, instance_id, d, q, clk, gtype):
        self.instance_id = instance_id
        self.d = d
        self.q = q
        self.clk = clk
        self.gtype = gtype
    
    def print_latch(self, digit):
        return "%s l%0*d ( .d(%s), .o(%s), .ck(%s) );" % \
                (self.gtype, digit, self.instance_id, 
                 self.d, self.q, self.clk)


class LatchMapper(object):
    """ Latch-mapped netlist generator. """
    def __init__(self):
        self.latch_list = list()


    def map_latches(self, src_v, latch_cell, clock_port, dest_v, rm_source_v):
        """ Map latche cells into the given netlist. """

        with open(src_v, 'r') as f:
            # read lines without blank lines
            lines = [l for l in (line.strip() for line in f) if l]

        lines_iter = iter(lines)

        f_dest = open(dest_v, 'w')
        f_dest.write("// Latch-mapped netlist written by map_latches.py, %s\n"
                     "// Format: ICCAD2015 placement contest\n" % \
                            (strftime("%Y-%m-%d %H:%M:%S", gmtime())))  
        f_dest.write("//    Input file:  " + src_v + "\n")
        f_dest.write("//    Latch cell:  " + latch_cell + "\n")
        f_dest.write("//    Clock port:  " + clock_port + "\n")
        f_dest.write("//    Output file: " + dest_v + "\n//\n")

        for line in lines_iter:
            # write_verilog command of ABC always creates a port 'clock'.
            if line.startswith('module'):
                f_dest.write("\n\n" + line.rstrip(' clock,') + "\n")

                while True:
                    line = next(lines_iter)
                    tokens = line.split()
                    [ f_dest.write(t + "\n") for t in tokens]
                    if line.endswith(');'):
                        f_dest.write("\n// Start PIs\n")
                        break

            # write_verilog command of ABC always writes 'input  clock;', 
            # so remove it
            elif line == 'input  clock;':
                continue

            # Start PIs
            elif line.startswith('input'):
                tokens = line.split()
                input_list = [t[:-1] for t in tokens[1:]]   # strip the trailing ',' or ';'

                while not line.endswith(';'):
                    line = next(lines_iter)
                    tokens = line.split(' ')
                    input_list.extend( [t[:-1] for t in tokens[0:]] )

                for i in input_list:
                    f_dest.write("input %s;\n" % (i))

                f_dest.write("\n// Start POs\n")

            # Start POs
            elif line.startswith('output'):
                tokens = line.split()
                output_list = [t[:-1] for t in tokens[1:]]   # strip the trailing ',' or ';'

                while not line.endswith(';'):
                    line = next(lines_iter)
                    tokens = line.split()
                    output_list.extend( [t[:-1] for t in tokens[0:]] )

                for i in output_list:
                    f_dest.write("output %s;\n" % (i))

                f_dest.write("\n// Start wires\n")

            # reg statements should be canged to wire statements.
            elif line.startswith('reg'):
                tokens = line.split()
                net_list = [t[:-1] for t in tokens[1:]]

                while not line.endswith(';'):
                    line = next(lines_iter)
                    tokens = line.split()
                    net_list.extend( [t[:-1] for t in tokens[0:]] )

            # Start wires
            elif line.startswith('wire'):
                tokens = line.split()
                net_list.extend( [t[:-1] for t in tokens[1:]] )

                while not line.endswith(';'):
                    line = next(lines_iter)
                    tokens = line.split()
                    net_list.extend( [t[:-1] for t in tokens[0:]] )

                for i in net_list + input_list + output_list:
                    f_dest.write("wire %s;\n" % (i))
                f_dest.write('\n// Start cells\n')

            # Skip always statement
            elif line.startswith('always'):
                break

            elif line.startswith('//'):
                f_dest.write(line)

            # Format cell instantiations as ICCAD contest format
            else:
                line = ' '.join(line.split())
                i1 = line.find('(')  # Find the first left parenthesis (
                i2 = line.find(');')  # Find the end of the instantiation );

                gate_type, instance = line[:i1].split()
                if gate_type == 'one':
                    gate_type = 'vcc'
                elif gate_type == 'zero':
                    gate_type = 'vss'

                f_dest.write("%s %s ( %s );\n"
                              % (gate_type, instance, line[i1+1:i2]))

        latch_count = 1
        for line in lines_iter:
            try:
                # Q <= D;
                for c in ['<', '=', ';']:
                    line = line.replace(c, '')
                tokens = line.split()
                instance_id = latch_count
                latch_count += 1
                latch = Latch(instance_id, tokens[1], tokens[0],
                              clock_port, latch_cell)
                self.latch_list.append(latch)

            except IndexError:
                break

        digit = int(math.log(len(self.latch_list),10)) + 1

        f_dest.write('\n'.join([l.print_latch(digit) for l in self.latch_list]))
        f_dest.write('\n\nendmodule\n')

        f_dest.close()

        if rm_source_v:
            import os
            print ("Remove source verilog file: %s" % (src_v))
            os.remove(src_v)


if __name__ == '__main__':
    opt = parse_cl()
    src_v = opt.src_v
    latch_cell = opt.latch_cell
    clock_port = opt.clock_port
    dest_v = opt.dest_v
    remove_source_verilog = opt.remove_source_verilog

    print ("Input file:  " + src_v)
    print ("Latch cell:  " + latch_cell)
    print ("Clock port:  " + clock_port)
    print ("Output file: " + dest_v)
    sys.stdout.flush()

    mapper = LatchMapper()
    mapper.map_latches(src_v, latch_cell, clock_port, dest_v, remove_source_verilog)
