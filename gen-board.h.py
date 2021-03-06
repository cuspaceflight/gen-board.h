#! /usr/bin/python3

import argparse
import collections
import os
import textwrap
import sys

import yaml

HEADER = textwrap.dedent("""\
/*
    ChibiOS - Copyright (C) 2006..2016 Giovanni Di Sirio
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
*/

/*
    Generated by gen-board.h.py based on {yamlfile}
*/

#ifndef _BOARD_H_
#define _BOARD_H_


/*
    Setup for {name}
*/

/*
    Board identifier
*/
#define BOARD_{name}
#define BOARD_NAME                     "{name}"

/*
    Board oscillators-related settings.
*/
#if !defined(STM32_LSECLK)
#define STM32_LSECLK                   {lsefreq}U
#endif

#if !defined(STM32_HSECLK)
#define STM32_HSECLK                   {hsefreq}U
#endif

/*
    Board voltages
    Required for performance limits calculation.
*/
#define STM32_VDD                      {voltage}U

/*
    MCU type as defined in the ST header.
*/
#define {mcutype}

""")

IO_PORT_SETUP = textwrap.dedent("""\
/*
    I/O ports initial setup, this configuration is established soon after reset
    in the initialization code.
     Please refer to the STM32 Reference Manual for details.
*/
#define PIN_MODE_INPUT(n)              (0U << ((n) * 2U))
#define PIN_MODE_OUTPUT(n)             (1U << ((n) * 2U))
#define PIN_MODE_ALTERNATE(n)          (2U << ((n) * 2U))
#define PIN_MODE_ANALOG(n)             (3U << ((n) * 2U))
#define PIN_OD_LOW(n)                  (0U << (n))
#define PIN_OD_HIGH(n)                 (1U << (n))
#define PIN_OTYPE_PUSHPULL(n)          (0U << (n))
#define PIN_OTYPE_OPENDRAIN(n)         (1U << (n))
#define PIN_OSPEED_VERYLOW(n)          (0U << ((n) * 2U))
#define PIN_OSPEED_LOW(n)              (1U << ((n) * 2U))
#define PIN_OSPEED_MEDIUM(n)           (2U << ((n) * 2U))
#define PIN_OSPEED_HIGH(n)             (3U << ((n) * 2U))
#define PIN_PUPD_FLOATING(n)           (0U << ((n) * 2U))
#define PIN_PUPD_PULLUP(n)             (1U << ((n) * 2U))
#define PIN_PUPD_PULLDOWN(n)           (2U << ((n) * 2U))
#define PIN_AFIO_AF(n, v)              ((v) << (((n) % 8U) * 4U))

""")

FOOTER = textwrap.dedent("""\
#if !defined(_FROM_ASM_)
#ifdef __cplusplus
extern "C" {
#endif
  void boardInit(void);
#ifdef __cplusplus
}
#endif
#endif /* _FROM_ASM_ */

#endif /* _BOARD_H_ */""")


class MCU():
    def __init__(self, mcutype):
        mcu_filename = self._choose_mcu_file(mcutype)

        with open(mcu_filename) as mcu_file:
            mcu_def = yaml.load(mcu_file)
        self.ports = mcu_def['ports']
        self.pins_per_port = mcu_def['pins_per_port']

    def _choose_mcu_file(self, mcutype):
        types = self._mcu_types()
        rank_types = sorted(types,
                            key=lambda x: self._match_names(mcutype, x),
                            reverse=True)
        choice = rank_types[0]
        score = self._match_names(mcutype, choice)

        if score <= 0:
            print("Error: No matching mcu type definition found.")
            sys.exit(1)
        mcu_filename = os.path.join(self._mcu_dir(), choice + ".yaml")
        return mcu_filename

    def _match_names(self, test, x):
        score = 0
        for tc, xc in zip(test, x):
            if tc == xc:
                score += 1
            elif x == "x":
                continue
            else:
                score -= 1
        return score

    def _mcu_types(self):
        return [name[:-5]
                for name in os.listdir(self._mcu_dir())
                if name[-5:] == ".yaml"]

    def _mcu_dir(self):
        script_path = os.path.abspath(__file__)
        script_dir = os.path.dirname(script_path)
        return os.path.join(script_dir, "mcu")


