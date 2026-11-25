# -*- coding: utf-8 -*-
#
# Board visualization for the ST NUCLEO-F401RE.
#
# Runs inside Renode, which embeds IronPython 2 -- hence the print statements
# and the absence of anything from Python 3.
#
# Serves a drawing of the board on one port and live data on another, so a
# learner watches the board rather than reading a log. The plumbing follows
# ck-ra6m5-vis, which solved these problems already; the pin map and the board
# data are this board's own.
#
#   i $ORIGIN/vis/vis_f401re.py
#   serveVisualization 8000

import os
import json
import tempfile
import urllib2
import zipfile
import StringIO
import SocketServer
import SimpleHTTPServer
from threading import Thread, Lock

# Renode's embedded interpreter already has the assemblies loaded and provides
# `clr`, `sys` and the Antmicro namespace, so nothing here adds a reference.
# Trying to add one fails with "Could not add reference to assembly Emulator".
from Antmicro.Renode.Peripherals.Miscellaneous import LED, Button
from Antmicro.Renode.Peripherals.UART import IUART

# For running the course's build. The note above is about the Emulator
# assembly; `System` is a different matter and does need an explicit
# reference -- without one, `from System.Diagnostics import Process` fails
# with "Cannot import name Process". Measured 2026-11-11 in Renode 1.16.1,
# which embeds IronPython 2.7.12 on .NET 8.
#
# Not `subprocess`, which imports here and then refuses the one thing the
# build needs: `stderr=subprocess.STDOUT` raises NotImplementedError,
# "Cannont redirect stderr to stdout yet" (the typo is theirs).
import clr
clr.AddReference("System")
from System.Diagnostics import Process, ProcessStartInfo

dir_path = os.path.dirname(os.path.realpath(__file__))
if dir_path not in sys.path:
    sys.path.append(dir_path)
os.chdir(dir_path)

from websocket_server import WebsocketServer


def dumps(value):
    """JSON for the page, as plain ASCII, whatever the machine's code page is.

    Not json.dumps directly. The text sent to the page has non-ASCII in it --
    Japanese part names, a degree sign -- and Python 2 will happily mix byte
    strings and unicode in one structure and then reach for the interpreter's
    default codec to reconcile them. Inside Renode on a Japanese Windows
    install that codec reports itself as 'unknown' and raises, and the whole
    CATALOGUE, PINS, CONNECTORS, ONBOARD and DIVERGENCES block went with it:
    the page drew an empty board and nothing anywhere said why.

    Saying the encoding removes the guess, and ensure_ascii means what leaves
    here is pure ASCII with \\uXXXX escapes, which no code page can spoil.

    It is not enough on its own. IronPython's json refuses a *unicode* string
    holding a character between U+0080 and U+00FF whatever it is told about
    encodings -- a degree sign raised "'unknown' codec can't decode byte 0xb0"
    with and without the argument above, while the same character as the UTF-8
    bytes "\\xc2\\xb0" went through, and so did Japanese, which is above that
    range. So text in that range is written as byte escapes wherever it appears
    in this file, and tests/sweep.py refuses a literal one.
    """
    return json.dumps(value, encoding="utf-8", ensure_ascii=True)


# --- What this board physically has -----------------------------------------
#
# An STM32F401RE in an LQFP64 package brings out ports A, B and C in full, one
# pin of port D, and two of port H. Renode's generic STM32F4 declares ports A
# through K with sixteen pins each, so the drawing must not simply mirror what
# the simulator offers -- see the 'superset-peripherals' row of
# divergences.json.

REAL_PORTS = {
    "A": range(16),
    "B": range(16),
    "C": range(16),
    "D": [2],
    "H": [0, 1],
}

# The Arduino-compatible headers, which are why this board was chosen. Each
# entry is (silkscreen label, the pin it reaches, what already uses it).
#
# Source: UM1724, 'STM32 Nucleo-64 boards', Arduino connector tables.

# Each list runs in the order the pins are physically arranged, top to bottom,
# with the USB socket at the top -- which is the order UM1724's tables use and
# the order somebody counting holes on the board in front of them will count
# in. The digital headers therefore run downwards from the highest number, and
# CN5 carries an AVDD and a GND above D13 that an earlier version of this table
# left out entirely.

ARDUINO = {
    "CN9": [
        ("D7", "PA8", None),
        ("D6", "PB10", None),
        ("D5", "PB4", None),
        ("D4", "PB5", None),
        ("D3", "PB3", None),
        ("D2", "PA10", None),
        ("D1", "PA2", "USART2 TX, the ST-LINK virtual COM port"),
        ("D0", "PA3", "USART2 RX, the ST-LINK virtual COM port"),
    ],
    "CN5": [
        ("D15", "PB8", "I2C1 SCL"),
        ("D14", "PB9", "I2C1 SDA"),
        ("AVDD", None, "the analog supply"),
        ("GND", None, "ground"),
        ("D13", "PA5", "LD2, the user LED"),
        ("D12", "PA6", None),
        ("D11", "PA7", None),
        ("D10", "PB6", None),
        ("D9", "PC7", None),
        ("D8", "PA9", None),
    ],
    "CN8": [
        ("A0", "PA0", None),
        ("A1", "PA1", None),
        ("A2", "PA4", None),
        ("A3", "PB0", None),
        ("A4", "PC1", None),
        ("A5", "PC0", None),
    ],
    "CN6": [
        ("NC", None, None),
        ("IOREF", None, "3.3 V reference"),
        ("RESET", None, "the reset line"),
        ("3V3", None, "power"),
        ("5V", None, "power"),
        ("GND", None, "ground"),
        ("GND", None, "ground"),
        ("VIN", None, "power"),
    ],
}

# Which side of the drawing each header sits on, and in which order down that
# side, matching the real board with its USB socket at the top. This is the
# Arduino Uno R3 arrangement the NUCLEO-64 follows: power above analog on the
# left, the high digital header above the low one on the right.
#
# The right-hand pair used to be listed CN9 then CN5, which drew D0 at the top
# and D8 below it -- the reverse of the board in front of the learner. Somebody
# counting holes down from the USB socket would have landed on the wrong one
# every time.
CONNECTOR_SIDES = [("CN6", "left"), ("CN8", "left"),
                   ("CN5", "right"), ("CN9", "right")]

CONNECTORS = [(name, side, [(label, pin) for label, pin, _why in ARDUINO[name]])
              for name, side in CONNECTOR_SIDES]

# label -> pin, and pin -> label, for both directions of lookup.
LABEL_TO_PIN = {}
PIN_TO_LABEL = {}
PIN_TO_HEADER = {}
PIN_RESERVED = {}
for _cn, _rows in ARDUINO.items():
    for _label, _pin, _why in _rows:
        if _pin is None:
            continue
        LABEL_TO_PIN[_label] = _pin
        PIN_TO_LABEL[_pin] = _label
        PIN_TO_HEADER[_pin] = _cn
        if _why:
            PIN_RESERVED[_pin] = _why

# Hardware the board carries, as opposed to anything a learner adds later.
# Keyed by the name the board description gives it.
ON_BOARD = {
    "led": {"pin": "PA5", "kind": "LED", "what": "LD2, the green user LED"},
    "button": {"pin": "PC13", "kind": "BUTTON",
               "what": "B1, the blue user button. Idles high, falls when pressed"},
}

# There is no third dictionary here for parts the board description wires up
# but does not carry. There used to be, holding an Si7021 on I2C1, and it was
# the only thing in the drawing that was neither the board nor the learner's
# doing. A sensor is now a palette part like any other, so the board view has
# two kinds of thing on it instead of three: what the board has, and what you
# put there.

POLL_SECONDS = 0.5


# --- What a learner may add --------------------------------------------------
#
# Only parts Renode models faithfully. Anything the simulator cannot represent
# honestly is left out rather than drawn with a caveat, because a part that
# looks connected and is not is exactly the confusion this drawing exists to
# prevent. ADR-0001.
#
# Deliberately short. The fourth exercise needs several LEDs and the board has
# one; that is the whole of what this must support today. A wider catalogue is
# a separate question, and every entry in it has to be checked against what
# Renode actually models before it is offered.

# Each entry carries two sorts of thing. `model`, `bus`, `address`,
# `properties` and `drives` are how the part is declared to Renode. `cat`,
# `attach`, `label`, `label_ja` and `props` are how the page draws it -- which
# group it appears under in the picker, which artwork it gets, and which
# readings it offers to set.
#
# `attach` is the page's word and is derived from the others: "gpio-out" for
# something the pin drives, "gpio-in" for something that drives the pin, "i2c"
# for something on the bus. It is spelled out rather than computed so that the
# drawing and the declaration cannot drift apart silently.
#
# `props` is [name, low, high, unit]. A low and high of None means the page
# offers a plain number box instead of a slider, which is what an unknown range
# or an unknown unit deserves -- a slider labelled with a unit the simulator
# does not actually use would teach something false.

