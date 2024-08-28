# Channel access server used to generate fake PV signals analogous to accelerator components.
# The main body of the script instantiates PVs from a file passed by command line argument.
import json
import math
import os
import sys
import time
import argparse
from pathlib import Path
from importlib.metadata import version

from orbit.lattice import AccNode
from orbit.py_linac.lattice import LinacPhaseApertureNode, MarkerLinacNode
from orbit.py_linac.lattice_modifications import Add_quad_apertures_to_lattice, Add_rfgap_apertures_to_lattice

from virtaccl.PyORBIT_Model.pyorbit_child_nodes import BPMclass, WSclass, DumpBunchClass
# from orbit.py_linac.linac_parsers import SNS_LinacLatticeFactory
from virtaccl.PyORBIT_Model.pyorbit_lattice_factory import PyORBIT_Lattice_Factory

from orbit.core.bunch import Bunch
from orbit.core.linac import BaseRfGap, RfGapTTF, RfGapTTF_slow

from virtaccl.ca_server import Server, epics_now, not_ctrlc
from virtaccl.PyORBIT_Model.virtual_devices import Cavity, BPM, Quadrupole, Corrector, P_BPM, \
    WireScanner, Quadrupole_Power_Supply, Corrector_Power_Supply, Bend_Power_Supply, Bend, Quadrupole_Power_Shunt
from virtaccl.PyORBIT_Model.SNS.virtual_devices_SNS import SNS_Dummy_BCM, SNS_Cavity, SNS_Dummy_ICS, SNS_Bunch_Dumper

from virtaccl.PyORBIT_Model.pyorbit_lattice_controller import OrbitModel


def load_config(filename: Path):
    with open(filename, "r") as json_file:
        devices_dict = json.load(json_file)


