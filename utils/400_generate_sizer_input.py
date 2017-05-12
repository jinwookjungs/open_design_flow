
from time import gmtime, strftime
import sys, re, os

import verilog_parser

BIG_BLOCK_PREFIX='block_'
TIE_CELLS=('vcc', 'vss')


def parse_cl():
    import argparse
    """ parse and check command line options
    @return: dict - optinos key/value
    """
    parser = argparse.ArgumentParser(
                description='Convert a given gate-level verilog to a blif.')

    # Add arguments
    parser.add_argument(
            '-i', action="store", dest='src_v', required=True)
    parser.add_argument(
            '-o', action="store", dest='dest_v', default='out.v')
    parser.add_argument(
            '--clock', action="store", dest='clock', default='iccad_clk')
    parser.add_argument(
            '--clock_period', action="store", dest='period', default='0.0')

    opt = parser.parse_args()
    return opt


def generate_sizer_input(src, dest, dest_sdc, clock='iccad_clk', period='0.0'):

    module = verilog_parser.Module()

    module.read_verilog(src)
    module.clock_port = clock
    module.print_stats()

    #
    inputs = set(module.inputs[:])
    outputs = set(module.outputs[:])
    wires = set(module.wires[:])

    # Remove big blocks and tie cells
    blocks, ties, std_cells = list(), list(), list()

    for i in module.instances:
        if i.gate_type.startswith('block'):
            blocks.append(i)
            [inputs.add(net) for pin,net in i.output_pin_dict.items()]
            [outputs.add(net) for pin,net in i.input_pin_dict.items()]

        elif i.gate_type in ('vcc', 'vss'):
            ties.append(i)
            [inputs.add(net) for pin,net in i.output_pin_dict.items()]

        elif i.gate_type in ('PI', 'PO'):
            continue

        else:
            std_cells.append(i)

    # Remove floating logic
    for net_name, net in module.net_dict.items():
        # If the number of connected nodes to the net is 1
        if len(net.nodes) == 1:
            # Get the node
            node = net.nodes[0]
            if node.gate_type.startswith('block'):
                continue    # blocks are already removed

            if node.gate_type in ('PI', 'PO'):
                continue    # don't touch PI/POs

            # Find the pin connected to the net
            pin_dict = dict(node.input_pin_dict)
            pin_dict.update(node.output_pin_dict)

            pin = [p for p,n in pin_dict.items() if n == net_name][0]

            # Create a dummy port
            if pin.startswith('o'):
                outputs.add(net_name)
            else:
                inputs.add(net_name)

    # block to block connection?
    outputs = outputs - inputs
    wires = wires - set(list(inputs) + list(outputs))

    # Write verilog
    sizer = verilog_parser.Module()
    sizer.name, sizer.clock_port = (module.name, clock)

    (sizer.inputs, sizer.outputs, sizer.wires) = \
        (list(inputs), list(outputs), list(wires))

    sizer.instances = std_cells[:]

    # Generate circuit graph 
    sizer.create_pio_nodes()
    sizer.construct_circuit_graph()
    sizer.print_stats()

    sizer.write_verilog(dest)
    sizer.write_sdc(dest_sdc, period)


if __name__ == '__main__':
    opt = parse_cl()
    src = opt.src_v
    dest = opt.dest_v
    clock = opt.clock
    period = float(opt.period)

    _offset = dest.find('.v')
    if _offset == -1:
        dest = dest + '.v'
        dest_sdc = dest + '.sdc'
    else:
        dest_sdc = dest[:_offset] + '.sdc'
        
    print ("Input file     : " + src)
    print ("Output file    : " + dest)
    print ("Output sdc     : " + dest_sdc)
    print ("Clock port     : " + clock)
    print ("Clock period   : " + repr(period))
    sys.stdout.flush()

    generate_sizer_input(src, dest, dest_sdc, clock, period)
    print ("Done")