CATALOGUE = {
    # --- parts that go on a pin you choose ---------------------------------
    "LED": {
        "bus": "gpio",
        "cat": "Output",
        "attach": "gpio-out",
        "label": "LED",
        "label_ja": "LED",
        "what": "A light-emitting diode. Drive its pin high to light it.",
        "model": "Miscellaneous.LED",
    },
    "Button": {
        "bus": "gpio",
        "drives": True,   # sends into the pin, rather than being driven by it
        "cat": "Input",
        "attach": "gpio-in",
        "label": "Push button",
        "label_ja": "押しボタン",
        "what": "A push button. Reads low while held, like the board's own.",
        "model": "Miscellaneous.Button",
        "properties": {"invert": "true"},
    },

    # --- parts that go on the I2C bus, at a fixed address ------------------
    #
    # These need no pin chosen: I2C1 is already on PB8 and PB9. The address is
    # the real part's, so a learner can follow its datasheet.
    #
    # Every one of these was checked for a working settable value. A sensor
    # whose reading cannot be changed teaches nothing, however faithful its
    # register model is -- which rules out several well-known parts. See
    # 'Rejected' below.
    "SI7021": {
        "bus": "i2c",
        "cat": "Sensor",
        "attach": "i2c",
        "label": "Si7021 temperature and humidity sensor",
        "label_ja": "Si7021 温度湿度センサ",
        "address": "0x40",
        "what": "A temperature and humidity sensor. The fourth exercise reads "
                "this one. Add it before you start that exercise.",
        "model": "Sensors.SI70xx",
        "properties": {"model": "Model.SI7021"},
        "values": ["Temperature", "Humidity"],
        # The Si7021 datasheet's own ranges.
        "props": [["Temperature", -40, 125, "\xc2\xb0C"],
                  ["Humidity", 0, 100, "%"]],
    },
    "TMP103": {
        "bus": "i2c",
        "cat": "Sensor",
        "attach": "i2c",
        "label": "TMP103 temperature sensor",
        "label_ja": "TMP103 温度センサ",
        "address": "0x70",
        "what": "A temperature sensor. The simplest I2C part here: one byte, "
                "one reading. Start with this one.",
        "model": "Sensors.TMP103",
        "values": ["Temperature"],
        # The TMP103 datasheet's own range.
        "props": [["Temperature", -40, 125, "\xc2\xb0C"]],
    },
    "BMP180": {
        "bus": "i2c",
        "cat": "Sensor",
        "attach": "i2c",
        "label": "BMP180 pressure sensor",
        "label_ja": "BMP180 気圧センサ",
        "address": "0x77",
        "what": "A pressure and temperature sensor. Reports raw pressure with "
                "calibration coefficients you apply yourself.",
        "model": "Sensors.BMP180",
        "values": ["Temperature", "UncompensatedPressure"],
        # UncompensatedPressure is the raw converter reading, not pascals. It
        # gets a number box and no unit, because naming one would be a guess
        # and applying the calibration is the exercise.
        "props": [["Temperature", -40, 85, "\xc2\xb0C"],
                  ["UncompensatedPressure", None, None, "raw"]],
    },
    "ADXL372": {
        "bus": "i2c",
        "cat": "Sensor",
        "attach": "i2c",
        "label": "ADXL372 accelerometer",
        "label_ja": "ADXL372 加速度センサ",
        "address": "0x1D",
        "what": "A three-axis accelerometer. Multi-byte reads, one per axis.",
        "model": "Sensors.ADXL372",
        "values": ["AccelerationX", "AccelerationY", "AccelerationZ"],
        # No unit given: the real part is a +/-200 g device, but which unit
        # Renode's property is in was not established, and a slider reading "g"
        # that is really milli-g is worse than a bare number.
        "props": [["AccelerationX", None, None, ""],
                  ["AccelerationY", None, None, ""],
                  ["AccelerationZ", None, None, ""]],
    },
}

# Parts deliberately not offered, and why. Kept here rather than in a document
# so that the reason is next to the decision when somebody wonders.
#
#   ADXL345    the popular accelerometer, but acceleration is not settable --
#              only MaxFifoDepth is. It would look right and do nothing.
#   TMP108     the source says "This model is a stub, roughly compatible with
#              TMP103". Offer TMP103 and call it a TMP103.
#   SHT21      only humidity is settable; there is no temperature to set.
#   AK09916,   their obvious setters raise instead of setting. They work only
#   ICP_101xx  through Default* properties, which is too sharp an edge here.
#   LSM303DLHC_Gyroscope
#              is a magnetometer. The class name is wrong upstream and
#              offering it under either name teaches something false.
#   Any LCD    Renode models no character LCD and no OLED, in 1.16.1 or
#              1.17.0. An SPI ST7789 exists on master only. The seven-segment
#              display below is the closest honest substitute.
#   SevenSegmentsDisplay
#              real and good, but it needs eight segment wires plus one per
#              digit. Placing that needs a multi-pin picker the page does not
#              have yet. Worth adding; not free.
#   Any second SPI part
#              spi1 takes exactly one device and no address -- it is a
#              single-slot bus in Renode. A palette that let a learner add two
#              would produce a platform that fails to load.

# The board's own hardware, by the name the board description gives it. A
# declaration whose name is not in here was put there by a person -- which is
# how an added part is recognised, rather than by comparing the file against a
# pristine copy of itself. ADR-0006.
BOARD_PERIPHERALS = frozenset(ON_BOARD.keys())

# Parts go here, not into boards/nucleo_f401re.repl. That file is the board and
# is updated for everyone; this one is the learner's own and is what the
# simulation loads.
BOARD_FILE = os.path.join(os.path.dirname(dir_path), "board.repl")

# label -> {"kind", "pin", "port", "index"} for everything a learner has added.
ADDED_PARTS = {}

# The repository, which is not where this process is: the module does
# os.chdir(dir_path) above, so relative paths here mean vis/. Everything that
# runs the build or names an exercise goes through this.
REPO_ROOT = os.path.dirname(dir_path)
EXERCISES_DIR = os.path.join(REPO_ROOT, "exercises")

# One build at a time, refused rather than queued. Held by the plugin instead
# of by the page because the page is a browser tab: a second tab, or one left
# open across a reload, can ask without knowing a build is running, and two
# builds writing one firmware.elf while a reset is in flight is the state this
# exists to make unreachable.
build_lock = Lock()
building = [False]

# Sensor readings the learner typed, by qualified name. Reloading firmware
# resets every peripheral, so without this the one exercise with a sensor
# loses its test input on every build.
#
# The value kept is the one they GAVE, never one read back from the machine.
# A reading does not read back exactly -- 25 returns as 24.99, recorded as
# 'sensor-value-quantisation' -- so restoring what the board reports would
# move the value further from their number on every rebuild.
SET_BY_LEARNER = {}

# What the environment check said, kept so a page connecting later still
# learns it rather than only the page that happened to be open at startup.
ENVIRONMENT = [None]

# The vocabulary this file reports in. Declared rather than left implicit
# because the other half of it -- the sentence a learner reads for each one --
# lives in vis/index.html, and nothing but a test would notice the two
# drifting apart. There is no learner-facing prose in this file at all: a page
# is the only side that knows which language it is showing.
BUILD_TOKENS = ("BUILT", "DID_NOT_COMPILE", "COULD_NOT_BUILD",
                "REFUSED_UNKNOWN", "REFUSED_BUSY",
                # Firmware that arrived rather than being built here. LOADED
                # rather than BUILT because the page says different words for
                # them: one is the learner's code as it is on their machine,
                # the other is a binary from somewhere else, and which one is
                # on the board is the thing they most need to be sure of.
                "LOADED", "REFUSED_NOT_FIRMWARE", "REFUSED_NOTHING_INSIDE",
                # Fetching the build the service made. Success is LOADED, the
                # same as a build handed over by the learner: the spec asks
                # for both to be reported the same way, because a fallback
                # that reports differently is a second feature nobody tested.
                "REFUSED_NO_CREDENTIAL", "REFUSED_NO_RUN",
                # Three ways to have no build, split on 2026-11-12 because
                # one message was serving all of them and was only right
                # for one. NO_RUN keeps its meaning -- a build existed and
                # has been cleared -- and the other two take the cases it
                # was giving the wrong advice to.
                "REFUSED_NO_PUSH", "REFUSED_NEVER_BUILT",
                "REFUSED_FETCH_FAILED")
ENVIRONMENT_TOKENS = ("READY", "INCOMPLETE", "UNCHECKED")

# How much a page may hand over. An exercise's ELF is about 12 KB and a whole
# run's archive about 11 KB, so this is three hundred times what is needed --
# small enough that nothing can fill the container's memory by posting, large
# enough that no real firmware ever meets it.
MAX_UPLOAD = 4 * 1024 * 1024

# What firmware and an archive begin with. Checked instead of trusting a file
# name: a learner renaming something does not change what it is, and the
# simulator's complaint about a file that is not an ELF says nothing a learner
# could act on.
ELF_MAGIC = "\x7fELF"
ZIP_MAGIC = "PK\x03\x04"

# Where the launcher leaves the learner's own credential. Called a secret
# rather than a token throughout, because `token` in this file means an
# outcome -- BUILT, LOADED, REFUSED_... -- and a name shared between a
# vocabulary and a credential is a name that gets one of them printed, and the only host it
# is ever sent to. Both are fixed here rather than taken from a request:
# ADR-0044 makes that a condition of using the credential at all, because this
# port is reachable from any page open in the learner's browser.
SECRET_FILE = "/run/secrets/gh"
API = "https://api.github.com"
LEARNER_WORKFLOW = "check-my-work.yml"


