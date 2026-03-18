import serial
from serial_device import SerialDevice

class SPECSensor(SerialDevice):
    def __init__(self, com_port='COM4', baudrate=9600, timeout=1, verbose=True):
        super().__init__(com_port, baudrate, timeout, verbose)

    def read(self):
        """ Read gas concentration only in ppb """
        if not self.is_connected():
            print("[ERROR] Sensor is not connected.")
            return None

        try:
            self.device.write(b'\r')
            sensorData_byte = self.device.readline()

            # Ensure data is received
            if not sensorData_byte:
                print("[WARNING] No data received from sensor.")
                return None

            sensorData_str = sensorData_byte.decode('ascii').strip().split(',')
            
            if len(sensorData_str) < 4:
                print(f"[ERROR] Unexpected sensor data format: {sensorData_str}")
                return None

            # sensorData = int(sensorData_str[1])
            # if self.verbose:
            #     print("DGS2 data in PPB:", sensorData)
                
            # We may need Temp and RH as well for the temperature correction
            sensorData = [float(sensorData_str[1])]
            sensorData += [0.01 * float(elem) for elem in sensorData_str[2:4]] # [ppb, C, %]
            if self.verbose:
                print(f'DGS2 - Concentration: {sensorData[0]:.0f} ppb, Temp: {sensorData[1]:.2f} C, RH: {sensorData[2]:.2f} %')

            return sensorData
        
        except (serial.SerialException, ValueError, IndexError) as e:
            print(f"[ERROR] Failed to read from sensor: {e}")
            return None

    """ Never close the SPEC sensor  """
    # def __del__(self):
    #     """Destructor to close the serial connection when the object is deleted"""
    #     if self.sensor.is_open:
    #         self.sensor.close()
    #         print(f"Serial port {self.com_port} closed.")
    #     else:
    #         print(f"Serial port {self.com_port} was already closed.")


""" Example """
if __name__ == "__main__":
    VERBOSE = True
    sensor = SPECSensor(com_port = 'COM4',
                        baudrate = 9600,
                        timeout = 1,
                        verbose = VERBOSE)
    
    sensor.read()
    import time
    time.sleep(2)
    sensor.read()
