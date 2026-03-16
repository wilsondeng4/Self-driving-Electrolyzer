import serial
import time
from serial_device import SerialDevice

class PeriPump():

    def __init__(self, com_port='COM5', baudrate = 9600, timeout = 1, verbose = True):
        self.pump = SerialDevice(com_port, baudrate, timeout, verbose)

    def __del__(self):
        #stop pump function and disconnect function here
        self.stop()
        self.pump.disconnect()
        print("PeriPump stopped and disconnected")

    def send_command(self, command: str):
        if self.pump.is_connected():
            try:
                command = bytes.fromhex(command) #command is in hex format
                #Note that the 7th bit is a check sum. Since we only run at 2 different flowrate,
                #We choose not to have a function to calculate check sum.
                self.pump.device.write(command)
                #after writing, pump does reply a serial command, we choose not to receive here.
                time.sleep(0.1)
            except serial.SerialException as e:
                print(f"Serial Error: {e}")
        else:
            print(f"Serial port {self.pump.com_port}, PeriPump is not connected.")
    
    def start(self):
        print(f"{self.pump.com_port} PeriPump start.")
        self.send_command("CC 01 48 00 00 DD F2 01")

    def stop(self):
        print(f"{self.pump.com_port} PeriPump stop.")
        self.send_command("CC 01 49 00 00 DD F3 01")

    def set_flowrate_25_start(self):
        #Note, without stopping the pump, flowrate cannot be changed.
        self.stop()
        print(f"{self.pump.com_port} PeriPump set flowrate to 25mL/min.")
        self.send_command("CC 01 4B 80 01 DD 76 02") #38
        self.start()

    def set_flowrate_17_start(self):
        #Note, without stopping the pump, flowrate cannot be changed.
        self.stop()
        print(f"{self.pump.com_port} PeriPump set flowrate to 17mL/min.")
        self.send_command("CC 01 4B 06 01 DD FC 01") #26.2
        self.start()

    def set_flowrate_1_start(self):
        #Note, without stopping the pump, flowrate cannot be changed.
        self.stop()
        print(f"{self.pump.com_port} PeriPump set flowrate to 1mL/min.")
        self.send_command("CC 01 4B 10 00 DD 05 02") #1.5
        self.start()

if __name__ == "__main__":

    Sample = PeriPump()
    Sample.set_flowrate_17_start()
    time.sleep(5)
    Sample.stop()
    Sample.set_flowrate_1_start()
    time.sleep(5)
    Sample.stop()
    del Sample