def port_of(pin):
    """'PA10' -> ('gpioPortA', 10)."""
    return ("gpioPort" + pin[1], int(pin[2:]))


def _read_board_file():
    try:
        handle = open(BOARD_FILE)
        try:
            return handle.read()
        finally:
            handle.close()
    except Exception:
        return ""


def _write_board_file(text):
    handle = open(BOARD_FILE, "w")
    try:
        handle.write(text)
    finally:
        handle.close()


def _properties(entry):
    props = entry.get("properties") or {}
    return "".join("    %s: %s\n" % (k, v) for k, v in sorted(props.items()))


def _declaration(name, kind, pin):
    """The .repl text that declares one part.

    Two shapes. A part on a pin needs its own block plus a line in the port's
    block wiring it to that pin. A part on the I2C bus needs only one block,
    because the bus is already on PB8 and PB9 and the address does the routing.
    """
    entry = CATALOGUE[kind]
    model = entry["model"]

    if entry.get("bus") == "i2c":
        return ("\n// added from the board view\n"
                "%s: %s @ i2c1 %s\n%s"
                % (name, model, entry["address"], _properties(entry)))

    port, index = port_of(pin)

    # Which way the signal runs decides where the connection line goes, and
    # getting it wrong makes the platform refuse to load. An LED is driven by
    # the pin, so the port's block points at it. A button drives the pin, so
    # the line lives in the button's own block and points at the port -- which
    # is exactly how the board's own B1 is declared.
    if entry.get("drives"):
        return ("\n// added from the board view\n"
                "%s: %s @ %s\n%s    -> %s@%d\n"
                % (name, model, port, _properties(entry), port, index))

    return ("\n// added from the board view\n"
            "%s: %s @ %s\n%s\n"
            "%s:\n"
            "    %d -> %s@0\n"
            % (name, model, port, _properties(entry), port, index, name))


def _payload(name, kind, pin, address=None):
    """Everything the page needs to draw one added part, in one place.

    Both routes to an added part come through here -- the one that has just
    been declared, and the one adopted from board.repl at startup -- because
    when they built their own dictionaries the adopted part came back missing
    fields and was drawn as a labelled box instead of as the component.

    `kind` is a catalogue key for anything the page offered. For a part a
    person declared by hand it is whatever model name was in the file, which is
    not in the catalogue; that case is flagged rather than guessed at.
    """
    entry = CATALOGUE.get(kind) or {}
    known = kind in CATALOGUE

    attach = entry.get("attach")
    if attach is None:
        attach = "i2c" if address else "gpio-out"
    on_bus = attach == "i2c"

    label = PIN_TO_LABEL.get(pin)

    # Which divergence rows apply to this part. Matched on several names at
    # once -- the kind, the way it attaches, the pin and its Arduino label --
    # because the register keys rows by whichever of those a reader would
    # recognise.
    tokens = [kind, kind.upper(), attach, pin, label]
    if on_bus:
        tokens += ["i2c", "PB8", "PB9"]

    return {
        "path": ("sysbus.i2c1." + name) if on_bus else name,
        "label": name,
        "labels": [name],
        "kind": kind,
        "cat": entry.get("cat") or ("Sensor" if on_bus else "Output"),
        "attach": attach,
        "handWired": not known,
        "pin": None if on_bus else pin,
        "pinNames": [] if on_bus else ([pin] if pin else []),
        "busPins": ["PB8", "PB9"] if on_bus else [],
        "pins": ("I2C " + str(address)) if on_bus else (label or pin or "?"),
        "address": address,
        "props": entry.get("props", []),
        "values": entry.get("values", []),
        "divergences": divergences_for(tokens),
    }


def scan_board_file():
    """Find the parts a learner has added, from the file rather than memory.

    Read at startup so that a part added in an earlier session, or declared by
    hand, is drawn like any other. Recognised by name: anything the real board
    does not carry was put there by a person.
    """
    found = {}
    text = _read_board_file()
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        # 'name: Namespace.Model @ node'
        if ":" in stripped and "@" in stripped and not stripped.startswith("gpioPort"):
            name = stripped.split(":", 1)[0].strip()
            model = stripped.split(":", 1)[1].split("@")[0].strip()
            if name in BOARD_PERIPHERALS:
                continue
            kind = None
            for candidate, entry in CATALOGUE.items():
                if entry["model"] == model:
                    kind = candidate
            current = {"kind": kind or model, "pin": None, "label": None}
            # A part on the bus carries its address where a pin would be.
            after_at = stripped.split("@", 1)[1].strip()
            if after_at.startswith("i2c1"):
                rest = after_at[len("i2c1"):].strip()
                current["address"] = rest or None
                current["label"] = rest or None
                if kind:
                    current["values"] = CATALOGUE[kind].get("values", [])
            found[name] = current
        # '    10 -> name@0' under a port block
        elif "->" in stripped and current is not None:
            left, right = stripped.split("->", 1)
            target = right.split("@")[0].strip()
            if target in found:
                try:
                    found[target]["index"] = int(left.strip())
                except ValueError:
                    pass
    return found


def resolve_added_pins(found):
    """Work out which pin each added part sits on.

    Two forms to read, because the connection line lives in a different place
    depending on which way the signal runs:

        gpioPortA:            a part the pin drives, such as an LED
            5 -> led@0

        button: ... @ gpioPortC   a part that drives the pin
            -> gpioPortC@13
    """
    text = _read_board_file()
    port = None
    part = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if stripped.startswith("gpioPort") and stripped.endswith(":"):
            port, part = stripped[:-1], None
            continue

        if ":" in stripped and "@" in stripped:
            name = stripped.split(":", 1)[0].strip()
            part = name if name in found else None
            port = None
            continue

        if "->" not in stripped:
            continue
        left, right = stripped.split("->", 1)

        if port and left.strip():
            # port block: index -> part@0
            target = right.split("@")[0].strip()
            if target in found:
                try:
                    found[target]["pin"] = "P%s%d" % (port[len("gpioPort"):],
                                                      int(left.strip()))
                except ValueError:
                    pass
        elif part and not left.strip():
            # part block: -> gpioPortX@index
            node = right.split("@")[0].strip()
            if node.startswith("gpioPort"):
                try:
                    found[part]["pin"] = "P%s%d" % (node[len("gpioPort"):],
                                                    int(right.split("@")[1].strip()))
                except (ValueError, IndexError):
                    pass
    return found


def adopt_added_parts():
    global ADDED_PARTS
    found = resolve_added_pins(scan_board_file())
    ADDED_PARTS = {}
    for name, part in found.items():
        ADDED_PARTS[name] = _payload(name, part.get("kind"), part.get("pin"),
                                     part.get("address"))
    for name, part in ADDED_PARTS.items():
        where = part.get("pin") or ("I2C " + str(part.get("address") or "?"))
        print "Adopted added part: %s (%s on %s)" % (name, part.get("kind"), where)


def refuse(client, why):
    send_to(client, "|".join(["REFUSED", why, ""]))


def add_part(client, kind, pin):
    """Declare a part, in the running machine and in the board file."""
    if kind not in CATALOGUE:
        return refuse(client, "There is no %s in the palette." % kind)

    entry = CATALOGUE[kind]
    on_bus = entry.get("bus") == "i2c"
    pins = pin_map()

    if on_bus:
        # No pin to choose: the bus is already wired. Only the address can
        # collide, and two devices answering one address is a real fault on
        # hardware too.
        label = entry["address"]
        name = kind.lower()
        for existing_name, existing in ADDED_PARTS.items():
            if existing.get("address") == entry["address"]:
                return refuse(client, "%s is already at address %s on this bus."
                              % (existing_name, entry["address"]))
        if name in ADDED_PARTS or name in BOARD_PERIPHERALS:
            return refuse(client, "There is already a %s on the board." % kind)
        info = None
    else:
        if pin not in pins:
            return refuse(client, "%s is not a pin this device brings out." % pin)

        info = pins[pin]
        if info.get("occupant"):
            return refuse(client, "%s already has %s on it."
                          % (pin, info["occupant"]))
        if info.get("reserved"):
            return refuse(client, "%s is %s. Using it would break that."
                          % (pin, info["reserved"]))
        for existing in ADDED_PARTS.values():
            if existing.get("pin") == pin:
                return refuse(client, "%s already has a part on it." % pin)

        label = info.get("label") or pin
        name = "%s_%s" % (kind.lower(), label.lower())
        if name in ADDED_PARTS or name in BOARD_PERIPHERALS:
            return refuse(client, "There is already something called %s." % name)

    declaration = _declaration(name, kind, pin)

    # Written to a file and loaded the way a board description is.
    # LoadPlatformDescriptionFromString cannot carry a newline through the
    # monitor, and this declaration needs two blocks: the part itself, and the
    # port line that wires it to a pin.
    part_file = os.path.join(tempfile.gettempdir(), "f401re_add_%s.repl" % name)
    try:
        handle = open(part_file, "wb")
        try:
            handle.write(declaration)
        finally:
            handle.close()
        with machine_lock:
            monitor.Parse("machine LoadPlatformDescription @%s"
                          % part_file.replace(chr(92), "/"))
    except Exception as e:
        return refuse(client, "The simulator would not take that: %s"
                      % str(e).split(chr(10))[0][:160])

    # Parse reports a bad description by printing rather than raising, so the
    # only trustworthy check is whether the part is actually in the machine.
    # Writing board.repl for something that did not load would leave the
    # drawing and the machine disagreeing, which is the one thing this must
    # never do.
    present = False
    try:
        with machine_lock:
            if on_bus:
                present = machine["sysbus.i2c1." + name] is not None
            else:
                for kind_type in (LED, Button):
                    for part in machine.GetPeripheralsOfType[kind_type]():
                        if machine.GetLocalName(part) == name:
                            present = True
    except Exception:
        pass
    if not present:
        return refuse(client, "The simulator did not accept that part. "
                              "Nothing was written to board.repl.")

    try:
        _write_board_file(_read_board_file().rstrip("\n") + "\n" + declaration)
    except Exception as e:
        return refuse(client, "Added to the running board, but could not write "
                              "board.repl: %s" % e)

    record = _payload(name, kind, None if on_bus else pin,
                      entry["address"] if on_bus else None)
    ADDED_PARTS[name] = record

    # Hook it so the page sees it change, exactly like the board's own LED.
    try:
        with machine_lock:
            for led in machine.GetPeripheralsOfType[LED]():
                if machine.GetLocalName(led) == name:
                    led.StateChanged += blink_led
    except Exception:
        pass

    send_message("|".join(["ADDED", name, dumps(record)]))
    # The pin this went on is no longer free, and the drawing colours every
    # hole from this map. Without the resend it stayed amber, and the picker
    # went on offering a pin the next add would be refused for.
    send_message("PINS|" + dumps(pin_map()) + "|")
    print "Added %s on %s" % (name, pin)


