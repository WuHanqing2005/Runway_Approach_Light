'''
接线说明：OLED(IIC)液晶模块-->ESP32 IO
         GND-->(GND)
         VCC-->(5V)
         SCL-->(27)
         SDA-->(22)
         按钮 --> GPIO14
'''

import urequests as requests
import time
import network
import socket
import json
import uQR
from machine import Pin, SoftI2C
from ssd1306 import SSD1306_I2C
import ntptime

# 初始化 OLED 屏幕
i2c = SoftI2C(sda=Pin(22), scl=Pin(27))
oled = SSD1306_I2C(128, 64, i2c)
oled.fill(0)
oled.show()

# 屏幕滚动间隔时间设为5s
SCROLL_TIME = 5

# 初始化复位引脚 (GPIO0连接EN引脚)
reset_pin = Pin(0, Pin.OUT, value=1)  # 初始化为高电平

# 初始化按钮引脚 (GPIO14)
button_pin = Pin(14, Pin.IN, Pin.PULL_DOWN)  # 使用内部下拉电阻

# 配置文件路径
CONFIG_FILE = "config.json"  # 配网信息
REQUEST_HEADERS_FILE = "REQUEST_HEADERS.json"  # 随机请求头信息

# 默认请求头
DEFAULT_REQUEST_HEADERS = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
]

# 默认配网信息
DEFAULT_CONFIG = {
    "WIFI_SSID": "",
    "WIFI_PASSWORD": "",
    "AIRPORT_CODE": "ZYTX"
}

# 配网热点配置
AP_SSID = 'METAR_Config'
AP_PASSWORD = '12345678'

# 全局变量存储最后一次成功获取的数据
LAST_GOOD_METAR = None
LAST_GOOD_TAF = None
LAST_FETCH_TIME = 0
LAST_REBOOT_TIME = 0
FETCH_INTERVAL = 60  # 1分钟更新一次数据

# 初始化RTC时间
def sync_ntp_time():
    try:
        ntptime.settime()
        return True
    except:
        return False

# 时间格式转换函数（使用NTP时间）
def format_time(timestamp):
    if timestamp <= 0:
        return "从未更新"
    tm = time.localtime(timestamp)
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        tm[0], tm[1], tm[2], tm[3], tm[4], tm[5])

# 检查按钮是否被按下
def check_button():
    return button_pin.value() == 1  # 按下时为高电平

# 加载配置
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # 合并默认配置和用户配置
            for key in DEFAULT_CONFIG:
                if key not in config:
                    config[key] = DEFAULT_CONFIG[key]
            return config
    except:
        return DEFAULT_CONFIG

# 保存配置
def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# 生成并显示二维码
def display_qr_code(url):
    oled.fill(0)
    oled.text("IP:192.168.4.1", 8, 0)
    oled.text(" Scan", 8, 25)
    oled.text("  to", 8, 35)
    oled.text("Config", 8, 45)
    oled.show()
    
    qr = uQR.QRCode()
    qr.add_data(url)
    matrix = qr.get_matrix()
    
    # 计算二维码显示位置(居中)
    qr_size = len(matrix) * 2
    x_offset = 64 - qr_size // 4 + 8
    y_offset = 5
    
    for row in range(len(matrix)):
        for col in range(len(matrix[0])):
            if matrix[row][col]:
                # 放大2倍显示
                oled.fill_rect(x_offset+col*2, y_offset+row*2, 2, 2, 1)
    oled.show()