def main():
    loc = Path(__file__).parent
    va_version = version('virtaccl')
    parser = argparse.ArgumentParser(
        description='Run the SNS PyORBIT virtual accelerator server. Version ' + va_version)
    # parser.add_argument('--prefix', '-p', default='test', type=str, help='Prefix for PVs')

    # Json file that contains a dictionary connecting EPICS name of devices with their associated element model names.
    parser.add_argument('--file', '-f', default=loc / 'va_config.json', type=str,
                        help='Pathname of config json file.')

    # Number (in Hz) determining the update rate for the virtual accelerator.
    parser.add_argument('--refresh_rate', default=1.0, type=float,
                        help='Rate (in Hz) at which the virtual accelerator updates (default=1.0).')

    # Lattice xml input file and the sequences desired from that file.
    parser.add_argument('--lattice', default=loc / 'PyORBIT_Model/SNS/sns_linac.xml', type=str,
                        help='Pathname of lattice file')
    parser.add_argument("--start", default="MEBT", type=str,
                        help='Desired sequence of the lattice to start the model with (default=MEBT).')
    parser.add_argument("end", nargs='?', default="HEBT1", type=str,
                        help='Desired sequence of the lattice to end the model with (default=HEBT1).')

    # Desired initial bunch file and the desired number of particles from that file.
    parser.add_argument('--bunch', default=loc / 'PyORBIT_Model/SNS/MEBT_in.dat', type=str,
                        help='Pathname of input bunch file.')
    parser.add_argument('--particle_number', default=1000, type=int,
                        help='Number of particles to use (default=1000).')
    parser.add_argument('--beam_current', default=38.0, type=float,
                        help='Initial beam current in mA. (default=38.0).')
    parser.add_argument('--save_bunch', const='end_bunch.dat', nargs='?', type=str,
                        help="Saves the bunch at the end of the lattice after each track in the given location. "
                             "If no location is given, the bunch is saved as 'end_bunch.dat' in the working directory. "
                             "(Default is that the bunch is not saved.)")

    # Json file that contains a dictionary connecting EPICS name of devices with their phase offset.
    parser.add_argument('--phase_offset', default=None, type=str,
                        help='Pathname of phase offset file.')

    # Desired amount of output.
    parser.add_argument('--debug', dest='debug', action='store_true',
                        help="Some debug info will be printed.")
    parser.add_argument('--production', dest='debug', action='store_false',
                        help="DEFAULT: No additional info printed.")
    parser.add_argument('--print_settings', dest='print_settings', action='store_true',
                        help="Will only print setting PVs. Will NOT run the virtual accelerator. (Default is off)")
    parser.add_argument('--print_pvs', dest='print_pvs', action='store_true',
                        help="Will print all PVs. Will NOT run the virtual accelerator. (Default is off)")

    # Number (in seconds) that determine some delay parameter in the server. Not exactly sure how it works, so use at
    # your own risk.
    parser.add_argument('--ca_proc', default=0.1, type=float,
                        help='Number (in seconds) that determine some delay parameter in the server. Not exactly sure '
                             'how it works, so use at your own risk. (Default=0.1)')

    os.environ['EPICS_CA_MAX_ARRAY_BYTES'] = '10000000'

    args = parser.parse_args()
    debug = args.debug
    save_bunch = args.save_bunch

    config_file = Path(args.file)
    with open(config_file, "r") as json_file:
        devices_dict = json.load(json_file)

    update_period = 1 / args.refresh_rate

    lattice_file = args.lattice
    start_sequence = args.start
    end_sequence = args.end

    lattice_factory = PyORBIT_Lattice_Factory()
    lattice_factory.setMaxDriftLength(0.01)
    model_lattice = lattice_factory.getLinacAccLattice_test(lattice_file, end_sequence, start_sequence)
    cppGapModel = BaseRfGap
    # cppGapModel = RfGapTTF
    # cppGapModel = RfGapTTF_slow
    rf_gaps = model_lattice.getRF_Gaps()
    for rf_gap in rf_gaps:
        rf_gap.setCppGapModel(cppGapModel())
        phaseAperture = LinacPhaseApertureNode(rf_gap.getRF_Cavity().getFrequency(), rf_gap.getName() + ":phaseAprt")
        phaseAperture.setPosition(rf_gap.getPosition())
        phaseAperture.setMinMaxPhase(-180.0 * 2, +180.0 * 2)
        rf_gap.addChildNode(phaseAperture, AccNode.EXIT)
    Add_quad_apertures_to_lattice(model_lattice)
    Add_rfgap_apertures_to_lattice(model_lattice)

    bunch_file = Path(args.bunch)
    part_num = args.particle_number

    bunch_in = Bunch()
    bunch_in.readBunch(str(bunch_file))
    bunch_orig_num = bunch_in.getSizeGlobal()
    if bunch_orig_num < part_num:
        print('Bunch file contains less particles than the desired number of particles.')
    elif part_num <= 0:
        bunch_in.deleteAllParticles()
    else:
        bunch_macrosize = bunch_in.macroSize()
        bunch_macrosize *= bunch_orig_num / part_num
        bunch_in.macroSize(bunch_macrosize)
        for n in range(bunch_orig_num):
            if n + 1 > part_num:
                bunch_in.deleteParticleFast(n)
        bunch_in.compress()
    beam_current = args.beam_current / 1000  # Set the initial beam current in Amps.

    model = OrbitModel(debug=debug, save_bunch=save_bunch)
    model.define_custom_node(BPMclass.node_type, BPMclass.parameter_list, diagnostic=True)
    model.define_custom_node(WSclass.node_type, WSclass.parameter_list, diagnostic=True)
    model.initialize_lattice(model_lattice)
    model.set_initial_bunch(bunch_in, beam_current)
    element_list = model.get_element_list()

    delay = args.ca_proc
    server = Server(process_delay=delay)

    offset_file = args.phase_offset
    if offset_file is not None:
        with open(offset_file, "r") as json_file:
            offset_dict = json.load(json_file)

    cavities = devices_dict["RF_Cavity"]
    for name, device_dict in cavities.items():
        ele_name = device_dict["PyORBIT_Name"]
        if ele_name in element_list:
            amplitude = device_dict["Design_Amplitude"]
            initial_settings = model.get_element_parameters(ele_name)
            initial_settings['amp'] = 1
            phase_offset = 0
            if offset_file is not None:
                phase_offset = offset_dict[name]
            rf_device = SNS_Cavity(name, ele_name, initial_dict=initial_settings, phase_offset=phase_offset,
                                   design_amp=amplitude)
            server.add_device(rf_device)

    quad_ps_names = devices_dict["Quadrupole_Power_Supply"]
    ps_quads = {}
    for name in quad_ps_names:
        ps_quads[name] = {"quads": {}, "min_field": math.inf}

    quads = devices_dict["Quadrupole"]
    for name, device_dict in quads.items():
        ele_name = device_dict["PyORBIT_Name"]
        polarity = device_dict["Polarity"]
        if ele_name in element_list:
            initial_field_str = abs(model.get_element_parameters(ele_name)['dB/dr'])
            if "Power_Supply" in device_dict and device_dict["Power_Supply"] in quad_ps_names:
                ps_name = device_dict["Power_Supply"]
                if "Power_Shunt" in device_dict and device_dict["Power_Shunt"] in devices_dict[
                    "Quadrupole_Power_Shunt"]:
                    shunt_name = device_dict["Power_Shunt"]
                    ps_quads[ps_name]["quads"] |= \
                        {name: {'or_name': ele_name, 'shunt': shunt_name, 'dB/dr': initial_field_str,
                                'polarity': polarity}}
                    if ps_quads[ps_name]["min_field"] > initial_field_str:
                        ps_quads[ps_name]["min_field"] = initial_field_str
                else:
                    ps_quads[ps_name]["quads"] |= \
                        {name: {'or_name': ele_name, 'shunt': 'none', 'dB/dr': initial_field_str,
                                'polarity': polarity}}
                    if ps_quads[ps_name]["min_field"] > initial_field_str:
                        ps_quads[ps_name]["min_field"] = initial_field_str

    for ps_name, ps_dict in ps_quads.items():
        if ps_dict["quads"]:
            ps_field = ps_dict["min_field"]
            ps_device = Quadrupole_Power_Supply(ps_name, ps_field)
            server.add_device(ps_device)
            for quad_name, quad_model in ps_dict["quads"].items():
                if quad_model['shunt'] == 'none':
                    quad_device = Quadrupole(quad_name, quad_model['or_name'], power_supply=ps_device,
                                             polarity=quad_model['polarity'])
                else:
                    shunt_name = quad_model['shunt']
                    field = quad_model['dB/dr']
                    shunt_field = field - ps_field
                    shunt_device = Quadrupole_Power_Shunt(shunt_name, shunt_field)
                    server.add_device(shunt_device)
                    quad_device = Quadrupole(quad_name, quad_model['or_name'], power_supply=ps_device,
                                             power_shunt=shunt_device, polarity=quad_model['polarity'])
                server.add_device(quad_device)

    correctors = devices_dict["Corrector"]
    for name, device_dict in correctors.items():
        ele_name = device_dict["PyORBIT_Name"]
        polarity = device_dict["Polarity"]
        if ele_name in element_list:
            initial_field = model.get_element_parameters(ele_name)['B']
            if "Power_Supply" in device_dict and device_dict["Power_Supply"] in devices_dict["Corrector_Power_Supply"]:
                ps_name = device_dict["Power_Supply"]
                ps_device = Corrector_Power_Supply(ps_name, initial_field)
                server.add_device(ps_device)
                corrector_device = Corrector(name, ele_name, power_supply=ps_device, polarity=polarity)
                server.add_device(corrector_device)

    bends = devices_dict["Bend"]
    for name, device_dict in bends.items():
        ele_name = device_dict["PyORBIT_Name"]
        if ele_name in element_list:
            initial_field = 0
            if "Power_Supply" in device_dict and device_dict["Power_Supply"] in devices_dict["Bend_Power_Supply"]:
                ps_name = device_dict["Power_Supply"]
                ps_device = Bend_Power_Supply(ps_name, initial_field)
                server.add_device(ps_device)
                bend_device = Bend(name, ele_name, power_supply=ps_device)
                server.add_device(bend_device)

    wire_scanners = devices_dict["Wire_Scanner"]
    for name, model_name in wire_scanners.items():
        if model_name in element_list:
            ws_device = WireScanner(name, model_name)
            server.add_device(ws_device)

    bpms = devices_dict["BPM"]
    for name, device_dict in bpms.items():
        ele_name = device_dict["PyORBIT_Name"]
        if ele_name in element_list:
            phase_offset = 0
            if offset_file is not None:
                phase_offset = offset_dict[name]
            bpm_device = BPM(name, ele_name, phase_offset=phase_offset)
            server.add_device(bpm_device)

    pbpms = devices_dict["Physics_BPM"]
    for name, model_name in pbpms.items():
        if model_name in element_list:
            pbpm_device = P_BPM(name, model_name)
            server.add_device(pbpm_device)

    dummy_device = SNS_Dummy_BCM("Ring_Diag:BCM_D09", 'HEBT_Diag:BPM11')
    server.add_device(dummy_device)
    dummy_device = SNS_Dummy_ICS("ICS_Tim")
    server.add_device(dummy_device)

    # Retrack the bunch to update all diagnostics
    model.force_track()

    if args.print_settings:
        for setting in server.get_setting_pvs():
            print(setting)
        sys.exit()
    elif args.print_pvs:
        for pv in server.get_pvs():
            print(pv)
        sys.exit()

    if debug:
        print(server)
    server.start()
    print(f"Server started.")

    # Our new data acquisition routine
    while not_ctrlc():
        loop_start_time = time.time()

        now = epics_now()

        new_params = server.get_settings()
        server.update_readbacks()
        model.update_optics(new_params)
        model.track()
        new_measurements = model.get_measurements()
        server.update_measurements(new_measurements)

        server.update()

        loop_time_taken = time.time() - loop_start_time
        sleep_time = update_period - loop_time_taken
        if sleep_time < 0.0:
            print('Warning: Update took longer than refresh rate.')
        else:
            time.sleep(sleep_time)

    print('Exiting. Thank you for using our virtual accelerator!')


if __name__ == '__main__':
    main()
