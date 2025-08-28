from gpiozero import DigitalOutputDevice, DigitalInputDevice

import os

# import csv
import time

import logging
import sys

from enum import Enum
from typing import Union

from jtag_device import JTAGDevice


class JtagLeg(Enum):
    DR = 0
    IR = 1
    RS = 2  # reset
    DL = 3  # long delay
    ID = 4  # idle in run-test
    IRP = 5  # IR with pause
    IRD = 6  # transition to IR directly
    DRC = 7  # DR for config: MSB-to-LSB order, and use fast protocols
    DRR = 8  # DR for recovery: print out the value returned in non-debug modes
    DRS = 9  # DR for SPI: MSB-to-LSB order, use fast protocols, but also readback data


class JtagState(Enum):
    TEST_LOGIC_RESET = 0
    RUN_TEST_IDLE = 1
    SELECT_SCAN = 2
    CAPTURE = 3
    SHIFT = 4
    EXIT1 = 5
    PAUSE = 6
    EXIT2 = 7
    UPDATE = 8


class JTAGRpi:
    def __init__(
        self,
        TCK_pin: int = 13,
        TMS_pin: int = 27,
        TDI_pin: int = 26,
        TDO_pin: int = 5,
        name="RPi JTAG",
    ) -> None:
        self.TCK_pin = TCK_pin
        self.TMS_pin = TMS_pin
        self.TDI_pin = TDI_pin
        self.TDO_pin = TDO_pin

        self.log = logging.getLogger(f"{name}")
        self.log.setLevel(logging.INFO)
        self.devices = []
        self.last_ir_val = -1


        self.state = JtagState.RUN_TEST_IDLE
        self.jtag_legs = []

        self.readout = False
        self.do_pause = False
        self.cur_leg = []
        self.tdo_vect = ""
        self.tdo_stash = ""
        self.jtag_results = []
        self.readdata = 0

        self.tms_reset_num = 7

        # Initialize GPIO pins using gpiozero
        self.tck = DigitalOutputDevice(self.TCK_pin)
        self.tms = DigitalOutputDevice(self.TMS_pin)
        self.tdi = DigitalOutputDevice(self.TDI_pin)
        self.tdo = DigitalInputDevice(self.TDO_pin)

    def _set_tck_tdi_simultaneous(self, tck_val, tdi_val):
        """Set TCK and TDI with minimal timing skew for JTAG operations"""
        # For JTAG timing: Set TDI first (data setup), then TCK (clock edge)
        # This ensures data is stable before the clock transition
        raise Exception("DRC/DRS not implemented") 
        self.tdi.value = tdi_val
        self.tck.value = tck_val

    def debug_log(self, cur_leg):

        #     if not((cur_leg[0] == JtagLeg.DRC) or (cur_leg[0] == JtagLeg.DRS)):
        #         logging.debug("start: %s (%s) / %s", str(cur_leg), str(decode_ir(int(cur_leg[1],2))), str(cur_leg[2]) )
        #     else:
        self.log.debug(
            "start: %s config data of length %s", cur_leg[0], str(len(cur_leg[1]))
        )

    def phy_sync(self, tdi, tms):
        tdo = self.tdo.value  # grab the TDO value before the clock changes

        # Set initial states: TCK=0, TDI=tdi, TMS=tms
        self.tck.value = 0
        self.tdi.value = tdi
        self.tms.value = tms
        
        # Clock rising edge
        self.tck.value = 1
        
        # Clock falling edge
        self.tck.value = 0

        return tdo

    def jtag_step(self):
        if self.state == JtagState.TEST_LOGIC_RESET:
            if not 0 == len(self.jtag_legs):
                self.phy_sync(0, 0)
                self.state = JtagState.RUN_TEST_IDLE
                self.last_ir_val = -1

        elif self.state == JtagState.RUN_TEST_IDLE:
            if len(self.cur_leg):
                if (
                    self.cur_leg[0] == JtagLeg.DR
                    or self.cur_leg[0] == JtagLeg.DRC
                    or self.cur_leg[0] == JtagLeg.DRR
                    or self.cur_leg[0] == JtagLeg.DRS
                ):
                    self.phy_sync(0, 1)
                    if self.cur_leg[0] == JtagLeg.DRR or self.cur_leg[0] == JtagLeg.DRS:
                        self.readout = True
                    else:
                        self.readout = False
                    self.state = JtagState.SELECT_SCAN
                elif self.cur_leg[0] == JtagLeg.IR or self.cur_leg[0] == JtagLeg.IRD:
                    self.phy_sync(0, 1)
                    self.phy_sync(0, 1)
                    self.do_pause = False
                    self.state = JtagState.SELECT_SCAN
                elif self.cur_leg[0] == JtagLeg.IRP:
                    self.phy_sync(0, 1)
                    self.phy_sync(0, 1)
                    self.do_pause = True
                    self.state = JtagState.SELECT_SCAN
                elif self.cur_leg[0] == JtagLeg.RS:
                    self.log.info("TMS reset")
                    for i in range(self.tms_reset_num):
                        self.phy_sync(0, 1)

                    self.state = JtagState.TEST_LOGIC_RESET
                    self.last_ir_val = -1
                    try:
                        self.cur_leg = self.jtag_legs.pop(0)
                        self.debug_log(self.cur_leg)
                    except IndexError:
                        self.cur_leg = []
                #                         return
                elif self.cur_leg[0] == JtagLeg.DL:
                    time.sleep(0.005)  # 5ms delay
                    self.cur_leg = self.jtag_legs.pop(0)
                    self.debug_log(self.cur_leg)
                elif self.cur_leg[0] == JtagLeg.ID:
                    self.phy_sync(0, 0)
                    self.cur_leg = self.jtag_legs.pop(0)
                    self.debug_log(self.cur_leg)
            else:
                if len(self.jtag_legs):
                    self.cur_leg = self.jtag_legs.pop(0)
                    self.debug_log(self.cur_leg)
                else:
                    self.phy_sync(0, 0)
                self.state = JtagState.RUN_TEST_IDLE

        elif self.state == JtagState.SELECT_SCAN:
            self.phy_sync(0, 0)
            self.state = JtagState.CAPTURE

        elif self.state == JtagState.CAPTURE:
            self.phy_sync(0, 0)
            self.tdo_vect = ""  # prep the tdo_vect to receive data
            self.state = JtagState.SHIFT

        elif self.state == JtagState.SHIFT:
            if self.cur_leg[0] == JtagLeg.DRC or self.cur_leg[0] == JtagLeg.DRS:
                raise Exception("DRC/DRS not implemented")
                if (
                    self.cur_leg[0] == JtagLeg.DRC
                ):  # duplicate code because we want speed (eliminating TDO readback is significant speedup)
                    self._set_tck_tdi_simultaneous(0, 1)  # TCK=0, TDI=1
                    for bit in self.cur_leg[1][:-1]:
                        if bit == "1":
                            self._set_tck_tdi_simultaneous(1, 1)  # TCK=1, TDI=1
                            self._set_tck_tdi_simultaneous(0, 1)  # TCK=0, TDI=1
                        else:
                            self._set_tck_tdi_simultaneous(1, 0)  # TCK=1, TDI=0
                            self._set_tck_tdi_simultaneous(0, 0)  # TCK=0, TDI=0
                else:  # jtagleg is DRS -- duplicate code, as TDO readback slows things down significantly
                    self._set_tck_tdi_simultaneous(0, 1)  # TCK=0, TDI=1
                    for bit in self.cur_leg[1][:-1]:
                        if bit == "1":
                            self._set_tck_tdi_simultaneous(1, 1)  # TCK=1, TDI=1
                            self._set_tck_tdi_simultaneous(0, 1)  # TCK=0, TDI=1
                        else:
                            self._set_tck_tdi_simultaneous(1, 0)  # TCK=1, TDI=0
                            self._set_tck_tdi_simultaneous(0, 0)  # TCK=0, TDI=0
                    tdo = self.tdo.value
                    if tdo == 1:
                        self.tdo_vect = "1" + self.tdo_vect
                    else:
                        self.tdo_vect = "0" + self.tdo_vect

                self.state = JtagState.SHIFT

                if self.cur_leg[-1:] == "1":
                    tdi = 1
                else:
                    tdi = 0
                self.cur_leg = []
                tdo = self.phy_sync(tdi, 1)
                if tdo == 1:
                    self.tdo_vect = "1" + self.tdo_vect
                else:
                    self.tdo_vect = "0" + self.tdo_vect
                self.state = JtagState.EXIT1
                self.log.debug("leaving config")

            else:
                if len(self.cur_leg[1]) > 1:
                    if self.cur_leg[1][-1] == "1":
                        tdi = 1
                    else:
                        tdi = 0
                    self.cur_leg[1] = self.cur_leg[1][:-1]
                    tdo = self.phy_sync(tdi, 0)
                    if tdo == 1:
                        self.tdo_vect = "1" + self.tdo_vect
                    else:
                        self.tdo_vect = "0" + self.tdo_vect
                    self.state = JtagState.SHIFT
                else:  # this is the last item
                    if self.cur_leg[1][0] == "1":
                        tdi = 1
                    else:
                        tdi = 0
                    self.cur_leg = []
                    tdo = self.phy_sync(tdi, 1)
                    if tdo == 1:
                        self.tdo_vect = "1" + self.tdo_vect
                    else:
                        self.tdo_vect = "0" + self.tdo_vect
                    self.state = JtagState.EXIT1

        elif self.state == JtagState.EXIT1:
            tdo_stash = self.tdo_vect
            if self.do_pause:
                self.phy_sync(0, 0)
                self.state = JtagState.PAUSE
                self.do_pause = False
            else:
                self.phy_sync(0, 1)
                self.state = JtagState.UPDATE

        elif self.state == JtagState.PAUSE:
            self.log.debug("pause")
            # we could put more pauses in here but we haven't seen this needed yet
            self.phy_sync(0, 1)
            self.state = JtagState.EXIT2

        elif self.state == JtagState.EXIT2:
            self.phy_sync(0, 1)
            self.state = JtagState.UPDATE

        elif self.state == JtagState.UPDATE:
            self.jtag_results.append(
                int(self.tdo_vect, 2)
            )  # interpret the vector and save it
            self.log.debug("result: %s", str(hex(int(self.tdo_vect, 2))))
            if self.readout:
                # print('readout: 0x{:08x}'.format( int(tdo_vect, 2) ) )
                self.readdata = int(self.tdo_vect, 2)
                self.readout = False
            self.tdo_vect = ""

            # handle case of "shortcut" to DR
            if len(self.jtag_legs):
                if (
                    (self.jtag_legs[0][0] == JtagLeg.DR)
                    or (self.jtag_legs[0][0] == JtagLeg.IRP)
                    or (self.jtag_legs[0][0] == JtagLeg.IRD)
                ):
                    if (
                        self.jtag_legs[0][0] == JtagLeg.IRP
                        or self.jtag_legs[0][0] == JtagLeg.IRD
                    ):
                        self.phy_sync(0, 1)  # +1 cycle on top of the DR cycle below
                        self.log.debug("IR bypassing wait state")
                    if self.jtag_legs[0][0] == JtagLeg.IRP:
                        self.do_pause = True

                    self.cur_leg = self.jtag_legs.pop(0)
                    self.debug_log(self.cur_leg)
                    self.phy_sync(0, 1)
                    self.state = JtagState.SELECT_SCAN
                else:
                    self.phy_sync(0, 0)
                    self.state = JtagState.RUN_TEST_IDLE
            else:
                self.phy_sync(0, 0)
                self.state = JtagState.RUN_TEST_IDLE

        else:
            print("Illegal state encountered!")

    def jtag_next(self):
        if (
            self.state == JtagState.TEST_LOGIC_RESET
            or self.state == JtagState.RUN_TEST_IDLE
        ):
            if len(self.jtag_legs):
                # run until out of idle
                while (
                    self.state == JtagState.TEST_LOGIC_RESET
                    or self.state == JtagState.RUN_TEST_IDLE
                ):
                    self.jtag_step()
                    if 0 == len(self.cur_leg):
                        break

                # run to idle
                while (
                    self.state != JtagState.TEST_LOGIC_RESET
                    and self.state != JtagState.RUN_TEST_IDLE
                ):
                    self.jtag_step()
            else:
                # this should do nothing
                self.jtag_step()
        else:
            # we're in a leg, run to idle
            while (
                self.state != JtagState.TEST_LOGIC_RESET
                and self.state != JtagState.RUN_TEST_IDLE
            ):
                self.jtag_step()

    def process_command(self):
        while len(self.jtag_legs):
            self.jtag_next()

    def parse_rows(self, rows) -> None:
        self.jtag_legs = []
        self.cur_leg = []
        self.jtag_results = []
        for row in rows:
            self.parse_row(row)
        self.process_command()

    def parse_row(self, row) -> list:
        self.log.debug(row)
        if len(row) < 3:
            return []
        chain = str(row[0]).lower().strip()
        if chain[0] == "#":
            return []
        length = int(row[1])
        if str(row[2]).strip()[:2] == "0x":
            value = int(row[2], 16)
        elif str(row[2]).strip()[:2] == "0b":
            value = int(row[2], 2)
        else:
            value = int(row[2])

        if (
            (chain != "dr")
            & (chain != "ir")
            & (chain != "rs")
            & (chain != "dl")
            & (chain != "id")
            & (chain != "irp")
            & (chain != "ird")
            & (chain != "drc")
            & (chain != "drr")
            & (chain != "drs")
        ):
            self.log.critical("unknown chain type ", chain, " aborting!")
            exit(1)

        # logging.debug('found JTAG chain ', chain, ' with len ', str(length), ' and data ', hex(value))
        if chain == "rs":
            cmd = [JtagLeg.RS, "0", "0"]
        elif chain == "dl":
            cmd = [JtagLeg.DL, "0", "0"]
        elif chain == "id":
            cmd = [JtagLeg.ID, "0", "0"]

        else:
            if chain == "dr":
                code = JtagLeg.DR
            elif chain == "drc":
                raise Exception("DRC not implemented")
                code = JtagLeg.DRC
            elif chain == "drr":
                raise Exception("DRR not implemented")
                code = JtagLeg.DRR
            elif chain == "drs":
                raise Exception("DRS not implemented")
                code = JtagLeg.DRS
            elif chain == "ir":
                code = JtagLeg.IR
            elif chain == "ird":
                code = JtagLeg.IRD
            else:
                code = JtagLeg.IRP
            if len(row) > 3:
                cmd = [code, "%0*d" % (length, int(bin(value)[2:])), row[3]]
            else:
                cmd = [code, "%0*d" % (length, int(bin(value)[2:])), " "]
        self.jtag_legs.append(cmd)
        return cmd

    def finish(self) -> None:
        # gpiozero handles cleanup automatically
        pass

    @property
    def active_device(self) -> JTAGDevice:
        return self.devices[self.device]

    def add_device(self, device: JTAGDevice) -> None:
        self.devices.append(device)

    def reset_fsm(self, num: int = 7) -> None:
        self.tms_reset_num = num
        cmd = "rs, 0, 0"
        rows = []
        rows.append(cmd.split(","))
        self.parse_rows(rows)

    def access(
        self,
        addr: Union[int, str],
        data: int = -1,
        device: int = 0,
        write: bool = False,
    ):
        self.device = device
        self.jwrite = write
        if isinstance(addr, str):
            addr = self.active_device.names[addr].address
        #         elif -1 == addr:
        #             addr = addr
        elif isinstance(addr, int):
            addr = addr
        else:
            raise Exception(f"Unknown format for addr: {addr}")
        name = self.active_device.addresses[addr].name

        #         if addr is None:
        #             self.dr_len = self.shift_dr_num
        #         else:

        self.dr_len = self.active_device.addresses[addr].width
        self.dr_mask = (2**self.dr_len) - 1
        #         self.dr_val = val
        if -1 == data:
            self.total_dr_val = None
        else:
            self.total_dr_val = data << (len(self.devices) - 1 - self.device)
        self.total_dr_len = self.dr_len + len(self.devices) - 1

        self.ir_val = addr
        self.total_ir_len = 0
        self.total_ir_val = 0
        if addr is not None:
            for i, d in reversed(list(enumerate(self.devices))):
                if i == device:
                    if isinstance(self.ir_val, int):
                        v = self.ir_val
                    else:
                        v = 0
                else:
                    v = self.devices[i].names["BYPASS"].address
                self.total_ir_val += v << self.total_ir_len
                self.total_ir_len += d.ir_len
        #         print(f"0x{self.total_ir_val:02x} {self.total_ir_len} {self.total_dr_len}")

        self.dr_val = 0
        if write:
            self.dr_val = data << (len(self.devices) - 1 - self.device)

        rows = []
        if not self.total_ir_val == self.last_ir_val:
            rows.append(["ir", self.total_ir_len, self.total_ir_val, "id"])
        rows.append(["dr", self.total_dr_len, self.dr_val])

        self.parse_rows(rows)
        self.last_ir_val = self.total_ir_val
        returned_data = (
            self.jtag_results.pop() >> (len(self.devices) - 1 - self.device)
        ) & self.dr_mask
        if write:
            self.log.info(f"Write [{self.device}] {name}:  0x{data:08x}")
        else:
            self.log.info(f"Read  [{self.device}] {name}:  0x{returned_data:08x}")
        return returned_data

    def read(self, addr: Union[int, str], data: int = -1, device: int = 0) -> int:
        returned_data = self.access(addr, data, device, False)
        if data > -1:
            if not data == returned_data:
                self.log.warning(
                    f"Read  {addr}: Value return 0x{returned_data:08x} doesn't match expected 0x{data:08x}"
                )
        return returned_data

    def write(self, addr: Union[int, str], data: int, device: int = 0) -> None:
        self.access(addr, data, device, True)

    def read_idcode(self, device: int = 0) -> None:
        self.device = device
        self.read("IDCODE", self.active_device.idcode, device)
        # self.log.debug(f"Read  [{self.device}] IDCODE:  0x{self.active_device.idcode:08x} SUCCESS")