# 启动配网模式
def start_config_mode():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASSWORD)
    
    # 配网页面HTML
    HTML = """<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>METAR Display Setup</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            background-color: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            font-size: 28px;
            margin-bottom: 25px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            font-size: 18px;
            margin-bottom: 8px;
            color: #2c3e50;
            font-weight: bold;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 5px;
            box-sizing: border-box;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            border-color: #3498db;
            outline: none;
        }
        input[type="submit"] {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 12px 25px;
            font-size: 18px;
            border-radius: 5px;
            cursor: pointer;
            width: 100%;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover {
            background-color: #2980b9;
        }
        .footer {
            margin-top: 30px;
            font-size: 14px;
            color: #7f8c8d;
            text-align: center;
            border-top: 1px solid #eee;
            padding-top: 20px;
        }
        .footer a {
            color: #3498db;
            text-decoration: none;
        }
        .footer a:hover {
            text-decoration: underline;
        }
        .author-info {
            margin-top: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
            font-size: 16px;
        }
        .author-info h3 {
            color: #2c3e50;
            margin-top: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>METAR Display Config</h1>
        
        <form action="/save" method="post">
            <div class="form-group">
                <label for="ssid">WiFi SSID:</label>
                <input type="text" id="ssid" name="ssid" placeholder="Enter your WiFi SSID">
            </div>
            
            <div class="form-group">
                <label for="password">WiFi Password:</label>
                <input type="password" id="password" name="password" placeholder="Enter your WiFi password">
            </div>
            
            <div class="form-group">
                <label for="airport">Airport Code (ICAO):</label>
                <input type="text" id="airport" name="airport" value="ZYTX" placeholder="e.g. ZYTX">
            </div>
            
            <input type="submit" value="Save Settings">
        </form>
        
        <div class="author-info">
            <h3>About This Project</h3>
            <p>This RUNWAY APPROACH LIGHT Project is developed by Wuhanqing, an aviation enthusiast.</p>
            <p>Welcome to check out my Bilibili channel: <a href="https://space.bilibili.com/492152575" target="_blank">@Daniel_Qinghan</a></p>
            <p>For more Projects and Updates, follow me on GitHub: <a href="https://github.com/WuHanqing2005" target="_blank">@WuHanqing2005</a></p>
            <p>You can also contact me with Wechat, my Wechat ID is <b>Daniel_Qinghan</b></p>
        </div>
    </div>
    
    <div class="footer">
        <p>METAR Display System &copy; 2023 | Designed by Wuhanqing</p>
    </div>
</body>
</html>"""
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', 80))
    s.listen(1)
    
    display_qr_code('http://192.168.4.1')
    
    while True:
        conn, addr = s.accept()
        request = conn.recv(1024).decode()
        
        if 'POST /save' in request:
            # 解析表单数据
            params = request.split('\r\n\r\n')[1].split('&')
            config = {
                "WIFI_SSID": params[0].split('=')[1],
                "WIFI_PASSWORD": params[1].split('=')[1],
                "AIRPORT_CODE": params[2].split('=')[1]
            }
            save_config(config)
            
            conn.send('HTTP/1.1 200 OK\n\n<h1>Settings Saved!</h1>')
            conn.close()
            
            # 显示获取到的配置信息
            print("Config Info Received!")
            print(f"WIFI_SSID: {config['WIFI_SSID']}")
            print(f"WIFI_PASSWORD: {config['WIFI_PASSWORD']}")
            print(f"AIRPORT_CODE: {config['AIRPORT_CODE']}")
            
            oled.fill(0)
            oled.text("Config Info List", 0, 5)
            oled.text("WIFI_SSID:", 0, 20)
            oled.text(config["WIFI_SSID"], 0, 30)
            oled.text("AIRPORT_CODE:", 0, 40)
            oled.text(config["AIRPORT_CODE"], 0, 50)
            oled.show()
            time.sleep(3)
            
            # 显示重启信息
            oled.fill(0)
            oled.text("Config Saved!", 12, 15)
            oled.text("Rebooting...", 16, 35)
            oled.show()
            time.sleep(1)
            
            hardware_reset()  # 复位
    
        else:
            conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + HTML)
            conn.close()

# 硬件复位
def hardware_reset():
    global LAST_REBOOT_TIME
    LAST_REBOOT_TIME = time.time()
    print(f"LAST_REBOOT_TIME = {LAST_REBOOT_TIME}")
    
    print("Initiating hardware reset...")
    reset_pin.value(0)    # 拉低EN引脚
    time.sleep_ms(10)     # 保持10ms低电平
    reset_pin.value(1)    # 释放EN引脚
    print("Hardware reset completed!")

# 连接到 WiFi
def connect_to_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    oled.fill(0)
    oled.text("WLAN Connecting", 0, 15)
    oled.text("SSID:", 0, 30)
    oled.text(str(ssid), 0, 40)
    oled.show()
    time.sleep(1)
    
    wlan.connect(ssid, password)
    
    for _ in range(10):  # 尝试10次，每次间隔1秒
        if wlan.isconnected():
            # 连接成功后同步NTP时间
            if sync_ntp_time():
                print("NTP时间同步成功")
            break
        time.sleep(1)
    
    if wlan.isconnected():        
        oled.fill(0)
        oled.text("WLAN Connected!", 0, 15)
        oled.text("SSID:", 0, 30)
        oled.text(str(ssid), 0, 40)
        oled.show()
        time.sleep(1)
        return True
    else:
        oled.fill(0)
        oled.text("Connect failed", 0, 10)
        oled.text("Enter config mode", 0, 30)
        oled.show()
        time.sleep(2)
        return False

# 加载请求头
def load_request_headers():
    import os
    try:
        # 首先检查文件是否存在
        if REQUEST_HEADERS_FILE not in os.listdir():
            print(f"Error: {REQUEST_HEADERS_FILE} not found in filesystem")
            return DEFAULT_REQUEST_HEADERS
            
        # 尝试读取文件
        with open(REQUEST_HEADERS_FILE, 'r') as f:
            headers = json.load(f)
            print("Successfully loaded headers from file")
            if not headers:
                print("File is empty, using default headers")
                return DEFAULT_REQUEST_HEADERS
            return headers
    except Exception as e:
        print(f"Error loading headers: {e}")
        return DEFAULT_REQUEST_HEADERS

