"""
    A Verilog parser (for ISPD/ICCAD/TAU contest verilog files).
"""

import sys, operator

__tie_cells__ = ('vcc', 'vss')
__dff_name__ = 'ms00f80'
__block_prefix__ = 'block_'

class Net(object):
    def __init__(self, name):
        self.name = name
        self.nodes = list()

    def __str__(self):
        return "%s %d" % (self.name, len(self.nodes))


def get_pin_number(instance):
    """ instance is an instance of Instance. """
    gate_type = instance.gate_type

    if gate_type in __tie_cells__ \
       or gate_type.startswith(__block_prefix__):
        return 1
    
    elif gate_type == __dff_name__ :
        return 3

    else:
        try:
            return int(gate_type[2]) + int(gate_type[3]) + 1
        except IndexError:
            return 1


class Instance(object):
    """ Verilog gate information. """
    def __init__(self, gate_type, name):
        self.gate_type = gate_type
        self.name = name
        self.input_pin_dict = dict()
        self.output_pin_dict = dict()


    def __str__(self):
        return "%s %s %s %s" % \
               (self.gate_type, self.name,
                self.input_pin_dict, self.output_pin_dict) 


    def write_verilog(self):
        val = self.gate_type + ' ' + self.name + ' ( '
        output_pin_string, input_pin_string = list(), list()

        for k,v in self.output_pin_dict.items():
            output_pin_string.append(".%s(%s)" % (k,v))

        for k,v in self.input_pin_dict.items():
            input_pin_string.append(".%s(%s)" % (k,v))

        input_pin_string.sort()

        output_pins = ', '.join(sorted(output_pin_string))
        input_pins = ', '.join(sorted(input_pin_string))

        val += output_pins + ', ' + input_pins + ' );'
        return val


