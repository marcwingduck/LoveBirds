#!/usr/bin/env python3

import time
import RPi.GPIO as GPIO


motor_pin = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(motor_pin, GPIO.OUT)

servo = GPIO.PWM(motor_pin, 50)
servo.start(0)

try:
    while True:
        for dc in range(750, 600, -10):
            servo.ChangeDutyCycle(dc / 100.)
            time.sleep(0.02)
        for dc in range(600, 900, 10):
            servo.ChangeDutyCycle(dc / 100.)
            time.sleep(0.02)
        for _ in range(2):
            for dc in range(900, 800, -10):
                servo.ChangeDutyCycle(dc / 100.)
                time.sleep(0.01)
            for dc in range(800, 900, 10):
                servo.ChangeDutyCycle(dc / 100.)
                time.sleep(0.01)
        for dc in range(900, 750, -10):
            servo.ChangeDutyCycle(dc / 100.)
            time.sleep(0.01)
        time.sleep(1)
except KeyboardInterrupt:
    pass

servo.ChangeDutyCycle(0)
time.sleep(1)
servo.stop()

GPIO.cleanup()
