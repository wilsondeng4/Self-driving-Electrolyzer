#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 22 16:16:19 2025

@author: hslee
"""

from sensirion_shdlc_driver import ShdlcSerialPort, ShdlcConnection
from sensirion_shdlc_sfc5xxx import Sfc5xxxShdlcDevice, Sfc5xxxScaling, \
    Sfc5xxxValveInputSource, Sfc5xxxUnitPrefix, Sfc5xxxUnit, \
    Sfc5xxxUnitTimeBase, Sfc5xxxMediumUnit
import time

class SFC5xxxMFC:
    def __init__(self, portname='COM11', baudrate=9600, slave_address=0, gas_type=7, verbose = True):
        self.portname = portname
        self.baudrate = baudrate
        self.slave_address = slave_address
        self.gas_type = gas_type  # 0 for N2/Air, 7 for CO2
        self.verbose = verbose
        
        self.device = None
        self.port = None  # Ensure port reference exists

    def is_connected(self):
        """ Check if the device is connected. """
        return self.device is not None
    
    def __del__(self):
        """ Turn off the MFC by resetting the device. """
        if not self.is_connected():
            print("device is already disconnected.")
            return
    
        try:
            # Reset the device first
            self.device.device_reset()
    
            # Now you can safely release the device and port
            self.device = None
            if self.port:
                self.port.close()
                self.port = None
    
            if self.verbose:
                print(f"MFC on {self.portname} turned off.")
        except Exception as e:
            print(f"Error turning off MFC: {e}")

    def connect(self):
        """ Establish a connection to the MFC. """
        try:
            self.port = ShdlcSerialPort(self.portname, self.baudrate)
            self.device = Sfc5xxxShdlcDevice(ShdlcConnection(self.port), self.slave_address)
    
            # Set the medium unit only once when connecting
            unit = Sfc5xxxMediumUnit(
                Sfc5xxxUnitPrefix.MILLI,
                Sfc5xxxUnit.STANDARD_LITER,
                Sfc5xxxUnitTimeBase.MINUTE
            )
            self.device.set_user_defined_medium_unit(unit)
    
            # Select gas calibration **after** confirming successful connection
            self.device.activate_calibration(self.gas_type)
            if self.verbose:
                print(f"Gas calibration {self.gas_type} activated.")
                print(f"Connected to MFC on {self.portname}")          
    
        except Exception as e:
            print(f"Error connecting to MFC: {e}")
            self.device = None  # Ensure it's not mistakenly used


    def disconnect(self):
        """ Turn off the MFC by resetting the device. """
        if not self.is_connected():
            print("Error: No device connected. Cannot turn it off.")
            return
    
        try:
            # Reset the device first
            self.device.device_reset()
    
            # Now you can safely release the device and port
            self.device = None
            if self.port:
                self.port.close()
                self.port = None
    
            if self.verbose:
                print(f"MFC on {self.portname} turned off.")
        except Exception as e:
            print(f"Error turning off MFC: {e}")

    def set_flowrate(self, flowrate):
        """ Set the desired flow rate. """
        if not self.is_connected():
            print("Error: No device connected. Cannot set flowrate.")
            return

        try:
            self.device.set_setpoint(flowrate, Sfc5xxxScaling.USER_DEFINED)
            if self.verbose:
                print(f"Set flowrate to {flowrate} sccm on {self.portname}")
        except Exception as e:
            print(f"Error setting flowrate: {e}")

    def read_flow(self):
        """ Read the flow rate. """
        if not self.is_connected():
            print("Error: No device connected. Cannot monitor flow.")
            return None
        
        try:
            flowRate = self.device.read_measured_value(Sfc5xxxScaling.USER_DEFINED)
            if self.verbose:
                print(f'Measured Flow in {self.portname}: {flowRate:.2f} sccm')
            
            return flowRate
        
        except Exception as e:
            print(f"Error reading flowrate: {e}")
            return None

    def read_temperature(self):
        """ Read the MFC temperature. """
        if not self.is_connected():
            print("Error: No device connected. Cannot read temperature.")
            return None    

        try:
            temperature = self.device.measure_temperature()
            if self.verbose:
                print(f'Measured temperature of {self.portname}: {temperature:.2f} °C')
            
            return temperature
        
        except Exception as e:
            print(f"Error reading temperature: {e}")
            return None        

    def monitor_flow(self, duration):
        """ Monitor the flow rate for a specified duration. """
        """ Feb 25, 2025: Do not use this method """
        for _ in range(duration):
            self.read_flow()
            time.sleep(5)  # intervals

    def purge(self, duration):
        """ Execute purging (force open) in a duration """
        
        if not self.is_connected():
            print("Error: No device connected. Cannot purge.")
            return
        
        try:
            self.device.set_valve_input_source(Sfc5xxxValveInputSource.FORCE_OPEN)
            if self.verbose:
                print('Purging mode ON')
            time.sleep(duration)
            self.device.set_valve_input_source(Sfc5xxxValveInputSource.CONTROLLER)
            if self.verbose:
                print('Purging mode OFF')            

        except Exception as e:
            print(f"Error purging: {e}")

    def run(self, flowrate, duration):
        """ Execute the flow control process. """
        try:
            self.connect()
            if self.is_connected():
                self.set_flowrate(flowrate)
                self.monitor_flow(duration)
        finally:
            self.disconnect()

"""
        # Read whole flow value buffer
        buffer = device.read_measured_value_buffer(Sfc5xxxScaling.USER_DEFINED)
        print("Lost Values (Buffer Overrun): {}".format(buffer.lost_values))
        print("Sampling Time of Values: {:.3f} s".format(buffer.sampling_time))
        print("Buffered Flow Values: {}".format(buffer.values))
"""

if __name__ == '__main__':
    CONSTANTS_CO2 = ('COM11', 9600, 0, 7, True)
    FLOWRATE_CO2 = 10  # Flowrate in sccm

    CONSTANTS_Air = ('COM12', 9600, 0, 0, True)
    FLOWRATE_Air = 50  # Flowrate in sccm

    mfc_CO2 = SFC5xxxMFC(*CONSTANTS_CO2)
    mfc_CO2.connect()
    mfc_CO2.set_flowrate(FLOWRATE_CO2)
    # mfc_Air = SFC5xxxMFC(*CONSTANTS_Air)
    # mfc_Air.connect()
    # mfc_Air.set_flowrate(FLOWRATE_Air)
    # mfc_Air.purge(10)
    time.sleep(10)
    # mfc_Air.disconnect() # SHOULD DO THIS before closing the program!
    mfc_CO2.disconnect()