# 获取随机请求头
def get_random_header():
    import random
    headers = load_request_headers()
    return random.choice(headers)

# 改进的获取天气数据函数
def get_weather_data(airport_code):
    global LAST_GOOD_METAR, LAST_GOOD_TAF, LAST_FETCH_TIME
    
    current_time = time.time()
    time_since_last = current_time - LAST_FETCH_TIME
    need_fetch = time_since_last > FETCH_INTERVAL or LAST_GOOD_METAR is None
    
    # 调试输出
    print("\n" + "="*60)
    print(f"更新时间检查: 当前时间={format_time(current_time)}")
    print(f"上次更新时间={format_time(LAST_FETCH_TIME)}")
    print(f"时间差={time_since_last:.1f}秒, 需要更新={'是' if need_fetch else '否'}")
    print("="*60 + "\n")
    
    if need_fetch:
        headers = get_random_header()
        print(f"[请求头] {headers}")
        
        try:
            # 获取METAR数据
            metar_url = f"https://aviationweather.gov/api/data/metar?ids={airport_code}&format=json"
            print(f"[METAR] 请求URL: {metar_url}")
            metar_response = requests.get(metar_url, headers=headers, timeout=10)

            if metar_response.status_code == 200:
                data = metar_response.json()
                if data and len(data) > 0:
                    raw_metar = data[0].get('rawOb', '')
                    if raw_metar.endswith(' '):
                        raw_metar = raw_metar.rstrip()
                    metar_data = "METAR " + raw_metar + "="
                    LAST_GOOD_METAR = metar_data
                    LAST_FETCH_TIME = current_time
                    print(f"[METAR] 更新成功: {metar_data}")
                else:
                    print("[METAR] 数据为空，使用缓存")
                    metar_data = LAST_GOOD_METAR
            else:
                print(f"[METAR] 请求失败，状态码: {metar_response.status_code}")
                metar_data = LAST_GOOD_METAR
        except Exception as e:
            print(f"[METAR] 请求异常: {e}")
            metar_data = LAST_GOOD_METAR
        
        try:
            # 获取TAF数据
            taf_url = f"https://aviationweather.gov/api/data/taf?ids={airport_code}&format=json"
            print(f"[TAF] 请求URL: {taf_url}")
            taf_response = requests.get(taf_url, headers=headers, timeout=10)

            if taf_response.status_code == 200:
                data = taf_response.json()
                if data and len(data) > 0:
                    raw_taf = data[0].get('rawTAF', '')
                    if raw_taf.endswith(' '):
                        raw_taf = raw_taf.rstrip()
                    taf_data = raw_taf + "="
                    LAST_GOOD_TAF = taf_data
                    LAST_FETCH_TIME = current_time
                    print(f"[TAF] 更新成功: {taf_data}")
                else:
                    print("[TAF] 数据为空，使用缓存")
                    taf_data = LAST_GOOD_TAF
            else:
                print(f"[TAF] 请求失败，状态码: {taf_response.status_code}")
                taf_data = LAST_GOOD_TAF
        except Exception as e:
            print(f"[TAF] 请求异常: {e}")
            taf_data = LAST_GOOD_TAF
        
        # 更新后再次打印时间信息
        print("\n" + "="*60)
        print(f"更新后时间检查: 当前时间={format_time(time.time())}")
        print(f"最后更新时间={format_time(LAST_FETCH_TIME)}")
        print("="*60 + "\n")
    else:
        print(f"[数据] 未达到更新间隔({FETCH_INTERVAL}秒)，使用缓存数据")
        metar_data = LAST_GOOD_METAR
        taf_data = LAST_GOOD_TAF
    
    return metar_data, taf_data

def process_weather_text(metar_text, taf_text):
    lines = []
    
    # 处理METAR报文
    if metar_text:
        metar_lines = []
        current_line = ""
        
        for word in metar_text.split(' '):
            if not current_line:
                current_line = word
            elif len(current_line) + 1 + len(word) <= 16:
                current_line += " " + word
            else:
                metar_lines.append(current_line)
                current_line = word
        
        if current_line:
            metar_lines.append(current_line)
        
        lines.extend(metar_lines)
    
    # 添加空行分隔METAR和TAF
    if metar_text and taf_text:
        lines.append("")  # 空行分隔
    
    # 处理TAF报文
    if taf_text:
        taf_lines = []
        current_line = ""
        
        for word in taf_text.split(' '):
            if not current_line:
                current_line = word
            elif len(current_line) + 1 + len(word) <= 16:
                current_line += " " + word
            else:
                taf_lines.append(current_line)
                current_line = word
        
        if current_line:
            taf_lines.append(current_line)
        
        lines.extend(taf_lines)
    
    return lines

