#!/usr/bin/env python3

import time
import RPi.GPIO as GPIO


play_led_pin = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(play_led_pin, GPIO.OUT)

play_led = GPIO.PWM(play_led_pin, 100)
play_led.start(0)

try:
    while True:
        for dc in range(0, 20, 2):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.01)
        for dc in range(20, -1, -2):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.005)
        time.sleep(0.05)

        for dc in range(0, 101, 2):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.01)
        for dc in range(100, -1, -2):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.01)
        time.sleep(0.06)

        for dc in range(0, 8, 2):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.01)
        for dc in range(7, -1, -1):
            play_led.ChangeDutyCycle(dc)
            time.sleep(0.01)
        time.sleep(1)
except KeyboardInterrupt:
    pass

play_led.ChangeDutyCycle(0)
time.sleep(1)
play_led.stop()

GPIO.cleanup()
