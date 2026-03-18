import time
import nidaqmx
from nidaqmx.constants import TerminalConfiguration

class NIUSB621xController:
    def __init__(self, device_name='dev1', write_channel='ao0', read_channel='ai1', verbose=True):
        """
        Initializes the NI USB-621x device for analog input and output.
        :param device_name: The name of the NI device (default: 'dev1')
        :param write_channel: The analog output channel (default: 'ao0')
        :param read_channel: The analog input channel (default: 'ai0')
        """
        self.device_name = device_name
        self.write_channel = write_channel
        self.read_channel = read_channel
        self.verbose = verbose
        
        # Create separate tasks for writing and reading
        self.write_task = nidaqmx.Task()
        self.read_task = nidaqmx.Task()
        
        # Add an analog output voltage channel
        self.write_task.ao_channels.add_ao_voltage_chan(f"{self.device_name}/{self.write_channel}")
        
        # Add an analog input voltage channel
        self.read_task.ai_channels.add_ai_voltage_chan(f"{self.device_name}/{self.read_channel}", 
                                                       terminal_config=TerminalConfiguration.RSE)
        if self.verbose:
            print(f"Initialized {self.device_name} with write channel {self.write_channel} and read channel {self.read_channel}")
    
    def analogWrite(self, voltage):
        """Sets the voltage to the specified value."""
        try:
            self.write_task.write(voltage)
            if self.verbose:
                print(f"Voltage set to {voltage}V on {self.device_name}/{self.write_channel}")
        except Exception as e:
            print(f"Error writing voltage to {self.device_name}/{self.write_channel}: {e}")
    
    def analogRead(self):
        """Reads the voltage from the analog input channel."""
        try:
            voltage = self.read_task.read()
            if self.verbose:
                print(f"Voltage read from {self.device_name}/{self.read_channel}: {voltage:.3f} V")
        except Exception as e:
            print(f"Error reading voltage to {self.device_name}/{self.read_channel}: {e}")
            
        return voltage

    def __del__(self):
        """Ensures the tasks are properly closed when the object is deleted."""
        if self.write_task:
            self.analogWrite(0.0) # reset channel to 0 volt output
            self.write_task.stop()
            self.write_task.close()
            if self.verbose:
                print(f"Write task for {self.device_name}/{self.write_channel} closed.")
        if self.read_task:
            self.read_task.stop()
            self.read_task.close()
            if self.verbose:
                print(f"Read task for {self.device_name}/{self.read_channel} closed.")







""" Example """
if __name__ == "__main__":
    VERBOSE = True
    controller = NIUSB621xController(device_name = 'dev1', 
                                     write_channel = 'ao0',
                                     read_channel = 'ai1', 
                                     verbose = VERBOSE)
    controller.analogWrite(5.0)
    try:
        while True:
            controller.analogRead()
            time.sleep(0.5)
    except KeyboardInterrupt:
        del controller
