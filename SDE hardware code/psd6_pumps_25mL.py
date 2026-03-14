import time
import numpy as np
import serial
from typing import Final

# Constants for valves and a pump 
WASTE: Final = 1
LIQUID_OUT: Final = 3   # Dispensing
LIQUID_IN: Final = 2    # Refilling
AIR_OUT: Final = 5      # Shared Dispensing pathway
AIR_IN: Final = 4

CLEANING_PUMP: Final = 0

class PSD6Pumps():
    def __init__(self, com_ports: list=['COM21', 'COM22', 'COM23', 'COM24'], baud_rate=38400, timeout=1, verbose=False):
        # Create serial connections for pumps
        """ pumps[0] for DI/Air, pumps[1:] for electrolytes """
        self.PSD6_pumps = [serial.Serial(port, baud_rate, timeout=timeout) for port in com_ports]
        for pump in self.PSD6_pumps:
            pump.write(self.command_compiler('N0'))
        self.verbose = verbose


    def command_compiler(self, command: str):
        # / is the start bit, 1 is the address, R is the stop bit
        # since we are not chaining device here, address is always 1
        return bytes(f'/1{command}R\r', 'utf-8')


    def initialize(self, *, duration=60):
        ''' Blocking function '''
        # Valve towards WASTE to minimize backpressure
        self.select_valve(list(range(len(self.PSD6_pumps))), WASTE)
        for pump in self.PSD6_pumps:
            pump.write(self.command_compiler('Y'))

        # Ensure the plunger to go position 0 - Blocking method
        ''' Warnings: without proper purposes, never change the duration'''
        time.sleep(duration)
        if self.verbose:
            print(f'Initialization DONE')


    def select_valve(self, pump_nums: list | int, valve: int):
        """ 
        Update on Apr 07, 2025
        1: Hold for initialization -> Waste
        2: Liquid/Air outlet (dispense)
        3: Liquid inlet (refill)
        4-6: Additional valves if necessary
        4: Air inlet (dispense)
        """
        if isinstance(pump_nums, int):
            pump_nums = [pump_nums]
            
        self.stop_pumps(pump_nums)
        for idx in pump_nums:
            self.PSD6_pumps[idx].write(self.command_compiler(f'I{valve}'))
            if self.verbose:
                print(f'PSD6 pump No.{idx}: valve switching to {valve}')
        time.sleep(1.0)

    ''' Apr 11: Not using in the dispense() method '''
    def set_flowrate(self, pump_nums: list | int, flowrates: list | float | int):
        # Roughly, set 500 (half)steps/sec -> ~55 sccm
        # set 36 -> ~4 sccm
        if isinstance(pump_nums, int):
            pump_nums = [pump_nums]
        if isinstance(flowrates, (float, int)):
            flowrates = [flowrates]

        ''' Here, we don't check the validity of flowrates (i.e. -2, 1000000 sccm);
            the syringe pumps just ignore it.
        '''
        # flowrate = 26.9 -> '/1V26.9R' -> Not a valid command
        rounded_flowrates = [round(flowrates[i]) if pump_nums[i] != 3 else round(flowrates[i]/1.101) for i in range(len(pump_nums))]

        #rounded_flowrates = [round(flowrate) for flowrate in flowrates]


        for i, idx in enumerate(pump_nums):
            self.PSD6_pumps[idx].write(self.command_compiler(f'V{rounded_flowrates[i]}'))
            if self.verbose:
                print(f'PSD6 pump No.{idx}: set flowrate to {rounded_flowrates[i]} - could be rounded')

        time.sleep(1.0)


    def refill(self, pump_nums: list | int = [0, 1, 2, 3]):
        ''' Non-blocking function: Need to put stop() explicitly '''
        if isinstance(pump_nums, int):
            pump_nums = [pump_nums]

        self.select_valve(pump_nums, LIQUID_IN)
        for idx in pump_nums:
            if idx == 3:
                self.PSD6_pumps[idx].write(self.command_compiler('V437A5687')) # 40 mL Maximum
            else:
                self.PSD6_pumps[idx].write(self.command_compiler('V500A6500')) # 40 mL Maximum

            if self.verbose:
                print(f'PSD6 pump No.{idx}: Refilling')

        time.sleep(1.0)

    
    # def refill_air(self, pump_nums: list | int = [0, 1, 2, 3]):
    #     if isinstance(pump_nums, int):
    #         pump_nums = [pump_nums]

    #     self.select_valve(pump_nums, AIR_IN)
    #     for idx in pump_nums:
    #         self.PSD6_pumps[idx].write(self.command_compiler('V500A13714')) # Air refill flowrates here
    #         if self.verbose:
    #             print(f'PSD6 pump No.{idx}: Refilling Air')
    #     time.sleep(0.5)


    def dispense(self, pump_nums: list | int, flowrates: list | float | int):
        ''' Non-blocking function '''
        if isinstance(pump_nums, int):
            pump_nums = [pump_nums]
        if isinstance(flowrates, (float, int)):
            flowrates = [round(flowrates)]

        rounded_flowrates = [round(flowrates[i]) if pump_nums[i] != 3 else round(flowrates[i]/1.101) for i in range(len(pump_nums))]

        # Apr 11: It might occur error due to the timing issue
        # self.set_flowrate(pump_nums, flowrates) 
        self.select_valve(pump_nums, LIQUID_OUT)

        # for idx in pump_nums:
        #     self.PSD6_pumps[idx].write(self.command_compiler('A0'))
        #     if self.verbose:
        #         print(f'PSD6 pump No.{idx}: Dispensing')

        for idx, flowrate in zip(pump_nums, rounded_flowrates):
            self.PSD6_pumps[idx].write(self.command_compiler(f'V{flowrate}A0'))
            if self.verbose:
                print(f'PSD6 pump No.{idx}: Dispensing at {flowrate} steps/sec - could be rounded')

        time.sleep(1.0)


    # def dispense_air(self, pump_nums: list | int = [0, 1, 2, 3]):
    #     ''' Non-blocking function '''
    #     if isinstance(pump_nums, int):
    #         pump_nums = [pump_nums]

    #     self.select_valve(pump_nums, AIR_OUT)

    #     for idx in pump_nums:
    #         self.PSD6_pumps[idx].write(self.command_compiler('V250A0')) # Dispense air flowrates here
    #         if self.verbose:
    #             print(f'PSD6 pump No.{idx}: Dispensing Air')

    #     time.sleep(0.5)

    # def remove_bubble(self, pump_nums: list | int = [0, 1, 2, 3]):
    #     ''' Blocking Function '''
    #     if isinstance(pump_nums, int):
    #         pump_nums = [pump_nums]

    #     self.select_valve(pump_nums, WASTE)

    #     for idx in pump_nums:
    #         self.PSD6_pumps[idx].write(self.command_compiler('V500A0')) # Dispense air flowrates here
    #         if self.verbose:
    #             print(f'PSD6 pump No.{idx}: Bubble being removed in the syringe')

    #     time.sleep(2.0)

    #     self.stop_pumps(pump_nums)

    #     # Compensate the electrolytes
    #     self.refill(pump_nums) # Wait for 1 second in the method
    #     self.stop_pumps(pump_nums)


    def stop_pumps(self, pump_nums: list | int = [0, 1, 2, 3]):
        if isinstance(pump_nums, int):
            pump_nums = [pump_nums]

        for idx in pump_nums:
            self.PSD6_pumps[idx].write(self.command_compiler('T'))
            if self.verbose:
                print(f'PSD6 pump No.{idx}: Stopped')

        time.sleep(1.0)


    def close_pumps(self):
        for pump in self.PSD6_pumps:
            pump.close()
        if self.verbose:
            print(f'Closed')


# Usage
if __name__ == '__main__':
    try:
        PSD6_controller = PSD6Pumps(verbose=True)
        
        print("1. Initializing")
        PSD6_controller.initialize()
        
        print("2. Refilling")
        # PSD6_controller.refill()
        # time.sleep(5)
        # PSD6_controller.refill([3])
        # time.sleep(5)
        # PSD6_controller.stop_pumps([3])

        # PSD6_controller.dispense([3], [437])

        # time.sleep(8)

        PSD6_controller.refill([0,1,2,3])
        time.sleep(15)
        PSD6_controller.stop_pumps([0,1,2,3])
                
        print("3. Dispensing")
        PSD6_controller.dispense([0,1,2,3], [125,125,125,125])
        time.sleep(15)
        PSD6_controller.stop_pumps([0,1,2,3])
        
        print("6. Stopping")
   
        PSD6_controller.close_pumps()

    except (KeyboardInterrupt, TimeoutError, IndexError):
        PSD6_controller.stop_pumps([0, 1, 2, 3])
        PSD6_controller.close_pumps()