class Pins():
    _Pin = collections.namedtuple("Pin", ['name', 'port', 'num',
                                          'mode', 'od', 'otype',
                                          'ospeed', 'pupd', 'af',
                                          'raw'])

    def __init__(self, board_def):
        self.mcu = MCU(board_def['mcutype'])

        default, _ = self._parse_data_str(board_def['default'], True)

        self._pins = {port: [self._Pin(name="PIN{}".format(n),
                                       port=port,
                                       num=n,
                                       raw="unused",
                                       **default)
                             for n in range(self.mcu.pins_per_port)]
                      for port in self.mcu.ports}

        self._pins_by_name = {}

        for name, pin_data in board_def['pins'].items():
            pin = self._parse_pin_data(name, pin_data, default)
            self._pins[pin.port][pin.num] = pin
            self._pins_by_name[pin.name] = pin

    def _parse_data_str(self, pin_data, default=False):
        pin = {}
        raw = []
        for elm in pin_data.split(","):
            elm = elm.strip().upper()
            if(elm[0] == "P" and
               elm[1] in self.mcu.ports and
               int(elm[2:]) < self.mcu.pins_per_port):
                pin['port'] = elm[1]
                pin['num'] = int(elm[2:])
            elif elm in ['INPUT',
                         'OUTPUT',
                         'ANALOG']:
                if 'mode' in pin:
                    print("Error: You cannot specify both an AF and a mode")
                    sys.exit(1)
                pin['mode'] = elm
                pin['af'] = 0
                raw += [elm]
            elif elm in ['STARTLOW',
                         'STARTHIGH']:
                pin['od'] = elm[5:]
                raw += [elm]
            elif elm in ['PUSHPULL',
                         'OPENDRAIN']:
                pin['otype'] = elm
                raw += [elm]
            elif elm in ['VERYLOWSPEED',
                         'LOWSPEED',
                         'MEDIUMSPEED',
                         'HIGHSPEED']:
                pin['ospeed'] = elm[:-5]
                raw += [elm]
            elif elm in ['FLOATING',
                         'PULLUP',
                         'PULLDOWN']:
                pin['pupd'] = elm
                raw += [elm]
            elif elm[:2] == "AF":
                if 'mode' in pin:
                    print("Error: You cannot specify both an AF and a mode")
                    sys.exit(1)
                pin['mode'] = "ALTERNATE"
                pin['af'] = int(elm[2:])
                raw += [elm]
            else:
                print("Error: Invalid pin keyword {} at {}!".format(elm,
                                                                    pin_data))
                sys.exit(1)

        if default:
            self._default_check_data(pin)
        return pin, raw

    def _default_check_data(self, pin):
        if 'mode' not in pin:
            print("Error: Default must specify either INPUT, OUTPUT, ANALOG or an AF.")
            sys.exit(1)
        elif 'od' not in pin:
            print("Error: Default must specify either STARTLOW or STARTHIGH.")
            sys.exit(1)
        elif 'otype' not in pin:
            print("Error: Default must specify either PUSHPULL or OPENDRAIN.")
            sys.exit(1)
        elif 'ospeed' not in pin:
            print("Error: Default must specify either VERYLOWSPEED, LOWSPEED, MEDIUMSPEED, HIGHSPEED.")
            sys.exit(1)
        elif 'pupd' not in pin:
            print("Error: Default must specify either FLOATING, PULLUP or PULLDOWN.")
            sys.exit(1)
        elif 'port' in pin:
            print("Error: You cannot specify a PXN for default.")
            sys.exit(1)

    def _parse_pin_data(self, name, pin_data, default):
        pin = {"name": name.upper()}
        pin.update(default)

        data, raw = self._parse_data_str(pin_data)

        pin.update(data)

        pin['raw'] = ", ".join(raw).lower()

        return self._Pin(**pin)

    def pin_by_name(self, name):
        return self._pins_by_name[name]

    def pin_by_port(self, port, num):
        return self._pins[port.upper()][num]

    def iter_names(self):
        return iter(self._pins_by_name)

    def iter_ports(self):
        return sorted(iter(self._pins))

    def iter_port(self, port):
        return iter(self._pins[port.upper()])


