"""
    Lef parser.
"""


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

    metal_layer_dict = dict()   # layer name : pitches


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


class LefMacro(object):
    """ Lef Macro """
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


def parse_lef(file_name):
    """ Parse lef and get size of each gate. """

    # read file without blank lines
    with open(file_name, 'r') as f:
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



