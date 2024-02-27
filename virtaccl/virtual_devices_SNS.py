import time
import math
from random import randint, random
from typing import Dict, Any

import numpy as np
from virtaccl.virtual_devices import Cavity, Quadrupole, Quadrupole_Doublet, Quadrupole_Set, Corrector

from .ca_server import Device, AbsNoise, LinearT, PhaseT, not_ctrlc, PhaseTInv, LinearTInv


# Here are the device definitions that take the information from PyORBIT and translates/packages it into information for
# the server.
#
# All the devices need a name that will determine the name of the device in the EPICS server. If the corresponding
# element in PyORBIT has a different name, then it will need to be specified in the declaration as the model_name. If
# the device has settings (values changed by the user), they can be given initial values to match the model using
# initial_dict. These initial settings need to be in a dictionary using the appropriate keys defined by PyORBIT to
# differentiate different parameters. And finally, if the device has a phase, both setting and measurement, they can be
# given an offset using phase_offset.
#
# The strings denoted with a "_pv" are labels for EPICS. Changing these will alter the EPICS labels for values on the
# server. The strings denoted with a "_key" are the keys for parameters in PyORBIT for that device. These need to match
# the keys PyORBIT uses in the paramsDict for that devices corresponding PyORBIT element.


class SNS_Cavity(Cavity):
    def __init__(self, name: str, model_name: str = None, initial_dict: dict[str,] = None, phase_offset=0):
        if model_name is None:
            self.model_name = name
        else:
            self.model_name = model_name
        super().__init__(name, self.model_name, initial_dict, phase_offset)

        # Sets initial values for parameters.
        if initial_dict is not None:
            initial_phase = initial_dict[SNS_Cavity.phase_key]
            initial_amp = initial_dict[SNS_Cavity.amp_key]
        else:
            initial_phase = 0
            initial_amp = 1.0

        # Create old amp variable for ramping
        self.old_amp = initial_amp

        # Adds a phase offset. Default is 0 offset.
        offset_transform = PhaseTInv(offset=phase_offset, scaler=-180 / math.pi)
        initial_phase = offset_transform.raw(initial_phase)

        self.amp_transform = LinearTInv(scaler=SNS_Cavity.design_amp)
        initial_amp = self.amp_transform.raw(initial_amp)

        # Registers the device's PVs with the server
        self.register_setting(SNS_Cavity.phase_pv, default=initial_phase, transform=offset_transform)
        self.register_setting(SNS_Cavity.amp_pv, default=initial_amp, transform=self.amp_transform)
        self.register_setting(SNS_Cavity.amp_goal_pv, default=initial_amp, transform=self.amp_transform)
        self.register_setting(SNS_Cavity.blank_pv, default=0.0)


class SNS_Quadrupole(Quadrupole):
    def __init__(self, name: str, model_name: str = None, initial_dict: Dict[str, Any] = None):
        if model_name is None:
            self.model_name = name
        else:
            self.model_name = model_name
        super().__init__(name, self.model_name, initial_dict)

        readback_name = name.replace('PS_', '', 1)

        # Sets up initial values.
        if initial_dict is not None:
            initial_field = initial_dict[Quadrupole.field_key]
        else:
            initial_field = 0.0

        field_noise = AbsNoise(noise=1e-6)

        pol = 1
        if 'PS_QH' in name:
            pol = -1
        pol_transform = LinearTInv(scaler=pol)

        initial_field = pol_transform.raw(initial_field)

        # Registers the device's PVs with the server
        field_param = self.register_setting(Quadrupole.field_set_pv, default=initial_field, transform=pol_transform)
        self.register_readback(Quadrupole.field_readback_pv, field_param, noise=field_noise,
                               name_override=readback_name)


class SNS_Quadrupole_Doublet(Quadrupole_Doublet):
    def __init__(self, name: str, h_model_name: str, v_model_name: str, initial_dict: Dict[str, Any] = None):
        self.h_name = h_model_name
        self.v_name = v_model_name
        self.model_names = [h_model_name, v_model_name]
        super().__init__(name, h_model_name, v_model_name, initial_dict)

        readback_name = name.replace('PS_', '', 1)

        # Sets up initial values.
        if initial_dict is not None:
            initial_field = initial_dict[Quadrupole_Doublet.field_key]
        else:
            initial_field = 0.0

        field_noise = AbsNoise(noise=1e-6)

        pol = 1
        if 'SCL' in name:
            pol = -1
        pol_transform = LinearTInv(scaler=pol)

        initial_field = pol_transform.raw(initial_field)

        # Registers the device's PVs with the server
        field_param = self.register_setting(Quadrupole_Doublet.field_set_pv, default=initial_field,
                                            transform=pol_transform)
        self.register_readback(Quadrupole_Doublet.field_readback_pv, field_param, noise=field_noise,
                               name_override=readback_name)


