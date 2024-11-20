import micropython
micropython.alloc_emergency_exception_buf(200)
from machine import Pin, ADC, I2C
from ssd1306 import SSD1306_I2C
from fifo import Fifo
from led import Led
import time
from piotimer import Piotimer
import math
import network
from umqtt.simple import MQTTClient
import socket
import mip
import ujson
import urequests as requests

class Network:
    def __init__(self):
        self.ssid = "KME761_Group_5"
        self.password = "TeamFive12345?"
        self.broker_ip = "192.168.5.253"
        self.wlan = None
        self.mqtt_client = None
        self.oled = OLED()
    
    def connect_to_wlan(self):
        # Create WLAN instance and connect to the network
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(self.ssid, self.password)
        
        # Attempt to connect once per second
        while not self.wlan.isconnected():
            self.oled.display_message("Hello!")
            print("Connecting to WLAN...")
            time.sleep(1)
        
        # Print the IP address of the Pico
        print("Connection successful. Pico IP:", self.wlan.ifconfig()[0])
    
    def connect_mqtt(self):
        # Create and connect to MQTT client
        self.mqtt_client = MQTTClient("", self.broker_ip)
        self.mqtt_client.connect(clean_session=True)
        print(f"Connected to MQTT broker at {self.broker_ip}")
        return self.mqtt_client
    
    def send_mqtt_message(self, topic, message, interval=5):
        try:
            # Sending a message every `interval` seconds
            self.mqtt_client.publish(topic, message)
            print(f"Sending to MQTT: {topic} -> {message}")
        except Exception as e:
            print(f"Failed to send MQTT message: {e}")



class Encoder:
    def __init__(self):
        self.a = Pin(10, mode = Pin.IN, pull = Pin.PULL_UP)
        self.b = Pin(11, mode = Pin.IN, pull = Pin.PULL_UP)
        self.btn = Pin(12, mode = Pin.IN, pull = Pin.PULL_UP)
        self.fifo = Fifo(30, typecode = 'i') #fifo to store rotate/ pressevent 
        self.a.irq(handler = self.rot_handler, trigger = Pin.IRQ_RISING, hard = True)
        self.btn.irq(handler = self.btn_handler, trigger = Pin.IRQ_RISING, hard = True)
        self.current_time = 0 #keep track of time diff bw button press
        self.prev_time = 0
        
    def rot_handler(self, pin):
        if self.b():
            self.fifo.put(-1) #to move arrow up when turn anti-clockwise
        else:
            self.fifo.put(1) #to move arrow down when turn clockwise
    
    def btn_handler(self, pin):
        self.current_time = time.ticks_ms()
        if int(self.current_time) - int(self.prev_time) > 300: #debounce time 300ms bw button press
            self.fifo.put(5)
            self.prev_time = self.current_time
 



