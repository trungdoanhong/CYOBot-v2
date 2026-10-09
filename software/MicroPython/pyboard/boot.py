import webrepl
webrepl.start()

import machine
machine.freq(240000000)

# check to see if there is main.py in SD card, if there is, overwrite the current file and restart
import os

try:
    os.stat("/sdcard/main.py")
    print("Found main.py, overwrite the main.py")
    
    # remove current main.py
    os.remove("main.py")
    
    with open('main.py', 'wt') as outfile:
        file = open('/sdcard/main.py', 'rt').read()
        outfile.write(file)
    
    # remove main.py in SD card
    os.remove("/sdcard/main.py")

except:
    print("No new file, continue")

# check to see if user wants to revert back to original main.py
import machine
import time

# check to see if button is pressed down
left = machine.Pin(4, machine.Pin.IN)
right = machine.Pin(38, machine.Pin.IN)

def _recovery_requested():
    # Recovery requires LEFT ONLY. A two-button hold belongs to servo test.
    if left.value() != 0 or right.value() == 0:
        return False
    from lib.display import LEDRing
    indicator = LEDRing()
    indicator.reset()
    started = time.ticks_ms()
    progress = -1
    while time.ticks_diff(time.ticks_ms(), started) < 3000:
        if left.value() != 0 or right.value() == 0:
            indicator.reset()
            return False
        step = min(11, time.ticks_diff(time.ticks_ms(), started) // 250)
        if step != progress:
            indicator.set_manual(step, (100, 0, 0))
            progress = step
        time.sleep_ms(20)
    return left.value() == 0 and right.value() != 0


if _recovery_requested():
    from lib.display import *
    from audio import player
    
    ring = LEDRing()
    matrix = Matrix()
    ring.reset()
    matrix.reset()
    prev_left = 1
    prev_right = 1
    progress = 0

    mPlayer = player(None)
    mPlayer.set_vol(100)

    mPlayer.play('file://sdcard/lib/data/reset-robot.wav')
    matrix.scroll("RESET", blue=100, speed=0.05)

    mPlayer.play('file://sdcard/lib/data/reset-guidance.wav')
    for i in range(4):
        ring.set_manual(9, (0, 0, 100))
        time.sleep_ms(200)
        ring.set_manual(9, (0, 0, 0))
        time.sleep_ms(200)
    ring.set_manual(9, (100, 0, 0))
    time.sleep_ms(600)
    for i in range(4):
        ring.set_manual(3, (0, 0, 100))
        time.sleep_ms(200)
        ring.set_manual(3, (0, 0, 0))
        time.sleep_ms(200)
    ring.set_manual(3, (100, 0, 0))
    
    # run reset_sequence
    mode = 0
    prev_left = left.value()
    mPlayer.play('file://sdcard/lib/data/portal.wav')
    matrix.scroll("PORTAL", green=100, speed=0.05)
    while right.value() == 1:
        if left.value() == 0 and prev_left == 1:
            mPlayer.play('file://sdcard/lib/data/button.wav')
            time.sleep_ms(200)
            mode = (mode + 1) % 2
            if mode == 0:
                mPlayer.play('file://sdcard/lib/data/portal.wav')
                matrix.scroll("PORTAL", green=100, speed=0.05)
            elif mode == 1:
                mPlayer.play('file://sdcard/lib/data/factory.wav')
                matrix.scroll("FACTORY", green=100, speed=0.05)
        
        prev_left = left.value()
        time.sleep(0.001)
    
    mPlayer.play('file://sdcard/lib/data/button.wav')

    if mode == 0:
        with open('/sdcard/main.py', 'wt') as outfile:
            file = open('main-server.py', 'rt').read()
            outfile.write(file)
        machine.reset()
    elif mode == 1:
        import json
        ## fix portal config file
        with open("/sdcard/config/portal-config.json") as file:
            content = json.loads(file.read())
        content["pythonWebREPL"]["endpoint"] = "ws://192.168.4.1:8266"
        content["onboarding"]["hasProvidedWifiCredentials"] = False
        
        with open("/sdcard/config/portal-config.json", "w") as outfile:
            outfile.write(json.dumps(content))
        
        ## fix brain config file
        with open("/sdcard/config/robot-config.json") as file:
            content = json.loads(file.read())
        content["wifi"]["ssid"] = ""
        content["wifi"]["password"] = ""
        with open("/sdcard/config/robot-config.json", "w") as outfile:
            outfile.write(json.dumps(content))
        
        try:
            os.stat("/sdcard/record.wav")
            os.remove("/sdcard/record.wav")

        except:
            print("No old records, continue")
        
        with open('/sdcard/main.py', 'wt') as outfile:
            file = open('main-server.py', 'rt').read()
            outfile.write(file)

        with open("state", "w") as file:
            file.write("0")
        
        machine.reset()