class Module(object):
    def __init__(self):
        self.name = None
        self.inputs = list()
        self.outputs = list()
        self.wires = list()
        self.clock_port = None  # clock port name

        self.instances = list()

        # circuit graph as a dictionary
        # (k,v) : (net, net instances)
        # v.nodes = node list connected to k
        self.net_dict = dict()


    def get_instance_count(self):
        return len(self.instances) - len(self.inputs) - len(self.outputs)


    def print_stats(self):
        print ("==================================================")
        print ("Name               : %s" % (self.name))
        print ("Name of clock port : %s" % (self.clock_port))
        print ("Number of inputs   : %d" % (len(self.inputs)))
        print ("Number of outputs  : %d" % (len(self.outputs)))
        print ("Number of wires    : %d" % (len(self.wires)))

        num_instances = len(self.instances) - (len(self.inputs + self.outputs))

        print ("Number of instances: %d" % (num_instances))

        big_blocks = [i for i in self.instances \
                      if i.gate_type.startswith(__block_prefix__)]
        if not len(big_blocks) == 0:
            print ("Number of macros   : %d" % (len(big_blocks)))

        tie_cells = [i for i in self.instances if i.gate_type in __tie_cells__]
        if not len(tie_cells) == 0:
            print ("Number of tie cells: %d" % (len(tie_cells)))

        net_degree = {k : len(v.nodes) for k,v in self.net_dict.items() if k != 'iccad_clk'}
        max_fanout = max(net_degree.items(), key=operator.itemgetter(1))
        avg_fanout = sum(net_degree.values()) / float(len(net_degree.values()))

        print ("Maximum net degree : %d (%s)" % (max_fanout[1], max_fanout[0]))
        print ("Average net degree : %f" % (avg_fanout))

        print ("==================================================\n")


    def read_verilog(self, file_name):
        """ Read verilog and get netlist info.
       
        Read a given verilog file and generate the dictionary of the circuit
        graph, as well as input/output/wire lists and a gate list.
        The given verilog must follow the ISPD/ICCAD/TAU specification.
        """

        # read file without blank lines
        with open(file_name, 'r') as f:
            lines = [l for l in (line.strip() for line in f) if l]
        lines_iter = iter(lines)

        # Get input, output, wire names 
        inputs, outputs, wires = list(), list(), list()

        for line in lines_iter:
            if line.startswith('//'):
                continue

            elif line.startswith('module '):
                self.name = line.split()[1]
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

        # Exclude inputs and outputs from wires
        wires = list(set(wires) - set(inputs + outputs))

        self.inputs = inputs
        self.outputs = outputs
        self.wires = wires  # wire = wire - input - output

        # Create PI/PO nodes
        self.create_pio_nodes()

        # Gate node extraction
        for line in lines_iter:
            for c in ['.', ',', '(', ')', ';']:
                line = line.replace(c, ' ')

            tokens = line.split()

            if tokens.__len__() < 2 or tokens[0] == '//': continue

            gate_type, name = tokens[0], tokens[1]
            self.instances.append( Instance(gate_type, name) ) 

            it = iter(tokens[2:])
            for (pin, net) in zip(it, it):
                if pin.startswith('o'):
                    self.instances[-1].output_pin_dict[pin] = net
                else:
                    self.instances[-1].input_pin_dict[pin] = net

        # Circuit graph construction
        self.construct_circuit_graph()

        try:
            assert len(inputs) > 0    
            assert len(outputs) > 0    
            assert len(wires) > 0    
            assert len(self.instances) > 0
        except AssertionError:
            print ("Error: in Verilog parsing...")
            sys.exit(-1)


    def create_pio_nodes(self):
        """ Create PIO nodes. """

        # Remove previously created PI/PO nodes
        for i in self.instances:
            if i.gate_type in ('PI', 'PO'):
                self.instances.remove(i)

        # Create PIO Nodes
        instances = list()
        [instances.append(Instance('PI', i)) for i in self.inputs]
        [instances.append(Instance('PO', o)) for o in self.outputs]

        for i in instances:
            if i.gate_type == 'PI':
                i.output_pin_dict = {'o' : i.name}

            elif i.gate_type == 'PO':
                i.input_pin_dict = {'a' : i.name}

        self.instances.extend(instances)


    def construct_circuit_graph(self):
        """ Circuit graph construction (Net dictionary) """

        # All nets in the circuit
        nets = list()
        [nets.append(Net(i)) for i in self.inputs]
        [nets.append(Net(o)) for o in self.outputs]
        [nets.append(Net(w)) for w in self.wires]

        # Initialize net dictionray
        # Key: net name
        # Value: net instance, which has a node list
        self.net_dict = {n.name : n for n in nets}

        for i in self.instances:
            # (k,v): (pin, net)
            try: 
                for k, v in i.input_pin_dict.items():
                    self.net_dict[v].nodes.append(i)
                for k, v in i.output_pin_dict.items():
                    self.net_dict[v].nodes.append(i)
            except KeyError:
                sys.stderr.write("Error: %s %s\n" % (i.name, i.gate_type))
                raise SystemExit(-1)

                

        # Check floating net
        num_floating_net = 0
        for net_name, net in self.net_dict.items():
            # If the number of connected nodes to the net is 1
            if len(net.nodes) == 1:
                # Get the node
                node = net.nodes[0]
                if node.gate_type.startswith(__block_prefix__):
                    continue    # blocks are not considered

                if node.gate_type in ('PI', 'PO'):
                    continue    # don't touch PI/POs

                # Find the pin connected to the net
                pin_dict = dict(node.input_pin_dict)
                pin_dict.update(node.output_pin_dict)

                pin = [p for p,n in pin_dict.items() if n == net_name][0]

                if num_floating_net < 10:
                    print ("%s %s %s" % (node.name, node.gate_type, net_name))

                num_floating_net += 1
                # print (net_name + ' ' + node.__str__())

        print ("Num floating net: %d" % (num_floating_net))


    def write_verilog(self, file_name):
        inputs = sorted(self.inputs)
        outputs = sorted(self.outputs)
        wires = sorted(self.wires)

        with open(file_name, 'w') as f:
            f.write("module %s (\n" % (self.name))
            f.write(',\n'.join(inputs) + ',\n')
            f.write(',\n'.join(outputs) + ');\n')
            f.write('\n// Start PIs\n')
            [f.write('input %s;\n' % (i)) for i in inputs]
            f.write('\n// Start POs\n')
            [f.write('output %s;\n' % (o)) for o in outputs]
            f.write('\n// Start wires\n')
            [f.write('wire %s;\n' % (w)) for w in inputs]
            [f.write('wire %s;\n' % (w)) for w in outputs]
            [f.write('wire %s;\n' % (w)) for w in wires]
            f.write('\n// Start cells\n')
            [f.write(g.write_verilog() + '\n') 
             for g in self.instances if g.gate_type not in ('PI', 'PO')]
            f.write('\nendmodule\n')


    def write_sdc(self, file_name, clock_period=50000.0):
        inputs = sorted(self.inputs)
        outputs = sorted(self.outputs)

        if self.clock_port is None:
            print("No clock port was set --> exit")
            return

        inputs.remove(self.clock_port)   # FIXME

        with open(file_name, 'w') as f:
            f.write('# Synopsys Design Constraints Format\n\n'
                    '# clock definition\n')
            f.write("create_clock -name mclk -period %.2f [get_ports %s]\n\n" \
                    % (clock_period, self.clock_port))

            f.write('# input delays\n')
            [f.write("set_input_delay 0.0 [get_ports %s] -clock mclk\n" % (i)) for i in inputs]
            f.write("\n")
            f.write('# input drivers\n')
            [f.write("set_driving_cell -lib_cell in01f80 -pin o [get_ports %s]" 
                     " -input_transition_fall 80.0 -input_transition_rise 80.0\n" % (i)) for i in inputs]
            f.write("\n")
            f.write('# output delays\n')
            [f.write("set_output_delay 0.0 [get_ports %s] -clock mclk\n" % (o)) for o in outputs]
            f.write("\n")
            f.write('# output loads\n')
            [f.write("set_load -pin_load 4.0 [get_ports %s]\n" % (o)) for o in outputs]


def extract_pin_and_net(token):
    """ token should be .PIN(NET), or .PIN(NET) """ 
    # replace .,() with blank
    for c in ('.', ',', '(', ')'):
        token = token.replace(c, ' ')

    token = token.strip().split()
    pin, net = token[0], token[1]
    return pin, net


if __name__ == '__main__':
    """ Test """
    def parse_cl():
        import argparse
        parser = argparse.ArgumentParser(description='A Verilog parser.')
        parser.add_argument('-i', action="store", dest='src', required=True)
        opt = parser.parse_args()
        return opt

    opt = parse_cl()
    src = opt.src

    module = Module()
    module.read_verilog(src)
    module.print_stats()