class SNS_Quadrupole_Set(Quadrupole_Set):
    def __init__(self, name: str, model_names: list[str], initial_dict: Dict[str, Any] = None):
        self.model_names = model_names
        super().__init__(name, model_names, initial_dict)

        readback_name = name.replace('PS_', '', 1)

        # Sets up initial values.
        if initial_dict is not None:
            initial_field = initial_dict[Quadrupole.field_key]
        else:
            initial_field = 0.0

        field_noise = AbsNoise(noise=1e-6)

        pol = 1
        if 'SCL' in name:
            pol = -1
        pol_transform = LinearTInv(scaler=pol)

        initial_field = pol_transform.raw(initial_field)

        # Registers the device's PVs with the server
        field_param = self.register_setting(Quadrupole_Set.field_set_pv, default=initial_field, transform=pol_transform)
        self.register_readback(Quadrupole_Set.field_readback_pv, field_param, noise=field_noise,
                               name_override=readback_name)


class SNS_Corrector(Corrector):
    def __init__(self, name: str, model_name: str = None, initial_dict: Dict[str, Any] = None):
        if model_name is None:
            self.model_name = name
        else:
            self.model_name = model_name
        super().__init__(name, model_name, initial_dict)

        readback_name = name.replace('PS_', '', 1)

        # Sets initial values for parameters.
        if initial_dict is not None:
            initial_field = initial_dict[Corrector.field_key]
        else:
            initial_field = 0.0

        field_noise = AbsNoise(noise=1e-6)

        pol = 1
        if 'SCL' in name:
            pol = -1
        pol_transform = LinearTInv(scaler=pol)

        initial_field = pol_transform.raw(initial_field)

        # Registers the device's PVs with the server
        field_param = self.register_setting(Corrector.field_set_pv, default=initial_field, transform=pol_transform)
        self.register_readback(Corrector.field_readback_pv, field_param, noise=field_noise,
                               name_override=readback_name)
        self.register_setting(Corrector.field_high_limit_pv, default=Corrector.field_limits[1])
        self.register_setting(Corrector.field_low_limit_pv, default=Corrector.field_limits[0])


class SNS_Dummy_BCM(Device):
    # EPICS PV names
    freq_pv = 'FFT_peak2'

    # PyORBIT parameter keys
    beta_key = 'beta'  # [c]

    c_light = 2.99792458e+8  # [m/s]
    ring_length = 247.967  # [m]

    def __init__(self, name: str, model_name: str = None):
        if model_name is None:
            self.model_name = name
        else:
            self.model_name = model_name
        super().__init__(name, self.model_name)

        # Registers the device's PVs with the server.
        self.register_measurement(SNS_Dummy_BCM.freq_pv)

    # Updates the measurement values on the server. Needs the model key associated with it's value and the new value.
    # This is where the measurement PV name is associated with it's model key.
    def update_measurements(self, new_params: Dict[str, Dict[str, Any]] = None):
        for model_name, param_dict in new_params.items():
            if model_name == self.model_name:
                for param_key, model_value in param_dict.items():
                    if param_key == SNS_Dummy_BCM.beta_key:
                        reason = SNS_Dummy_BCM.freq_pv
                        beta = model_value
                        freq = beta * SNS_Dummy_BCM.c_light / SNS_Dummy_BCM.ring_length
                        self.update_measurement(reason, freq)


class SNS_Dummy_ICS(Device):
    # EPICS PV names
    beam_on_pv = 'Gate_BeamOn:RR'
    event_pv = 'Util:event46'
    trigger_pv = 'Gate_BeamOn:SSTrigger'

    def __init__(self, name: str, model_name: str = None):
        if model_name is None:
            self.model_name = name
        else:
            self.model_name = model_name
        super().__init__(name, self.model_name)

        rr_noise = AbsNoise(noise=1e-2)
        event_noise = AbsNoise(noise=1e-9)

        # Registers the device's PVs with the server.
        self.register_measurement(SNS_Dummy_ICS.beam_on_pv, noise=rr_noise)
        self.register_measurement(SNS_Dummy_ICS.event_pv, noise=event_noise)
        self.register_setting(SNS_Dummy_ICS.trigger_pv, default=0)

    def update_measurements(self, new_measurements: Dict[str, Dict[str, Any]] = None):
        self.update_measurement(SNS_Dummy_ICS.beam_on_pv, 1)
        self.update_measurement(SNS_Dummy_ICS.event_pv, 0)

    def get_settings(self) -> Dict[str, Dict[str, Any]]:
        return {}
