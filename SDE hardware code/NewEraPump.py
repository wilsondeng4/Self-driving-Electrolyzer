import serial
import time
from serial_device import SerialDevice

class NewEraPump(SerialDevice):
    def __init__(self, com_port='COM26', baudrate = 19200, timeout = 1, verbose = True):
        super().__init__(com_port, baudrate, timeout, verbose)

    def __del__(self):
        if self.is_connected():
            self.disconnect()
            if self.verbose:
                print(f"Serial port {self.com_port}, NewEraPump, is closed.")
        else:
            print(f"Serial port {self.com_port}, NewEraPump, is already closed.")
    
    def send_command(self, command:str):
        if self.is_connected():
            binary_command = (command+'\r').encode("utf-8")
            try:
                self.device.write(binary_command)
                time.sleep(0.5)
            except serial.SerialException as e:
                print(f"Serial error: {e}")
        else:
            print(f"Serial port {self.com_port}, NewEraPump is not connected.")
    
    def start(self):
        self.send_command('RUN')
        if self.verbose:
            print(f"NewEraPump Started")
    
    def stop(self):
        self.send_command('STP')
        if self.verbose:
            print(f"NewEraPump Stopped")

    def forward_blocking(self, seconds:float):
        self.send_command('DIRINF')
        self.start()
        if self.verbose:
            print(f"NewEraPump set to forward and run for {seconds} seconds")
        time.sleep(seconds)
        self.stop()    

    def backward_blocking(self, seconds:float):
        self.send_command('DIRWDR')
        self.start() 
        if self.verbose:
            print(f"NewEraPump set to backward")
        time.sleep(seconds)
        self.stop()

    def dispense(self):
        self.send_command('DIRINF')
        self.start()
        if self.verbose:
            print(f"NewEraPump set to forward and run") 

    def refill(self):
        self.send_command('DIRWDR')
        self.start() 
        if self.verbose:
            print(f"NewEraPump set to backward")

    def set_flowrate(self, rate:int):
        command = 'RAT' + str(rate) + 'MM'
        self.send_command(command)
        if self.verbose:
            print(f"NewEraPump set flowrate to {rate} mL/min")

    """ Make sure no dead volume in the tubings and place the plunge to near 0 mL"""
    def initialize(self):
        self.set_flowrate(100)
        self.refill()
        time.sleep(23)
        self.stop()
        time.sleep(30)


if __name__ == "__main__":
    # Make sure plenty amount of DI (>45 mL) refilled in the pump
    DI = NewEraPump()
    DI.set_flowrate(10)
    time.sleep(1)
    DI.refill()
    time.sleep(20)
    # for _ in range(3):
    #     DI.set_flowrate(10)
    #     DI.refill()
    #     time.sleep(218)
    #     DI.stop()
    #     time.sleep(1)

    #     DI.set_flowrate(100) 
    #     DI.dispense()
    #     time.sleep(12)
    #     DI.stop()

    #     time.sleep(1)
    #     # time.sleep(95)

    #     DI.dispense()
    #     time.sleep(9)
    #     DI.stop()
    #     time.sleep(1)

    del DI