def _without_part(text, name):
    """The board file with one added part taken out, and nothing else.

    A part appears in the file in one of two shapes, and this used to
    understand only the first:

        gpioPortB:                                  <- an LED: the wiring
            6 -> led_d10@0                             sits in the port block

        button_d2: Miscellaneous.Button @ gpioPortA <- a button: its own
            invert: true                               block, wiring pointing
            -> gpioPortA@10                            out of it

    Removing a button used to delete its first line only and leave the two
    indented lines orphaned, after which the board description no longer
    loaded at all. A learner who added a button and changed their mind was
    left with a board that would not start and nothing to say why.

    Pure, so both shapes can be tested without a running machine.
    """
    lines = text.splitlines()
    out, index = [], 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # Shape one: the part's own block. Take the header and everything
        # indented under it, however many properties it has.
        if stripped.startswith(name + ":"):
            while out and out[-1].strip().startswith("// added from"):
                out.pop()
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if nxt.strip() and not nxt[:1].isspace():
                    break          # a new declaration at column 0
                index += 1
            continue

        # Shape two: a wiring line inside somebody else's block.
        if "->" in stripped and stripped.split("->", 1)[1].split("@")[0].strip() == name:
            index += 1
            continue

        out.append(line)
        index += 1

    # A port block that existed only to wire that part is now empty, and an
    # empty block is not valid here.
    pruned = []
    for position, line in enumerate(out):
        if line.strip().endswith(":") and not line[:1].isspace():
            rest = out[position + 1:]
            has_body = False
            for following in rest:
                if not following.strip():
                    continue
                if following[:1].isspace():
                    has_body = True
                break
            if not has_body:
                while pruned and pruned[-1].strip().startswith("// added from"):
                    pruned.pop()
                continue
        pruned.append(line)

    while pruned and not pruned[-1].strip():
        pruned.pop()
    return "\n".join(pruned) + "\n"


def remove_part(client, name):
    """Take a part out of the board file. The running machine keeps it.

    Renode cannot un-declare a peripheral from a running machine, so the file
    is the truth and the page says the simulation must be restarted. Pretending
    otherwise would leave the drawing and the machine disagreeing, which is the
    one thing this tool must not do.
    """
    if name not in ADDED_PARTS:
        return refuse(client, "%s is not something you added." % name)

    _write_board_file(_without_part(_read_board_file(), name))
    del ADDED_PARTS[name]
    send_message("|".join(["REMOVED", name, ""]))
    send_message("PINS|" + dumps(pin_map()) + "|")
    print "Removed %s from board.repl" % name


# --- Divergences -------------------------------------------------------------

DIVERGENCES_FILE = os.path.join(os.path.dirname(dir_path), "divergences.json")


def load_divergences():
    try:
        handle = open(DIVERGENCES_FILE)
        try:
            return json.load(handle).get("divergences", [])
        finally:
            handle.close()
    except Exception as e:
        print "Could not read divergences.json:", e
        return []


DIVERGENCES = load_divergences()


def divergences_for(tokens):
    """Rows whose shows_up_in overlaps any of `tokens`."""
    wanted = set(t for t in tokens if t)
    out = []
    for row in DIVERGENCES:
        if wanted & set(row.get("shows_up_in", [])):
            out.append(row)
    return out


# --- The pin map the page draws ---------------------------------------------

def pin_map():
    """Every pin the real device brings out, and what is on it."""
    pins = {}
    for port, indices in REAL_PORTS.items():
        for index in indices:
            name = "P%s%d" % (port, index)
            entry = {
                "port": port,
                "index": index,
                "header": PIN_TO_HEADER.get(name),
                "label": PIN_TO_LABEL.get(name),
                "reserved": PIN_RESERVED.get(name),
                "occupant": None,
                "kind": None,
                "onboard": False,
            }
            pins[name] = entry

    for name, part in ON_BOARD.items():
        if part["pin"] in pins:
            pins[part["pin"]]["occupant"] = name
            pins[part["pin"]]["kind"] = part["kind"]
            pins[part["pin"]]["onboard"] = True
            pins[part["pin"]]["what"] = part["what"]

    # PB8 and PB9 are left free rather than marked as taken. They carry I2C1,
    # which the ARDUINO table already records as reserved, and nothing sits on
    # them until a learner adds a sensor.

    # Anything a learner added, so a reloaded page shows what is really on the
    # board rather than an empty drawing that then refuses a collision with an
    # invisible part.
    for name, part in ADDED_PARTS.items():
        pin = part.get("pin")
        if pin in pins:
            pins[pin]["occupant"] = name
            pins[pin]["kind"] = part.get("kind")
            pins[pin]["onboard"] = False
            pins[pin]["added"] = True
            pins[pin]["what"] = "%s, which you added" % part.get("kind")

    return pins


def board_hardware():
    """The board's own parts, described the way an added part is.

    Sent so the page draws LD2, B1 and the Si7021 from one source rather than
    from a second copy of the pin map written into the HTML.

    Everything here is soldered to a real NUCLEO-F401RE. Anything that is not
    is a palette part, and travels as an ADDED payload instead.
    """
    out = {}
    for name, part in ON_BOARD.items():
        out[name] = {
            "pin": part["pin"],
            "pins": [part["pin"]],
            "kind": part["kind"],
            "what": part["what"],
            "path": name,
            "divergences": divergences_for([name, part["kind"], part["pin"],
                                            PIN_TO_LABEL.get(part["pin"])]),
        }
    return out


def _source_fingerprint():
    """A short hash of this file, so a stale page is detectable.

    The page reports what it was told; a mismatch against the file on disk
    means somebody edited the plugin and did not restart Renode.
    """
    try:
        handle = open(os.path.realpath(__file__), "rb")
        try:
            body = handle.read()
        finally:
            handle.close()
        total = 0
        for ch in body:
            total = (total * 131 + ord(ch)) & 0xFFFFFFFF
        return "%08x" % total
    except Exception:
        return "unknown"


PLUGIN_FINGERPRINT = _source_fingerprint()


# --- Serving -----------------------------------------------------------------

DATA_PORT = 9001


class NoCacheHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """Serve without caching, and tell the page its own data socket.

    A browser will otherwise serve a previous run's page from cache, which then
    talks to the wrong socket and looks like a dead board. The port is injected
    as the page is served rather than written into the file, so one checkout can
    serve any number of instances.
    """

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        SimpleHTTPServer.SimpleHTTPRequestHandler.end_headers(self)

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        """Take firmware a learner has handed over. The only POST served.

        This is the route that needs no credential: the learner's own browser
        is already signed in to GitHub, so they download a build there and
        hand the file to this page. It is also what an expired credential and
        an SSH clone fall back to, and credentials expire -- so it is built
        before anything leans on it and exercised by the same tests.

        The request carries an exercise name and bytes. It carries no path and
        no destination, and the name is checked against the exercises on disk
        before anything is done with it (ADR-0043, ADR-0044).

        The outcome goes back over the websocket rather than in this response,
        because every other outcome does and a page should not have to learn
        two ways of hearing the same news. This answers only whether the bytes
        arrived.
        """
        route = self.path.split("?", 1)[0]
        if route != "/firmware":
            self.send_error(404, "No such route")
            return

        exercise = ""
        if "?" in self.path:
            for pair in self.path.split("?", 1)[1].split("&"):
                if pair.startswith("exercise="):
                    exercise = pair[len("exercise="):]

        try:
            length = int(self.headers.getheader("content-length") or 0)
        except Exception:
            length = 0
        if length <= 0:
            self.send_error(400, "No firmware in the request")
            return
        if length > MAX_UPLOAD:
            self.send_error(413, "Firmware larger than %d bytes" % MAX_UPLOAD)
            return

        try:
            blob = self.rfile.read(length)
        except Exception:
            self.send_error(400, "The firmware did not arrive intact")
            return

        self.send_response(204)
        self.end_headers()

        # After answering, and inside a try: this runs on the connection's own
        # thread, so an exception here would drop the connection and the page
        # would be left believing the board was about to change.
        try:
            load_uploaded(exercise, blob)
        except Exception as e:
            print("Could not load what the page handed over: %s" % e)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                target = self.translate_path("/index.html")
                f = open(target, "rb")
                try:
                    body = f.read()
                finally:
                    f.close()
            except Exception:
                return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
            inject = "<script>window.VIS_DATA_PORT = %d;</script>" % DATA_PORT
            at = body.find("<title>")
            body = (body[:at] + inject + body[at:]) if at != -1 else (inject + body)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)


