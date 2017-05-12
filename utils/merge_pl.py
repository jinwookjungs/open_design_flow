"""
"""

from time import gmtime, strftime
import sys


def parse_cl():
    import argparse
    parser = argparse.ArgumentParser(description='Merge pl.')

    parser.add_argument('--nodes', action="store", dest='nodes', required=True)
    parser.add_argument('--src', action="store", dest='src_pl', required=True)
    parser.add_argument('--ref', action="store", dest='ref_pl', required=True)

    opt = parser.parse_args()

    return opt.nodes, opt.src_pl, opt.ref_pl


def merge_pl(nodes, src_pl, ref_pl):


    # Find terminal
    lines = [x.rstrip() for x in open(nodes, 'r')]
    terminals = [l.split()[0] for l in lines if l.endswith('terminal')]

    with open(src_pl, 'r') as f_src_pl:
        src_lines = [x.rstrip() for x in f_src_pl]
    with open(ref_pl, 'r') as f_ref_pl:
        ref_lines = [x.rstrip() for x in f_ref_pl]

    with open(src_pl, 'w') as f_pl:
        f_pl = open(src_pl, 'w')
        for l in src_lines:
            try:
                if l.split()[0] in terminals: pass
                else: f_pl.write(l + '\n')
            except IndexError:
                f_pl.write(l + '\n')
     
        for l in ref_lines:
            try:
                tokens = l.split()
                if tokens[0] in terminals:
                    f_pl.write("%s\t%.4f\t%.4f\t: N\n" \
                                % (tokens[0], float(tokens[1]), float(tokens[2])))
            except IndexError:
                pass


if __name__ == '__main__':
    nodes, src_pl, ref_pl = parse_cl()

    print ("Bookshelf nodes: %s" % (nodes))
    print ("Source pl: %s" % (src_pl))
    print ("Reference pl: %s" % (ref_pl))

    merge_pl(nodes, src_pl, ref_pl)