def display_lines(lines, start_index):
    oled.fill(0)
    for i in range(7):  # 显示7行（最后一行半截）
        idx = start_index + i
        if idx < len(lines):
            y = i * 10 if i < 6 else 60
            oled.text(lines[idx], 0, y)
    oled.show()

# 欢迎动画
def show_welcome_animation():
    # 要显示的文本和预计算的起始x坐标
    lines = [
        ("WELCOME TO", 24),
        ("METAR DISPLAY", 12),
        ("BY WUHANQING", 16)
    ]
    
    # 清屏
    oled.fill(0)
    oled.show()
    time.sleep(0.5)
    
    # 逐行打字机效果显示
    for i, (text, x_pos) in enumerate(lines):
        y_pos = 15 + i * 15  # 每行垂直间隔15像素
        
        # 逐字符显示
        for j in range(len(text) + 1):
            oled.fill(0)
            # 显示已完成的上一行
            for k in range(i):
                prev_text, prev_x = lines[k]
                oled.text(prev_text, prev_x, 15 + k * 15)
            # 显示当前行的部分文本
            oled.text(text[:j], x_pos, y_pos)
            oled.show()
            time.sleep(0.02)  # 每个字符显示间隔
        
        time.sleep(0.2)  # 每行显示完成后的间隔
    
    # 最终停留2秒
    time.sleep(2)
    
    # 清屏过渡
    for i in range(0, 64, 2):
        oled.fill_rect(0, i, 128, 2, 0)
        oled.show()
        time.sleep(0.005)

# 主程序
if __name__ == "__main__":
    show_welcome_animation()  # 欢迎动画
    
    try:
        config = load_config()
    except Exception as e:
        print(e)
        oled.fill(0)
        oled.text("ERROR:", 0, 5)
        oled.text(str(e), 0, 15)
        oled.text("Please", 42, 30)
        oled.text("Reboot", 42, 40)
        oled.text("Later", 46, 50)
        oled.show()
        time.sleep(3)
        hardware_reset()
    
    try:
        # 如果没有配置或连接失败，进入配网模式
        if not config["WIFI_SSID"] or not connect_to_wifi(config["WIFI_SSID"], config["WIFI_PASSWORD"]):
            start_config_mode()
            
    except Exception as e:
        print(e)
        oled.fill(0)
        oled.text("ERROR:", 0, 5)
        oled.text(str(e), 0, 15)
        oled.show()
        time.sleep(3)
        hardware_reset()
        
    # 记录程序开始运行时间以便定时重启
    START_TIME = time.time()
    
    # 主循环
    while True:
        try:
            # 调试输出
            print("\n" + "="*60)
            print("当前时间状态")
            print(f"time.time() = {format_time(time.time())}")
            print(f"START_TIME = {format_time(START_TIME)}")
            print("="*60 + "\n")
            
            # 如果运行时间超过24小时则强制重启
            if time.time() - START_TIME >= 86400:
                oled.fill(0)
                oled.text("Run over 24h", 16, 10)
                oled.text("Schedule Reboot", 4, 25)
                oled.text(format_time(time.time()), 0, 40)
                oled.show()
                time.sleep(3)
                hardware_reset()
            
            # 检查按钮是否按下
            if check_button():
                oled.fill(0)
                oled.text("Button pressed", 10, 20)
                oled.text("Enter config...", 10, 35)
                oled.show()
                time.sleep(1)
                start_config_mode()
            
            # 获取天气数据(函数内部会处理缓存和更新逻辑)
            metar_data, taf_data = get_weather_data(config["AIRPORT_CODE"])
            
            # 处理并显示数据
            if metar_data or taf_data:
                lines = process_weather_text(metar_data, taf_data)
                
                if len(lines) > 6:
                    for start_idx in range(0, len(lines), 6):
                        display_lines(lines, start_idx)
                        time.sleep(SCROLL_TIME)
                        # 在滚动期间检查按钮
                        if check_button():
                            start_config_mode()
                else:
                    display_lines(lines, 0)
                    time.sleep(SCROLL_TIME * 2)
                    # 在显示期间检查按钮
                    if check_button():
                        start_config_mode()
            else:
                oled.fill(0)
                oled.text("No weather data", 0, 20)
                oled.text("Retrying...", 0, 35)
                oled.show()
                time.sleep(5)
                
        except Exception as e:
            print(f"主循环错误: {str(e)}")
            oled.fill(0)
            oled.text("System Error", 0, 20)
            oled.text("Recovering...", 0, 35)
            oled.show()
            time.sleep(5)
            # 不是立即复位，而是尝试继续运行