# The polling thread and the message handler both write to the socket, and the
# bundled websocket_server is not thread safe.
send_lock = Lock()

# Renode's object model is not safe to walk from more than one thread, and
# several do: the poller, the message handler, and one per connected page.
machine_lock = Lock()

websocket_server = None
websocket_thread = None
main_server = None
server_thread = None
machine = None
uart_event_map = {}
polling = [True]


def send_message(message):
    if websocket_server is None:
        return
    with send_lock:
        for client in list(websocket_server.clients):
            try:
                websocket_server.send_message(client, message)
            except Exception:
                pass


def send_to(client, message):
    with send_lock:
        try:
            websocket_server.send_message(client, message)
        except Exception:
            pass


# What the program has printed so far, so a page that connects late is not
# shown an empty panel. Firmware often prints once at startup and then falls
# quiet; opening the board a minute later would otherwise look identical to a
# program that printed nothing at all.
UART_HISTORY = []
UART_HISTORY_LIMIT = 8000


def send_uart_chars(char, uart_name):
    text = chr(char)
    UART_HISTORY.append((uart_name, text))
    if len(UART_HISTORY) > UART_HISTORY_LIMIT:
        del UART_HISTORY[:len(UART_HISTORY) - UART_HISTORY_LIMIT]
    send_message("|".join(["UART", uart_name, text]))


def blink_led(led, state):
    send_message("|".join(["LED", machine.GetLocalName(led), str(state)]))


def peripheral(path):
    """Resolve a monitor path such as 'sysbus.i2c1.si7021'.

    The machine is indexed with the whole dotted path in one go. Walking it
    attribute by attribute does not work: the intermediate objects are not
    addressable that way, and every lookup silently returns nothing.
    """
    try:
        return machine[path]
    except Exception:
        return None


def read_sensor(path, prop):
    try:
        with machine_lock:
            obj = peripheral(path)
            if obj is None:
                return None
            return getattr(obj, prop, None)
    except Exception:
        return None


def all_sensors():
    """Every reading worth polling, which means the sensors a learner added.

    The board has none of its own. Recomputed each pass rather than captured
    once, so a sensor added mid session starts reporting without a restart.
    """
    out = []
    for name, part in ADDED_PARTS.items():
        for prop in part.get("values", []):
            out.append(("sysbus.i2c1." + name, prop))
    return out


def poll_sensors():
    """Report sensor readings while anything is connected.

    Polled rather than evented because Renode's sensor models raise no event
    when a value is set from the monitor, which is exactly how an instructor
    changes one during a session.
    """
    import time
    last = {}
    while polling[0]:
        try:
            for path, prop in all_sensors():
                value = read_sensor(path, prop)
                if value is None:
                    continue
                key = path + "." + prop
                if last.get(key) != value:
                    last[key] = value
                    send_message("|".join(["SENSOR", key, str(value)]))
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def report_buttons():
    try:
        with machine_lock:
            for button in machine.GetPeripheralsOfType[Button]():
                send_message("|".join(["BUTTON", machine.GetLocalName(button),
                                       str(button.Pressed)]))
    except Exception:
        pass


def drive_button(action, target):
    """Press or release a button because somebody clicked it on the page."""
    try:
        with machine_lock:
            for button in machine.GetPeripheralsOfType[Button]():
                if machine.GetLocalName(button) != target:
                    continue
                if action == "press":
                    button.Press()
                elif action == "release":
                    button.Release()
                send_message("|".join(["BUTTON", target, str(button.Pressed)]))
                return
    except Exception as e:
        print "Could not drive button %s: %s" % (target, e)


def _apply_sensor(qualified, value):
    """Put a reading on the machine. Shared by the page and by the restore.

    One implementation rather than two: a rebuild restores readings, and a
    restore that drifted from what setting a reading does would be a bug
    nobody could see from either side.
    """
    path, prop = qualified.rsplit(".", 1)
    with machine_lock:
        obj = peripheral(path)
        if obj is None:
            return False
        setattr(obj, prop, float(value))
        return True


def set_sensor(qualified, value):
    """Set a sensor reading from the page.

    The value will not read back exactly -- see 'sensor-value-quantisation'.
    Remembered as the learner typed it, for exactly that reason: a rebuild
    resets the peripheral, and restoring a read-back value would move their
    number a little further every time.
    """
    try:
        if _apply_sensor(qualified, value):
            SET_BY_LEARNER[qualified] = value
    except Exception as e:
        print "Could not set %s: %s" % (qualified, e)


def restore_learner_values():
    """Put back every reading the learner set, after a reload cleared it.

    Never raises: it runs as the last step of a build, and a sensor that has
    gone away since -- a part removed, say -- must not cost the learner the
    build they asked for.
    """
    for qualified, value in list(SET_BY_LEARNER.items()):
        try:
            _apply_sensor(qualified, value)
        except Exception as e:
            print "Could not restore %s: %s" % (qualified, e)


def report_state(client):
    """Say what every LED, button and sensor is doing, right now.

    The page redraws the whole board whenever the pin map or the connectors
    arrive, and a freshly drawn lamp is dark. The page does keep its own record
    to paint back over that, but a lamp for a part it has never heard about --
    one added in a previous session, say -- has no record to restore. Asking
    costs one round trip and removes the whole class of problem.
    """
    try:
        with machine_lock:
            for led in machine.GetPeripheralsOfType[LED]():
                send_to(client, "|".join(["LED", machine.GetLocalName(led),
                                          str(led.State)]))
            for button in machine.GetPeripheralsOfType[Button]():
                send_to(client, "|".join(["BUTTON", machine.GetLocalName(button),
                                          str(button.Pressed)]))
    except Exception as e:
        print "Could not report board state: %s" % e

    for path, prop in all_sensors():
        value = read_sensor(path, prop)
        if value is not None:
            send_to(client, "|".join(["SENSOR", path + "." + prop, str(value)]))


def exercises_in(directory):
    """Every exercise a repository holds, in order.

    An exercise is a directory with a main.c in it. Read from disk every time
    rather than captured once, because a learner's clone may hold an exercise
    this file predates -- the same reason all_sensors() recomputes.
    """
    try:
        names = os.listdir(directory)
    except Exception:
        return []
    found = []
    for name in sorted(names):
        if os.path.isfile(os.path.join(directory, name, "main.c")):
            found.append(name)
    return found


def outcome_of(code):
    """What the course build's exit code means, as a token for the page.

    build.sh distinguishes three outcomes and says so in its own header: 0
    built, 1 the compiler ran and rejected the code, 2 the build could not be
    attempted at all. The third is the one that matters most and the easiest
    to lose -- a missing compiler once told every learner in a grading run
    that their code was broken, and hints were invented about it.

    Anything else is treated as the learner's code rather than as a course
    defect, deliberately: claiming "not your fault" wrongly is the more
    expensive mistake, because it sends somebody to ask for help about an
    error they could have read.
    """
    if code == 0:
        return "BUILT"
    if code == 2:
        return "COULD_NOT_BUILD"
    return "DID_NOT_COMPILE"


def _run_shell(script, *arguments):
    """Run a fixed shell script from the repository root. Returns (code, output).

    `script` is a literal in this file. Anything variable is passed as an
    argument and reaches the script as $1, $2 and so on, so no amount of
    quoting inside it can become shell syntax -- a directory named
    `foo'; rm -rf /; '` arrives as that name and nothing else. Interpolating
    into the command string would have worked for every real exercise name and
    been wrong in principle, and ADR-0043 makes it a rule rather than a
    precaution: this port is reachable from any browser tab a learner has open.

    The shell merges stderr into stdout, as check-my-work.yml already does.
    Two reasons: IronPython's subprocess refuses stderr=STDOUT outright, and
    reading two .NET streams one after the other deadlocks if the one not
    being read fills up. One merged stream has neither problem.

    WorkingDirectory is set because this module chdir'd into vis/ at import.
    """
    info = ProcessStartInfo()
    info.FileName = "/bin/sh"
    info.ArgumentList.Add("-c")
    info.ArgumentList.Add(script)
    info.ArgumentList.Add("sh")            # $0, so the rest begin at $1
    for argument in arguments:
        info.ArgumentList.Add(argument)
    info.WorkingDirectory = REPO_ROOT
    info.RedirectStandardOutput = True
    info.UseShellExecute = False
    process = Process.Start(info)
    output = process.StandardOutput.ReadToEnd()
    process.WaitForExit()
    return process.ExitCode, output