class OLED:
    def __init__(self, scl_pin=15, sda_pin=14, width=128, height=64, freq=400000):
        # Initialize the I2C and OLED display
        self.i2c = I2C(1, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=freq)
        self.oled = SSD1306_I2C(width, height, self.i2c)
        self.heart = [
            [0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 1, 0, 0, 0, 1, 1, 0],
            [1, 1, 1, 1, 0, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 1, 1, 0, 0],
            [0, 0, 0, 1, 1, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0],
        ]
        self.size = 8
        self.max_adc = 65535
        self.last_x = -1
        self.last_y = self.oled.height//2
        
    def display_menu(self, lines, arrow_pos, left_arrow, right_arrow):
        self.oled.fill(0)  # Clear screen
        # Display each line of the menu
        for i, line in enumerate(lines):
            self.oled.text(line, self.size, i * self.size * 2)
        
        # Display left and right arrows
        self.oled.text(left_arrow, 0, arrow_pos)
        right_arrow_x = len(lines[0]) * self.size + self.size
        self.oled.text(right_arrow, right_arrow_x, arrow_pos)
        self.oled.show()
        
    def display_heart_rate(self, hr):
        # Clear top text area
        self.oled.fill_rect(0, 0, self.oled.width, self.size, 0)
        self.oled.text(f"{hr} bpm", 12, 0)
        for y, row in enumerate(self.heart):
            for x, c in enumerate(row):
                self.oled.pixel(x, y, c)
        
    def display_time(self, time):
        self.oled.fill_rect(0, self.oled.height-self.size, self.oled.width, self.oled.height, 0)
        self.oled.text(f"Time: {time}s", 12, self.oled.height-8)
       
    def display_val(self,val):
        y = self.oled.height - int(val*self.oled.height/self.max_adc) 
        y = max(self.size + 2, min(self.oled.height-self.size-2 , y))
        x = self.last_x + 1
        self.oled.line(x, self.size, x, self.oled.height-self.size, 0)
        self.oled.line(self.last_x, self.last_y, x, y, 1)
        
        self.oled.show()
        
        self.last_x = x
        if self.last_x > self.oled.width-1:
            self.last_x = -1
        self.last_y = y
        
    def display_stats(self, mean_hr, mean_ppi, rmssd, sdnn):
        # Clear bottom text area
        self.oled.fill(0)
        stats = [
            f"Mean HR: {mean_hr:.0f}",
            f"Mean PPI: {mean_ppi:.0f}",
            f"RMSSD: {rmssd:.0f}",
            f"SDNN: {sdnn:.0f}",
        ]
        for i, stat in enumerate(stats):
            self.oled.text(stat, 0, i * 16)

        self.oled.show()
    
    def display_message(self,text):
        self.oled.fill(1)
        if len(text)*self.size < self.oled.width - self.size:
            self.oled.text(text, self.size, self.oled.height//2, 0)
        else:
            print("Message too long!")
        self.oled.show()
        #time.sleep(1)

    def display_kubios(self, timestamp, mean_hr, mean_ppi, rmssd, sdnn, sns, pns):
        # Clear bottom text area
        self.oled.fill(0)
        stats = [
            f"{timestamp}",
            f"Mean HR: {mean_hr:.0f}",
            f"Mean PPI: {mean_ppi:.0f}",
            f"RMSSD: {rmssd:.0f}",
            f"SDNN: {sdnn:.0f}",
            f"SNS: {sns:.4f}",
            f"PNS: {pns:.4f}"
        ]
        for i, stat in enumerate(stats):
            self.oled.text(stat, 0, i * 9)

        self.oled.show()
        #time.sleep(7)






class Sensor:
    def __init__(self,option):
        #Input
        self.option = option
        self.freq = 250
        self.adc = ADC(26)
        self.data = Fifo(500)
        self.oled = OLED()
        self.led = Led(21, Pin.OUT, 0.5)
        self.running = True

    def read_sample(self, tid):
        self.data.put(self.adc.read_u16())
    
    def reset(self):
        self.samples = []
        self.MAX_SAMPLES = 250  # Maximum 250 samples in samples array
        self.min_interval = self.freq * 0.3  # Maximum heart rate 240 BPM => max PPI 250 ms => min sample interval = 0.25 * freq (62.5 samples)
        self.max_interval = self.freq * 2  # Minimum heart rate 30 BPM => min PPI 2000 ms => max sample interval = 2 * freq (500 samples)
        self.rise = False
        self.ris_edges = [0]
        self.hr_arr = []
        self.PPI_arr = []
        self.index = 0
        self.bad_signal_count = 0
        self.last_hr = None
        self.hr_5s = []
        #PIOTimer
        self.timer = Piotimer(mode=Piotimer.PERIODIC, freq=self.freq, callback=self.read_sample)

        #Time tracker
        self.start_time = time.time()
        self.last_hr_time = self.start_time  # Track the last time heart rate was printed
        self.last_time = self.start_time  # Track the last time time was printed
    
    def calculate_hr(self, interval):
        return int(60 / (interval / self.freq))

    def detect_hr(self, val, threshold_on, threshold_off):
        interval = self.index - self.ris_edges[-1] # Calculate how many samples between current val and last detected rising edge
        
        if not self.rise and val > threshold_on and self.min_interval <= interval <= self.max_interval: #detect edge within acceptable range
            self.rise = True
            self.ris_edges.append(self.index)
            self.led.on()
            
            if len(self.ris_edges) > 2: #Detect at least 2 rising edge
                hr = self.calculate_hr(interval)
#                 if self.last_hr is None:
#                     self.last_hr = hr
#                 elif abs(self.last_hr)-hr < 20:
                self.hr_arr.append(hr)
                self.hr_5s.append(hr)
                self.PPI_arr.append(interval*4)
#                     self.last_hr = hr
                return hr#self.last_hr
                    
        elif self.rise and val < threshold_off:
            self.rise = False
            self.led.off()
    
    def hr_update(self):
        current_time = time.time() # Get the current time and the elapsed time since the start
        elapsed_time = current_time - self.start_time
        
        if current_time - self.last_time >= 1:
            print(f"Time: {int(elapsed_time)}s") # Print the time every second starting from 0
            self.oled.display_time(elapsed_time)
            self.last_time = current_time
            
        if current_time - self.last_hr_time >= 5:# If 5 seconds have elapsed, print the heart rate or "Bad signal"
            # Display heart rate on OLED
            if 2 < len(self.hr_5s) and abs(self.hr_5s[0]-self.hr_5s[-1]) < 30: #check heart rate detected in acceptable range and first and last hr is within 30bpm
                update = int(sum(self.hr_5s)/len(self.hr_5s))
                update1 = self.calculate_mean_hr()
                self.bad_signal_count = 0 # reset signal count cause only if 3 consecutive bad signal => stop
                self.oled.display_heart_rate(update1)
                print(f"{update} BPM")
            else:    
                self.bad_signal_count += 1
                if self.bad_signal_count > 2: #3 consecutive bad signal => stop
                    self.stop()
                    print("Bad signal")
                    self.oled.display_message("Bad Signal")
                        
            self.hr_5s = []        
            
            self.last_hr_time = current_time
            
    def run(self):
        while self.data.has_data():
            val = self.data.get()
            # Display raw data on OLED
            self.index += 1
            if self.index % 20 == 0:
                self.oled.display_val(val)
                    
            self.samples.append(val)    
            self.samples = self.samples[-self.MAX_SAMPLES:]  # Keep most recent 250 samples for dynamic threshold
            if len(self.samples) > 1:
                min_val, max_val = min(self.samples), max(self.samples)
                if 2000 < max_val - min_val< 40000: #filter too small or to big diff bw max min
                    threshold_on = (min_val + max_val * 3) // 4  # Higher threshold to detect rising
                    threshold_off = (min_val + max_val) // 2  # Lower threshold to stop detecting new edge (eliminate lower rising edges)
                    hr = self.detect_hr(val, threshold_on, threshold_off)
            self.hr_update() # Check if need to print the heart rate after 5s
            self.stop_check()
    
    def start(self):
        self.reset()        
        while self.running:
          self.run()  
        return
                
    def start_op2(self):
        self.reset()
        self.pass_time = 0
        
        # Main loop to handle the timer and check if 30 seconds have elapsed
        while self.pass_time < 30 and self.running:
            self.pass_time = time.time() - self.start_time
            self.run()
            
        # After 30 seconds, stop data collection and display statistics
        self.timer.deinit()
        if len(self.hr_arr) > 2 and self.pass_time == 30:
            mean_hr = self.calculate_mean_hr()
            mean_ppi = self.calculate_mean_ppi()
            rmssd = self.calculate_rmssd()
            sdnn = self.calculate_sdnn()
            
            print("Mean HR:", mean_hr)
            print("Mean PPI:", mean_ppi)
            print("RMSSD:", rmssd)
            print("SDNN:", sdnn)
            
            # Connect to MQTT broker
            try:
                self.option.menu.network.connect_mqtt()
            except Exception as e:
                print(f"Failed to connect to MQTT: {e}")
        
            # Send MQTT messages periodically
            topic = "HRV"
            message = {
                "mean_hr": mean_hr,
                "mean_ppi": mean_ppi,
                "rmssd": rmssd,
                "sdnn": sdnn
                }
            json_message = ujson.dumps(message)
            self.option.menu.network.send_mqtt_message(topic, json_message)
            
            # Display HRV 
            self.oled.display_stats(mean_hr, mean_ppi, rmssd, sdnn)
            #time.sleep(3)
        self.stop()
        return
    
    def start_op3(self):
        self.reset()
        self.pass_time = 0
        
        # Main loop to handle the timer and check if 30 seconds have elapsed
        while self.pass_time < 30 and self.running:
            self.pass_time = time.time() - self.start_time
            self.run()
            
            
        # After 30 seconds, stop data collection and display statistics
        self.timer.deinit()
        if len(self.PPI_arr) > 5 and self.pass_time == 30:
            self.oled.display_message("Sending.....")
            self.option.kubios.authenticate()
            response = self.option.kubios.send_data_to_kubios(self.PPI_arr)
            #print(response)
            # Check if response is valid
            if not response == {'status': 'error', 'error': 'Error validating against schema'}:
            # Extract the specific values from the response dictionary
                mean_hr_bpm = response['analysis']['mean_hr_bpm']
                mean_ppi_ms = response['analysis']['mean_rr_ms']
                rmssd_ms = response['analysis']['rmssd_ms']
                sdnn_ms = response['analysis']['sdnn_ms']
                sns_index = response['analysis']['sns_index']
                pns_index = response['analysis']['pns_index']
                timestamp = response['analysis']['create_timestamp']
                
                 
                # Split the timestamp at 'T' to separate date and time
                data_date, data_time = timestamp.split('T')

                # Further process time_part to remove the timezone information
                data_time = data_time.split('+')[0]  # Remove timezone information
                
                timestamp = data_date + " " + data_time
                
                # Store data from Kubios to history arr
                self.option.menu.history.append((timestamp, mean_hr_bpm, mean_ppi_ms, rmssd_ms, sdnn_ms, sns_index, pns_index))
                self.option.menu.history = self.option.menu.history[-4:] #only keep 4 nearest measurement
                
                # Print analysis
                print(f"Time: {timestamp}")
                print(f"Mean HR: {mean_hr_bpm:.0f}")
                print(f"Mean PPI: {mean_ppi_ms:.0f}")
                print(f"RMSSD: {rmssd_ms:.0f}")
                print(f"SDNN: {sdnn_ms:.0f}")
                print(f"SNS: {sns_index:.0f}")
                print(f"PNS: {pns_index:.0f}")
                self.oled.display_kubios(timestamp, mean_hr_bpm, mean_ppi_ms, rmssd_ms, sdnn_ms, sns_index, pns_index)

            else:
                self.oled.display_message("Error!")
        else:
            print("Error")
            self.oled.display_message("Error!")
        self.stop()
        return
            
    def calculate_mean_hr(self):
        if len(self.hr_arr) > 2:
            return round(sum(self.hr_arr) / len(self.hr_arr))
        else:
            return None

    def calculate_mean_ppi(self):
        return round(sum(self.PPI_arr) / len(self.PPI_arr))
    
    def calculate_rmssd(self):
        successive_differences = [self.PPI_arr[i] - self.PPI_arr[i - 1] for i in range(1, len(self.PPI_arr))]# Calculate the successive differences in PPI
        squared_differences = [diff ** 2 for diff in successive_differences]# Calculate the square of the differences
        mean_squared_diff = sum(squared_differences) / len(squared_differences)# Calculate the mean of the squared differences
        return math.sqrt(mean_squared_diff)
    
    def calculate_sdnn(self):
        mean_ppi = self.calculate_mean_ppi() # Calculate the mean of the PPI array
        variance = sum([(ppi - mean_ppi) ** 2 for ppi in self.PPI_arr]) / len(self.PPI_arr) # Calculate the variance of the PPI array
        return math.sqrt(variance)

    def stop_check(self):
        while self.option.menu.encoder.fifo.has_data():
            if self.option.menu.encoder.fifo.get() == 5:
                self.stop()
    
    def stop(self):
        self.led.off()
        self.timer.deinit()
        self.running = False
        self.option.running = False

    



class Option1:
    def __init__(self, menu):
        self.menu = menu
        self.oled = self.menu.oled
        self.encoder = self.menu.encoder
        self.sensor = Sensor(self)
        self.running = True
        
    def start(self):
        self.oled.display_message("Press to Start")
        while self.running: 
            while self.encoder.fifo.has_data():
                if self.encoder.fifo.get() == 5:
                    self.sensor.start()
        return

class Option2:
    def __init__(self, menu):
        self.menu = menu
        self.oled = self.menu.oled
        #self.encoder = self.menu.encoder
        self.sensor = Sensor(self)
        self.running = True
        
    def start(self):
        self.oled.display_message("Measuring....")
        time.sleep(1)
        while self.running: 
#             while self.encoder.fifo.has_data():
#                 if self.encoder.fifo.get() == 5:
            self.sensor.start_op2()
        return
                    
class Option3:
    def __init__(self, menu):
        self.menu = menu
        self.oled = self.menu.oled
        #self.encoder = self.menu.encoder
        self.sensor = Sensor(self)
        self.kubios = Kubios()
        self.running = True
        
    def start(self):
        self.oled.display_message("Collecting....")
        time.sleep(1)
        while self.running: 
            #while self.encoder.fifo.has_data():
                #if self.encoder.fifo.get() == 5:
            self.sensor.start_op3()
        return

class Kubios:
    def __init__(self):
        self.api_key = "pbZRUi49X48I56oL1Lq8y8NDjq6rPfzX3AQeNo3a" 
        self.client_id = "3pjgjdmamlj759te85icf0lucv"
        self.client_secret = "111fqsli1eo7mejcrlffbklvftcnfl4keoadrdv1o45vt9pndlef"
        self.login_url = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/login"
        self.token_url = "https://kubioscloud.auth.eu-west-1.amazoncognito.com/oauth2/token"
        self.redirect_uri = "https://analysis.kubioscloud.com/v1/portal/login"
        self.access_token = None
    
    def authenticate(self):
        print("Authenticating with Kubios Cloud")
        response = requests.post(
            url=self.token_url,
            data=f'grant_type=client_credentials&client_id={self.client_id}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            auth=(self.client_id, self.client_secret)
        )
        response_data = response.json()  # parse JSON response into dictionary
        self.access_token = response_data.get("access_token")  # parse access token
        
    
    def send_data_to_kubios(self, data):
        print(f"Sending data to Kubios Cloud: {data}")
        # Create the dataset dictionary from data array
        dataset = {
            "type": "RRI",
            "data": data,
            "analysis": {"type": "readiness"}
            }

        # Make the readiness analysis with the given data
        response = requests.post(
            url="https://analysis.kubioscloud.com/v2/analytics/analyze",
            headers={
                "Authorization": f"Bearer {self.access_token}",  # Use access token to access your Kubios Cloud analysis session
                "X-Api-Key": self.api_key
            },
            json=dataset  # dataset will be automatically converted to JSON by the urequests library
        )

        response_data = response.json()  # Parse the JSON response
        
        return response_data
    
class Option4:
    def __init__(self, menu):
        self.menu = menu
        self.oled = self.menu.oled
        self.history = self.menu.history
        self.encoder = self.menu.encoder
        self.running = True
        self.lines = ["MEASUREMENT 1", "MEASUREMENT 2", "MEASUREMENT 3", "MEASUREMENT 4"] 
        self.left_arrow = "<"
        self.right_arrow = ">"
        self.arrow_pos = 0 #arrow position
        self.is_history_menu = True  # flag to track whether the main menu is being displayed
        self.size = 8
    
    def display(self):
        self.oled.display_menu(self.lines, self.arrow_pos, self.left_arrow, self.right_arrow)
        
    def start(self):
        while self.running:
            if self.is_history_menu:
                self.display()
                while self.encoder.fifo.has_data():
                    v = self.encoder.fifo.get()
                    if not v == 5:
                        direction = v
                        self.arrow_pos = min(max(self.arrow_pos + (direction * self.size * 2), 0), self.size * 6)  # Adjust arrow position
                    elif v == 5:
                         self.select_option()
        
    def display_empty(self):
        self.oled.oled.fill(1)
        self.oled.oled.text("No data", 35, 32,0)
        self.oled.oled.show()
        time.sleep(1)
        
    def select_option(self):
        # Perform an action based on the current arrow position
        option_index = self.arrow_pos // (self.size * 2)
        if option_index == 0: #Measurement 1
            if len(self.history) > 0:
                self.oled.display_kubios(self.history[0][0],self.history[0][1],self.history[0][2],self.history[0][3],self.history[0][4],self.history[0][5],self.history[0][6])
            else:
                self.display_empty()
            #return
        elif option_index == 1: #Measurement 2
            if len(self.history) > 1:
                self.oled.display_kubios(self.history[1][0],self.history[1][1],self.history[1][2],self.history[1][3],self.history[1][4],self.history[1][5],self.history[1][6])
            else:
                self.display_empty()
            #return
        elif option_index == 2: #Measurement 3
            if len(self.history) > 2:
                self.oled.display_kubios(self.history[2][0],self.history[2][1],self.history[2][2],self.history[2][3],self.history[2][4],self.history[2][5],self.history[2][6])
            else:
                self.display_empty()
            #return
        elif option_index == 3:
            if len(self.history) > 3:
                self.oled.display_kubios(self.history[3][0],self.history[3][1],self.history[3][2],self.history[3][3],self.history[3][4],self.history[3][5],self.history[3][6])
            else:
                self.display_empty()
        # Set is_main_menu flag to False since a specific option page is being displayed
        self.is_history_menu = False
        self.running = False

class Menu:
    def __init__(self):
        self.oled = OLED()
        self.encoder = Encoder()
        self.network = Network()
        self.network.connect_to_wlan()
#         self.mqtt_client = self.network.connect_mqtt()
        self.lines = ["1.MEASURE HR", "2.BASIC HRV", "3.KUBIOS", "4.HISTORY"] 
        self.left_arrow = "<"
        self.right_arrow = ">"
        self.arrow_pos = 0 #arrow position
        self.is_main_menu = True  # flag to track whether the main menu is being displayed
        self.size = 8
        self.history = []
        
    def display(self):
        self.oled.display_menu(self.lines, self.arrow_pos, self.left_arrow, self.right_arrow)
        
    def run(self):
        while True:
            if self.is_main_menu:
                self.display()
                while self.encoder.fifo.has_data():
                    v = self.encoder.fifo.get()
                    if not v == 5:
                        direction = v
                        self.arrow_pos = min(max(self.arrow_pos + (direction * self.size * 2), 0), self.size * 6)  # Adjust arrow position
                    elif v == 5:
                         self.select_option()
            else:
                # Clear the encoder input when not in main menu
                while self.encoder.fifo.has_data():
                    if self.encoder.fifo.get() == 5:
                        self.is_main_menu = True
    
    def select_option(self):
        # Perform an action based on the current arrow position
        option_index = self.arrow_pos // (self.size * 2)
        if option_index == 0:
            # "MEASURE HR"
            Option1(self).start()
            #return
        elif option_index == 1:
            # "BASIC HRV"
            Option2(self).start()
            #return
        elif option_index == 2:
            # "KUBIOS"
            Option3(self).start()
            #return
        elif option_index == 3:
            # "HISTORY"
            Option4(self).start()
            #return
        # Set is_main_menu flag to False since a specific option page is being displayed
        self.is_main_menu = False



    
menu = Menu()
menu.run()