def write_io_pins(board, pins):
    board.write(textwrap.dedent("""\
        /*
            IO pins assignments.
        */

        """))

    for port in pins.iter_ports():
        for pin in pins.iter_port(port):
            board.write("#define GPIO{port}_{name}{pad}{num}U\n".format(
                port=pin.port,
                name=pin.name,
                num=pin.num,
                # Pad line to start the pin number at 40 chars
                pad=" "*(39-14-len(pin.name))))
        board.write("\n")


def write_io_lines(board, pins):
    board.write(textwrap.dedent("""\
    /*
        IO lines assignments.
    */

    """))

    for name in sorted(pins.iter_names()):
        pin = pins.pin_by_name(name)
        board.write(
            "#define LINE_{name}{pad}PAL_LINE(GPIO{port}, {num}U)\n".format(
                name=pin.name,
                port=pin.port,
                num=pin.num,
                # Pad line to start PAL_LINE at 40 chars
                pad=" "*(39-13-len(pin.name))))
    board.write("\n")


def write_io_ports(board, pins):
    for port in pins.iter_ports():
        board.write(textwrap.dedent("""\
            /*
             *  GPIO{port} setup:
             *
            """).format(port=port))
        for pin in pins.iter_port(port):
            board.write(" * P{port}{num:<3}- {name:<29}({modes}).\n".format(
                port=pin.port,
                num=pin.num,
                name=pin.name,
                modes=pin.raw))
        board.write("*/\n")
        for mode in ['MODE', 'OTYPE', 'OSPEED', 'PUPD', 'OD']:
            out = "{:<39}(".format(
                "#define VAL_GPIO{port}_{mode}R".format(port=port,
                                                        mode=mode))
            out += " | \\\n                                        ".join(
                ["PIN_{mode}_{data}(GPIO{port}_{name})".format(
                    mode=mode,
                    data=pin._asdict()[mode.lower()],
                    port=pin.port,
                    name=pin.name)
                 for pin in pins.iter_port(port)])
            out += ")\n"
            board.write(out)

        afrl = "#define VAL_GPIO{port}_AFRL                 (".format(
            port=port)
        afrl += " | \\\n                                        ".join(
            ["PIN_AFIO_AF(GPIO{port}_{name}, {af}U)".format(
                port=port,
                name=pin.name,
                af=pin.af)
             for pin in pins.iter_port(port) if pin.num < 8])
        afrl += ")\n"
        board.write(afrl)

        afrh = "#define VAL_GPIO{port}_AFRH                 (".format(
            port=port)
        afrh += " | \\\n                                        ".join(
            ["PIN_AFIO_AF(GPIO{port}_{name}, {af}U)".format(
                port=port,
                name=pin.name,
                af=pin.af)
             for pin in pins.iter_port(port) if pin.num >= 8])
        afrh += ")\n"
        board.write(afrh)
        board.write("\n")


def process_yaml(board_def):
    # Voltages in the form 330 (3v3), 500 (5v)
    board_def['voltage'] = int(board_def['voltage']*100)
    return board_def


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("yamlfile",
                        help="YAML board definition fle to read.")
    parser.add_argument("outfile", nargs="?", default="board.h",
                        help="File to write to. [board.h]")

    return parser.parse_args()


def main():
    args = get_args()

    with open(args.yamlfile, "r") as def_file:
        board_def = yaml.load(def_file)

    board_def = process_yaml(board_def)
    pins = Pins(board_def)

    with open(args.outfile, "w") as board:
        board.write(HEADER.format(yamlfile=args.yamlfile,
                                  **board_def))

        write_io_pins(board, pins)

        write_io_lines(board, pins)

        board.write(IO_PORT_SETUP)

        write_io_ports(board, pins)

        board.write(FOOTER)

if __name__ == "__main__":
    main()