def run_course_build(exercise):
    """Run the course's own build for one exercise. Returns (code, output).

    The course's build, not a reproduction of it: grading runs this same
    script, so a learner's local outcome and their graded outcome cannot
    disagree about whether their code compiles. Its output also reaches the
    ledger and the assistant, which is why nothing here edits it.

    """
    return _run_shell('./tools/build.sh "$1" 2>&1', exercise)




def load_firmware(elf):
    """Put a built image on the board the way the simulator requires.

    Set $bin, make sure a reset macro loads it, then reset. `machine Reset`
    pauses the machine itself, runs the macro -- so the load is legal on a
    board that is running, which is how board.resc leaves it -- re-derives
    the vector table from the new image, and resumes.

    None of the obvious alternatives work, and tests/test_firmware_reload.py
    holds the measurements:

      - `sysbus LoadELF` on a running machine is refused outright, by
        printing rather than raising.
      - pause, load, reset, start HALTS the processor: the reset discards the
        symbol lookup the load just built, leaving no start address to derive.
        Memory survives a reset, so the board freezes showing what the old
        firmware last did -- loud in the log, silent on the board.

    The macro is redefined here even though board.resc already defines it,
    because `machine Reset` with no macro registered reports only a warning
    and leaves the board broken. Measured, not assumed.

    Returns True only if every command reported success. monitor.Parse returns
    a boolean and does so correctly for both failures above. The error buffer
    the Robot Framework keyword reads is not reachable from here: this
    interaction is a plain CommandInteraction with no GetError, so the text of
    a refusal goes to the simulator's console and the plugin reports its own
    sentence to the page.
    """
    path = elf.replace(chr(92), "/")
    with machine_lock:
        for command in ('$bin=@%s' % path,
                        'macro reset "sysbus LoadELF $bin"',
                        "machine Reset"):
            if not monitor.Parse(command):
                # Call syntax, not the statement form used elsewhere in this
                # file: tests/test_board_build.py lifts this function out by
                # source and runs it under Python 3, where a print statement
                # is a syntax error. `print(one_string)` means the same thing
                # in both.
                print("Firmware load failed at: %s" % command)
                return False
    return True


def say_build(exercise, token, text, client=None):
    """Say how a build went: to one page, or to all of them.

    Not through refuse(), which writes to the palette's status line -- the
    wrong card entirely for somebody who just pressed build.

    Who hears it is the distinction that matters, and it is not the one it
    first looks like:

      - An OUTCOME is broadcast. The board every page is watching has just
        changed, so every page needs to know, whichever one asked.
      - A REFUSAL goes only to the page that asked. It is about that request.
        Broadcasting it was measured, on 2026-11-11, with four pages pressing
        build together: every page reported a refusal, including the one whose
        build was running, because another page's refusal arrived first. The
        plugin was right and every page was wrong about it.

    `token` is what the page says; `text` is machine output to show verbatim,
    and is empty when there is none. Nothing a learner reads is composed here:
    this file has no Japanese in it, and the page is the only place that knows
    which language it is showing.

    The text is the last field because it is JSON and JSON can contain the
    separator, so a page joins everything after the third one back together
    before parsing it. The ADDED message already does this.
    """
    message = "|".join(["BUILD", exercise, token, dumps(text)])
    if client is None:
        send_message(message)
    else:
        send_to(client, message)


def repository_from_config(text):
    """'owner/repo' from a git config's origin, or None.

    Taken from the learner's own clone and never from a request: this is the
    edge ADR-0044's first condition is about. Three shapes reach here --
    https, https carrying a credential in the URL, and ssh -- and a wrong
    answer means the board fetches from a repository nobody asked about.

    Pure, so every shape is a test rather than a hope.
    """
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped.replace(" ", "").lower() == '[remote"origin"]'
            continue
        if not inside or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().lower() != "url":
            continue
        url = value.strip()
        if url.endswith(".git"):
            url = url[:-4]
        if "@" in url and "://" not in url:          # git@host:owner/repo
            url = url.split(":", 1)[-1]
        else:                                        # https://[cred@]host/...
            if "://" in url:
                url = url.split("://", 1)[1]
            if "@" in url:
                url = url.split("@", 1)[1]
            parts = url.split("/", 1)
            url = parts[1] if len(parts) > 1 else ""
        bits = [b for b in url.split("/") if b]
        if len(bits) >= 2:
            return "%s/%s" % (bits[-2], bits[-1])
    return None


def _read_text(path):
    """A file's text, or '' where there is none. Never raises."""
    try:
        handle = open(path)
        try:
            return handle.read()
        finally:
            handle.close()
    except Exception:
        return ""


def read_secret():
    """The learner's own credential, or None if the launcher left none.

    None is an ordinary outcome, not a fault: an SSH clone has no stored
    credential, and neither does a helper that keeps one somewhere of its
    own. Read on each use rather than held, so nothing keeps a copy.
    """
    try:
        handle = open(SECRET_FILE, "rb")
        try:
            token = handle.read().strip()
        finally:
            handle.close()
        return token or None
    except Exception:
        return None


def local_head():
    """The commit the learner's clone is on, short, or None."""
    try:
        head = open(os.path.join(REPO_ROOT, ".git", "HEAD")).read().strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            head = open(os.path.join(REPO_ROOT, ".git", ref)).read().strip()
        return head[:7] or None
    except Exception:
        return None


def firmware_from_upload(blob, exercise):
    """The firmware inside whatever a page handed over, or why there is none.

    Returns (image, None), or (None, token) saying what was wrong. Two shapes
    arrive, because they are the two a learner can get from GitHub by hand:

      - a bare ELF, which is what a Release asset is;
      - a zip, which is what an Actions artifact is, always, holding every
        exercise that compiled on that run.

    The zip is unpacked here rather than by the learner. Asking them to unpack
    it would be one more step in the path that exists because the other one
    was unavailable.

    Which member: the one whose path names this exercise, or the only one
    there is. An archive holding several and naming none of them is refused
    rather than guessed at -- loading somebody else's exercise onto the board
    and saying nothing is the failure this whole area is shaped to avoid.

    Judged on the leading bytes, not the file name. A learner who renames
    something has not changed what it is, and the simulator's complaint about
    a file that is not an ELF tells them nothing they can act on.

    Deliberately free of the simulator and of state, so the tests can put
    every shape through it without a board.
    """
    if blob[:4] == ELF_MAGIC:
        return blob, None

    if blob[:4] != ZIP_MAGIC:
        return None, "REFUSED_NOT_FIRMWARE"

    try:
        archive = zipfile.ZipFile(StringIO.StringIO(blob), "r")
        try:
            names = [n for n in archive.namelist()
                     if n.lower().endswith(".elf")]
            naming_it = [n for n in names if exercise in n]
            if len(naming_it) == 1:
                chosen = naming_it[0]
            elif len(names) == 1:
                chosen = names[0]
            else:
                return None, "REFUSED_NOTHING_INSIDE"
            image = archive.read(chosen)
        finally:
            archive.close()
    except Exception:
        return None, "REFUSED_NOT_FIRMWARE"

    if image[:4] != ELF_MAGIC:
        return None, "REFUSED_NOT_FIRMWARE"
    return image, None


class _NoRedirect(urllib2.HTTPRedirectHandler):
    """Refuse to follow a redirect, so the request can be inspected instead.

    This exists for one measured reason. Asking the API for an artifact's zip
    answers 302 to
    `productionresultssa31.blob.core.windows.net` -- Azure's storage, not even
    a GitHub host. urllib2 follows redirects by default and carries the
    headers across, so the default behaviour would send the learner's
    credential to a third party's host. Measured 2026-11-11.

    So nothing is followed. The location is read, and the bytes are fetched
    from it with no credential attached at all -- which works, because that
    URL is signed. The token therefore only ever reaches api.github.com,
    which is what ADR-0044 requires.
    """

    def redirect_request(self, *args):
        return None


def _api_get(path, secret):
    """A JSON GET against the API host. The only host a token is sent to."""
    request = urllib2.Request(API + path)
    request.add_header("Authorization", "Bearer " + secret)
    request.add_header("User-Agent", "nucleo-f401re-board-view")
    request.add_header("Accept", "application/vnd.github+json")
    answer = urllib2.urlopen(request, timeout=30)
    try:
        return json.loads(answer.read())
    finally:
        answer.close()


def _artifact_bytes(repository, artifact_id, secret, attempts=2):
    """An artifact's zip, fetched up to `attempts` times.

    Tried twice because once was measured to be too few. On 2026-11-12 a
    fetch failed with `Index was outside the bounds of the array.` -- a
    .NET exception from a read that did not finish -- and the very same
    press succeeded immediately afterwards. One retry turns a refusal the
    learner has to understand into a pause they do not notice.

    Everything is retried, including an HTTP error. That is deliberately
    blunt: a second request costs a fraction of a second and the walk
    below already tolerates several, whereas deciding which .NET
    exceptions deserve another go is a judgement this cannot make
    correctly from inside IronPython -- the one that was measured arrived
    as a bare Exception with no status attached to inspect. A genuinely
    deterministic failure simply fails twice and reports the same thing.

    This matters more than it did. The caller may now walk back through
    several runs, so there are more reads to be unlucky on.
    """
    last = None
    for attempt in range(attempts):
        try:
            return _artifact_bytes_once(repository, artifact_id, secret)
        except Exception as why:            # noqa: BLE001 -- see above
            last = why
            if attempt + 1 < attempts:
                print("Fetching the build failed (%s); trying once more"
                      % why)
    raise last


