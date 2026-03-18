import serial

class SerialDevice:
    def __init__(self, com_port, baudrate=9600, timeout=1, verbose=True):
        self.com_port = com_port
        self.baudrate = baudrate
        self.timeout = timeout
        self.verbose = verbose
        
        self.device = None  # Initialize as None in case connection fails
        self.connect()
        # try:
        #     self.device = serial.Serial(self.com_port, self.baudrate, timeout=self.timeout)
        #     if self.verbose:
        #         print(f"Connected to {self.com_port} at {self.baudrate} baud.")
        # except serial.SerialException as e:
        #     print(f"[ERROR] Failed to open serial port {self.com_port}: {e}")
            
    def is_connected(self):
        """ If the serial connection fails, self.device remains None, 
        and calling self.device.is_open directly would cause an error:"""
        return self.device is not None and self.device.is_open
    
    def connect(self):
        if not self.is_connected():
            try:
                self.device = serial.Serial(self.com_port, self.baudrate, timeout=self.timeout)
                if self.verbose:
                    print(f"Connected to {self.com_port} at {self.baudrate} baud.")
            
            except serial.SerialException as e:
                print(f"[ERROR] Failed to open serial port {self.com_port}: {e}")
        
        else:
            print(f"Serial port {self.com_port} was already opened.")  
                
    
    def disconnect(self): 
        if self.is_connected():
            try:
                self.device.close()
                if self.verbose:
                    print(f"Serial port {self.com_port} closed.")
            
            except serial.SerialException as e:
                print(f"[ERROR] Failed to close serial port {self.com_port}: {e}")                   
        else:
            print(f"Serial port {self.com_port} was already closed.")  
    