def _artifact_bytes_once(repository, artifact_id, secret):
    """An artifact's zip, with the credential kept on the API host."""
    opener = urllib2.build_opener(_NoRedirect)
    request = urllib2.Request(
        "%s/repos/%s/actions/artifacts/%s/zip" % (API, repository, artifact_id))
    request.add_header("Authorization", "Bearer " + secret)
    request.add_header("User-Agent", "nucleo-f401re-board-view")
    signed = None
    try:
        answer = opener.open(request, timeout=30)
        try:
            return answer.read()        # answered directly; nothing to follow
        finally:
            answer.close()
    except urllib2.HTTPError as why:
        if why.code in (301, 302, 303, 307, 308):
            signed = why.headers.get("location")
        else:
            raise
    if not signed:
        raise IOError("no location to fetch the artifact from")

    plain = urllib2.Request(signed)     # no Authorization header, on purpose
    plain.add_header("User-Agent", "nucleo-f401re-board-view")
    answer = urllib2.urlopen(plain, timeout=120)
    try:
        return answer.read()
    finally:
        answer.close()


def newest_build_of(exercise, runs, artifacts_of, firmware_of):
    """The newest run still holding a build OF THIS EXERCISE, as
    (run, artifact, image).

    Newest rather than the one matching the learner's HEAD: CI builds what was
    pushed and a working tree is almost always ahead, so insisting on an exact
    match would refuse nearly every time -- and a control that usually says no
    is not pressed twice. Which commit it was is reported instead.

    An expired artifact is passed over rather than treated as an error: seven
    days is short enough that a learner returning after a fortnight meets this
    in the ordinary way.

    OF THIS EXERCISE is the part that was missing until 2026-11-12. A run
    builds every exercise and keeps whatever compiled, so a run in which ONE
    exercise fails still produces an artifact -- holding the others. Taking
    the newest run with ANY artifact and then demanding this exercise be
    inside it refused the learner whose exercise had just broken, which is
    exactly the learner this control exists for, while an unexpired build of
    their exercise sat in the run before.

    That was not a decision; it was a case nobody enumerated. The design had
    already rejected refusing -- "never wrong and frequently useless... a
    feature that usually says no is not pressed twice" -- and the same
    reasoning covers this. Found on a learner's repository by pressing the
    button in an order no walkthrough had scripted.

    `artifacts_of` and `firmware_of` are passed in so this can be driven
    without a network. `firmware_of` returns the image or None and is called
    only on artifacts that have not expired. The search stops at the first
    artifact holding the exercise, so the ordinary case -- the newest run has
    it -- costs exactly one download, as it did before. Only a learner whose
    exercise failed to compile pays for another, bounded by the window the
    caller asks for.
    """
    live = False          # a build that is still kept, just not of this
    ever = False          # a build that existed once, expired or not

    for run in runs:
        for artifact in artifacts_of(run):
            ever = True
            if artifact.get("expired"):
                continue
            image = firmware_of(artifact)
            if image is not None:
                return run, artifact, image, None
            live = True

    # Why there is nothing, because the three reasons want different
    # advice and until 2026-11-12 all three got "push again to make a
    # fresh one" -- true for the expired case, useless to somebody whose
    # code has never compiled, and odd for somebody who has never pushed.
    #
    # Each is read off what the listing already showed, so none of this
    # costs a request:
    #
    #   no runs                     -> they have not pushed
    #   a kept build, without this  -> this exercise has not compiled
    #   only expired builds         -> it compiled once and has been cleared
    #   no artifact on any run      -> nothing has ever compiled
    if not runs:
        return None, None, None, "REFUSED_NO_PUSH"
    if live or not ever:
        return None, None, None, "REFUSED_NEVER_BUILT"
    return None, None, None, "REFUSED_NO_RUN"


def fetch_ci_build(exercise, client=None):
    """Put the build GitHub made onto the board."""
    if exercise not in exercises_in(EXERCISES_DIR):
        return say_build(exercise, "REFUSED_UNKNOWN", "", client)

    secret = read_secret()
    if secret is None:
        return say_build(exercise, "REFUSED_NO_CREDENTIAL", "", client)

    repository = repository_from_config(
        _read_text(os.path.join(REPO_ROOT, ".git", "config")))
    if not repository:
        return say_build(exercise, "REFUSED_FETCH_FAILED",
                         "This does not look like a clone of a repository.",
                         client)

    build_lock.acquire()
    try:
        if building[0]:
            return say_build(exercise, "REFUSED_BUSY", "", client)
        building[0] = True
    finally:
        build_lock.release()

    try:
        send_message("|".join(["FETCHING", exercise, ""]))
        try:
            listed = _api_get(
                "/repos/%s/actions/workflows/%s/runs?per_page=10"
                % (repository, LEARNER_WORKFLOW), secret)

            def artifacts_of(run):
                found = _api_get("/repos/%s/actions/runs/%s/artifacts"
                                 % (repository, run["id"]), secret)
                return found.get("artifacts", [])

            def firmware_of(artifact):
                blob = _artifact_bytes(repository, artifact["id"], secret)
                image, _refusal = firmware_from_upload(blob, exercise)
                return image

            run, artifact, image, why = newest_build_of(
                exercise, listed.get("workflow_runs", []),
                artifacts_of, firmware_of)

            # `why` says which of the three it is, and each wants
            # different advice -- see newest_build_of.
            # REFUSED_NOTHING_INSIDE is not among them and is no longer
            # reachable from here; it stays for the drop target, where it
            # is literally about a zip the learner handed over.
            if run is None:
                return say_build(exercise, why, "", client)
        except Exception as e:
            print("Could not fetch the build: %s" % e)
            return say_build(exercise, "REFUSED_FETCH_FAILED",
                             str(e)[:200], client)

        path = os.path.join(tempfile.gettempdir(),
                            "f401re_fetched_%s.elf" % exercise)
        handle = open(path, "wb")
        try:
            handle.write(image)
        finally:
            handle.close()

        if not load_firmware(path):
            return say_build(exercise, "COULD_NOT_BUILD",
                             "The build was fetched but the simulator would "
                             "not load it. See the console.")
        restore_learner_values()
        report_buttons()

        # Said separately from the outcome, because it is about which binary
        # is on the board rather than about whether the press worked, and a
        # learner needs it even when everything went right.
        head = local_head()
        send_message("|".join([
            "BUILT_FROM", exercise,
            dumps({"commit": (run.get("head_sha") or "")[:7],
                   "head": head or "",
                   "matches": bool(head) and
                              (run.get("head_sha") or "").startswith(head)})]))
        say_build(exercise, "LOADED", "")
    finally:
        build_lock.acquire()
        try:
            building[0] = False
        finally:
            build_lock.release()


def load_uploaded(exercise, blob, client=None):
    """Put firmware a page handed over onto the board.

    The same lock, the same load, and the same restoring of the learner's
    readings as a build -- because the spec's rule is about any firmware
    load, and because a second, lesser path that nobody exercises is how a
    fallback stops working without anybody noticing.
    """
    if exercise not in exercises_in(EXERCISES_DIR):
        return say_build(exercise, "REFUSED_UNKNOWN", "", client)

    build_lock.acquire()
    try:
        if building[0]:
            return say_build(exercise, "REFUSED_BUSY", "", client)
        building[0] = True
    finally:
        build_lock.release()

    try:
        image, refusal = firmware_from_upload(blob, exercise)
        if refusal is not None:
            return say_build(exercise, refusal, "", client)

        path = os.path.join(tempfile.gettempdir(),
                            "f401re_upload_%s.elf" % exercise)
        handle = open(path, "wb")
        try:
            handle.write(image)
        finally:
            handle.close()

        if not load_firmware(path):
            return say_build(exercise, "COULD_NOT_BUILD",
                             "The firmware was handed over but the simulator "
                             "would not load it. See the console.")
        restore_learner_values()
        report_buttons()
        say_build(exercise, "LOADED", "")
    finally:
        build_lock.acquire()
        try:
            building[0] = False
        finally:
            build_lock.release()


def report_environment():
    """Tell every page what the environment check said.

    Reads what tools/container-start.sh left behind rather than running
    anything. The check has to run BEFORE the simulator, because it is what
    builds verify/verify.elf and board.resc loads that file -- so running it
    from here, after the board, would be too late to be the thing that made
    the board possible. That script carries the measurement.

    Reported by the course because the learner cannot report it to
    themselves: once the container starts the simulator there is no prompt to
    type the check at, and the container is the maintained standard route
    rather than a fallback (ADR-0016). A check nobody can run is a diagnosis
    nobody can get.

    It reports and never withholds. The board has already started by the time
    a page reads this, deliberately: declining to start on a failed check is
    nearer repairing than reporting (ADR-0021), and a check wrong about its
    own environment would otherwise withhold a board that works.

    Nothing to report means nothing is said and the card stays hidden. That is
    the native route, where a learner runs the check themselves.

    Never raises: it must not be the reason a board never appears.
    """
    path = os.environ.get("COURSE_ENVIRONMENT_REPORT")
    if not path:
        return
    try:
        handle = open(path)
        try:
            output = handle.read()
        finally:
            handle.close()
        status = os.environ.get("COURSE_ENVIRONMENT_STATUS") or "0"
        token = "READY" if status.strip() == "0" else "INCOMPLETE"
    except Exception as e:
        token = "UNCHECKED"
        output = "The environment check's report could not be read: %s" % e
    ENVIRONMENT[0] = (token, output)
    send_message("|".join(["ENVIRONMENT", token, dumps(output)]))


def build_exercise(client, exercise):
    """Build one exercise and run it, because somebody asked from the page.

    `client` is who asked. Refusals go back to them alone; outcomes go to
    everybody, because the board they are all watching has changed.
    """
    if exercise not in exercises_in(EXERCISES_DIR):
        return say_build(exercise, "REFUSED_UNKNOWN", "", client)

    # Claimed under the lock so two requests cannot both see it free. The
    # refusal is here rather than in the page because the page cannot speak
    # for tabs it does not know about.
    build_lock.acquire()
    try:
        if building[0]:
            return say_build(exercise, "REFUSED_BUSY", "", client)
        building[0] = True
    finally:
        build_lock.release()

    try:
        send_message("|".join(["BUILDING", exercise, ""]))
        try:
            code, output = run_course_build(os.path.join("exercises", exercise))
        except Exception as e:
            # Call syntax; see the note in load_firmware.
            print("Could not run the build: %s" % e)
            return say_build(exercise, "COULD_NOT_BUILD",
                             "The build could not be started: %s"
                             % str(e)[:160])

        token = outcome_of(code)
        if token == "BUILT":
            elf = os.path.join(EXERCISES_DIR, exercise, "firmware.elf")
            if not os.path.isfile(elf):
                token = "COULD_NOT_BUILD"
                output = (output + "\nThe build reported success but wrote no "
                                   "firmware.elf.")
            elif not load_firmware(elf):
                token = "COULD_NOT_BUILD"
                output = (output + "\nThe firmware was built but the simulator "
                                   "would not load it. See the console.")
            else:
                restore_learner_values()
                report_buttons()

        say_build(exercise, token, output)
    finally:
        build_lock.acquire()
        try:
            building[0] = False
        finally:
            build_lock.release()


def message_received(client, server, message):
    try:
        parts = message.split("|")
        verb = parts[0]
        if verb in ("press", "release"):
            drive_button(verb, parts[1])
        elif verb == "sensor":
            set_sensor(parts[1], parts[2])
        elif verb == "buttons":
            report_buttons()
        elif verb == "refresh":
            report_state(client)
        elif verb == "add":
            add_part(client, parts[1], parts[2])
        elif verb == "remove":
            remove_part(client, parts[1])
        elif verb == "exercises":
            send_to(client, "|".join(["EXERCISES",
                                      dumps(exercises_in(EXERCISES_DIR)), ""]))
        elif verb == "build":
            # Only a name, and only one the repository has. No path, no
            # flags, no command text: this port is reachable by any tab the
            # learner has open, so what it accepts is the security boundary
            # rather than a matter of taste (ADR-0043).
            build_exercise(client, parts[1])
        elif verb == "fetch":
            # Also only a name. The repository comes from the learner's own
            # clone and the host is fixed in this file, so there is nothing
            # here for a page to point somewhere else (ADR-0044).
            fetch_ci_build(parts[1], client)
    except Exception as e:
        print "Bad message from page (%r): %s" % (message, e)


def new_client(client, server):
    """Tell a page everything it needs before it draws anything.

    A page that has just connected knows nothing. Without this it learns an
    LED's state only when the state next changes, so a steadily lit LED is drawn
    dark, possibly for a long time.

    Never allowed to raise: this runs on the connection's own handler thread, so
    an exception here ends the thread and drops the connection.
    """
    try:
        send_to(client, "|".join(["VERSION", PLUGIN_FINGERPRINT, ""]))
    except Exception:
        pass

    try:
        send_to(client, "CATALOGUE|" + dumps(CATALOGUE) + "|")
        send_to(client, "PINS|" + dumps(pin_map()) + "|")
        send_to(client, "CONNECTORS|" + dumps(CONNECTORS) + "|")
        send_to(client, "ONBOARD|" + dumps(board_hardware()) + "|")
        send_to(client, "DIVERGENCES|" + dumps(DIVERGENCES) + "|")
        send_to(client, "EXERCISES|" + dumps(exercises_in(EXERCISES_DIR)) + "|")
        # Whether fetching is available at all. Said as the page connects, so
        # a control that cannot work is never offered as though it could --
        # and said with its reason, because a learner cannot ask about
        # something that is merely greyed out.
        send_to(client, "|".join(["CAN_FETCH",
                                  "yes" if read_secret() else "no", ""]))
        if ENVIRONMENT[0] is not None:
            token, output = ENVIRONMENT[0]
            send_to(client, "|".join(["ENVIRONMENT", token, dumps(output)]))
        for name, part in ADDED_PARTS.items():
            send_to(client, "|".join(["ADDED", name, dumps(part)]))
    except Exception as e:
        print "Could not send the board layout: %s" % e

    try:
        with machine_lock:
            for led in machine.GetPeripheralsOfType[LED]():
                send_to(client, "|".join(["LED", machine.GetLocalName(led),
                                          str(led.State)]))
            for button in machine.GetPeripheralsOfType[Button]():
                try:
                    send_to(client, "|".join(["BUTTON",
                                              machine.GetLocalName(button),
                                              str(button.Pressed)]))
                except Exception:
                    pass
    except Exception as e:
        print "Could not greet a new page fully: %s" % e

    for path, prop in all_sensors():
        value = read_sensor(path, prop)
        if value is not None:
            send_to(client, "|".join(["SENSOR", path + "." + prop, str(value)]))

    # Grouped rather than one message per character: a minute of output is
    # thousands of characters and a page does not need them individually.
    if UART_HISTORY:
        grouped = []
        for name, text in UART_HISTORY:
            if grouped and grouped[-1][0] == name:
                grouped[-1][1].append(text)
            else:
                grouped.append((name, [text]))
        for name, chunks in grouped:
            send_to(client, "|".join(["UART", name, "".join(chunks)]))

    send_to(client, "READY||")


def _start_visualization(data_port):
    global websocket_server, websocket_thread, machine, DATA_PORT

    emulation = Antmicro.Renode.Core.EmulationManager.Instance.CurrentEmulation
    machine = emulation.Machines[0]

    # Whatever board.repl already declared is in the machine now, so claim it
    # before the page is served and before anything can be added on top of it.
    adopt_added_parts()

    for led in machine.GetPeripheralsOfType[LED]():
        led.StateChanged += blink_led
        print "Hooked LED:", machine.GetLocalName(led)

    for button in machine.GetPeripheralsOfType[Button]():
        print "Found button:", machine.GetLocalName(button)

    for uart in machine.GetPeripheralsOfType[IUART]():
        name_ref = clr.Reference[str]()
        if machine.TryGetAnyName(uart, name_ref):
            uart_name = str(name_ref.Value)
        else:
            uart_name = "unknown_uart"
        # Bound as a default argument: a bare closure over the loop variable
        # would make every UART report under whichever name the loop ended on.
        on_received = lambda char, _n=uart_name: send_uart_chars(char, _n)
        uart.CharReceived += on_received
        uart_event_map[uart] = on_received
        print "Hooked UART:", uart_name

    DATA_PORT = data_port
    # All interfaces, not the bundled server's 127.0.0.1 default. The page is
    # served from one socket and its data from this one, and the HTTP side has
    # always bound every interface. Inside a container the mismatch meant the
    # drawing loaded over the mapped port and then stayed empty forever: the
    # browser's websocket reached the container's external interface, where
    # nothing was listening, while the data socket sat on loopback inside.
    #
    # This is the same exposure the page already has. A simulator on a
    # learner's own machine holds nothing secret, and the two sockets being
    # reachable from different places is a trap rather than a protection.
    websocket_server = WebsocketServer(data_port, host="0.0.0.0")
    websocket_server.set_fn_message_received(message_received)
    websocket_server.set_fn_new_client(new_client)
    websocket_thread = Thread(target=websocket_server.serve_forever)
    websocket_thread.deamon = True
    websocket_thread.start()

    sensor_thread = Thread(target=poll_sensors)
    sensor_thread.deamon = True
    sensor_thread.start()


def mc_serveVisualization(port, data_port=9001):
    """Serve the board on `port`, with live data on `data_port`.

    Both are arguments so that two instances on one machine do not collide.
    """
    global main_server, server_thread
    _start_visualization(data_port)

    try:
        # ThreadingTCPServer, not TCPServer: a single-threaded server queues a
        # browser's parallel requests and drops the larger ones, leaving the
        # page half drawn.
        main_server = SocketServer.ThreadingTCPServer(("", port), NoCacheHandler)
        main_server.daemon_threads = True
        server_thread = Thread(target=main_server.serve_forever)
        server_thread.deamon = True
        print "Board at http://localhost:%d  (live data on port %d)" % (port, data_port)
        server_thread.start()

        # Reading a file, so no thread: the check itself already ran, before
        # the simulator did.
        report_environment()
    except:
        import traceback
        traceback.print_exc()


def mc_serveVisualizationData(data_port):
    """Serve only the live data, for a page served from somewhere else."""
    _start_visualization(data_port)
    print "Serving board data only, on port", data_port


print "Adding serveVisualization command."
