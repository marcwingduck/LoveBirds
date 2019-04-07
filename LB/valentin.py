# credit to Louis Ros
# !/usr/bin/python3.5

import asyncio
import time
import os
import sys
import signal
from telethon import TelegramClient, events, sync
from telethon.tl.types import InputMessagesFilterVoice
import RPi.GPIO as GPIO
from gpiozero import Servo
from time import sleep

# global
heartbeat = False  # heartbeat effect on led
authorized = False  # authorization to play messages
rec_duration = 0  # duration of recording (in half second)
auth_timeout = 0  # timeout (in 0.5 seconds) of authorization
messages_to_play = -1  # number of voice mail waiting

# pins
rec_btn_pin = 23
rec_led_pin = 25  # led recording (mic+)
play_led_pin = 22  # led you have a voice mail
motor_pin = 17

# gpio
GPIO.setmode(GPIO.BCM)

GPIO.setup(rec_btn_pin, GPIO.IN)
GPIO.setup(play_led_pin, GPIO.OUT)
GPIO.setup(motor_pin, GPIO.OUT)

GPIO.setup(rec_led_pin, GPIO.OUT)
GPIO.output(rec_led_pin, GPIO.LOW)
rec_led = GPIO.PWM(rec_led_pin, 500)  # 500Hz


async def auth_time_update():
    """
    time management: duration of recording and timeout for autorization to play
    """
    global authorized
    global auth_timeout
    global rec_duration

    while True:
        await asyncio.sleep(0.5)
        rec_duration = rec_duration + 1
        if authorized:
            auth_timeout = auth_timeout - 1
            if auth_timeout <= 0:
                authorized = False


async def rec_msg():
    """
    Send a message 'voice'
    initialisation of gpio led and button
    when button is pushed: recording in a separate process
    that is killed when the button is released
    conversion to .oga by sox
    """
    global rec_duration
    global authorized
    global heartbeat
    global auth_timeout

    delay = 0.2
    while True:
        await asyncio.sleep(delay)
        if GPIO.input(rec_btn_pin) == GPIO.LOW:
            heartbeat = False
            rec_led.ChangeDutyCycle(100)  # turns ON the REC LED
            rec_duration = 0
            pid = os.fork()
            if pid == 0:
                os.execl('/usr/bin/arecord', 'arecord', '--rate=44000', '/home/pi/rec.wav', '')
            else:
                while GPIO.input(rec_btn_pin) == GPIO.LOW:
                    await asyncio.sleep(delay)
                os.kill(pid, signal.SIGHUP)
                heartbeat = False
                # GPIO.output(rec_led_pin, GPIO.LOW)
                rec_led.ChangeDutyCycle(0)  # turns OFF the REC LED
                authorized = True
                auth_timeout = 30
                if rec_duration > 1:
                    os.system('/usr/bin/opusenc /home/pi/rec.wav /home/pi/rec.oga')
                    await client.send_file(peer, '/home/pi/rec.oga', caption='', allow_cache=False, voice_note=True)
        else:
            # heartbeat = False
            # GPIO.output(rec_led_pin, GPIO.LOW)
            rec_led.ChangeDutyCycle(0)


# servo turns min/max/mid once a new message arrived
async def spin_motor():
    prev_messages_to_play = -1

    servo = Servo(motor_pin)  # todo adjust min/max pulse width
    servo.detach()

    while True:
        await asyncio.sleep(0.2)
        if messages_to_play > prev_messages_to_play:
            prev_messages_to_play = messages_to_play

            servo.min()
            await asyncio.sleep(1)
            servo.max()
            await asyncio.sleep(1)
            servo.mid()
            await asyncio.sleep(1)

            servo.detach()


# this is the les that mimic heartbeat when you have a voicemail waiting
async def do_heartbeat():
    global heartbeat

    rec_led.start(100)  # Start PWM output, Duty Cycle = 0
    while True:
        if heartbeat:
            for dc in range(0, 20, 2):  # Increase duty cycle: 0~100
                rec_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            for dc in range(20, -1, -2):  # Decrease duty cycle: 100~0
                rec_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.005)
            time.sleep(0.05)

            for dc in range(0, 101, 2):  # Increase duty cycle: 0~100
                rec_led.ChangeDutyCycle(dc)  # Change duty cycle
                await asyncio.sleep(0.01)
            for dc in range(100, -1, -2):  # Decrease duty cycle: 100~0
                rec_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)

            await asyncio.sleep(0.06)

            for dc in range(0, 8, 2):  # Increase duty cycle: 0~100
                rec_led.ChangeDutyCycle(dc)  # Change duty cycle
                await asyncio.sleep(0.01)
            for dc in range(7, -1, -1):  # Decrease duty cycle: 100~0
                rec_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            await asyncio.sleep(1)
        else:
            await asyncio.sleep(0.1)


async def play_msg():
    """
    when authorized to play (authorized == True)
    play one or several messages waiting (file .ogg) play_led_pin on
    message playing => playing
    last message waiting => messages_to_play
    """
    global messages_to_play
    global authorized
    global auth_timeout
    global heartbeat

    playing = 0
    while True:
        if messages_to_play >= 0:
            GPIO.output(play_led_pin, GPIO.HIGH)
            heartbeat = True
        else:
            GPIO.output(play_led_pin, GPIO.LOW)
            heartbeat = False

        if messages_to_play >= 0 and authorized:
            while playing <= messages_to_play:
                name = '/home/pi/play' + str(playing) + '.ogg'
                os.system('sudo killall vlc')
                pid = os.fork()
                if pid == 0:
                    os.execl('/usr/bin/cvlc', 'cvlc', name, '--play-and-exit')
                    # os.execl('/usr/bin/cvlc', 'cvlc',  name, ' vlc://quit')
                os.wait()
                playing = playing + 1
                if playing <= messages_to_play:
                    await asyncio.sleep(1)
            playing = 0
            messages_to_play = -1
            authorized = True
            auth_timeout = 30
        await asyncio.sleep(0.2)


"""
initialization of the application and user for telegram
init of the name of the correspondant with the file /boot/PEER.txt
declaration of the handler for the messages arrival
filtering of message coming from the correspondant
download of file .oga renamed .ogg

"""
GPIO.output(play_led_pin, GPIO.HIGH)
api_id = 592944
api_hash = 'ae06a0f0c3846d9d4e4a7065bede9407'
client = TelegramClient('session_name', api_id, api_hash)
asyncio.sleep(2)
client.connect()
if not client.is_user_authorized():
    while not os.path.exists('/home/pi/phone'):
        pass
    f = open('/home/pi/phone', 'r')
    phone = f.read()
    f.close()
    # os.remove('/home/pi/phone')
    print(phone)

    asyncio.sleep(2)
    client.send_code_request(phone, force_sms=True)

    while not os.path.exists('/home/pi/key'):
        pass
    f = open('/home/pi/key', 'r')
    key = f.read()
    f.close()
    print(key)
    os.remove('/home/pi/key')
    asyncio.sleep(2)
    me = client.sign_in(phone=phone, code=key)
GPIO.output(play_led_pin, GPIO.LOW)

peer_file = open('/boot/PEER.txt', 'r')
peer = peer_file.readline()
if peer[-1] == '\n':
    peer = peer[0:-1]


@client.on(events.NewMessage)
async def receive_msg(event):
    global messages_to_play

    # print(event.stringify())
    from_name = '@' + event.sender.username

    # only plays messages sent by your correpondant, if you want to play messages from everybody comment next line and uncomment the next next line
    if event.media.document.mime_type == 'audio/ogg' and peer == from_name:
        ad = await client.download_media(event.media)
        messages_to_play += 1
        if messages_to_play == 0:
            # os.system('/usr/bin/cvlc --play-and-exit /home/pi/LB/lovebird.wav')
            os.system('/usr/bin/cvlc --play-and-exit /home/pi/LB/lovebird.wav')
        name = '/home/pi/play' + str(messages_to_play) + '.ogg'
        os.rename(ad, name)
        await asyncio.sleep(0.2)
        # os.system('/usr/bin/cvlc --play-and-exit ' +  name)


# main sequence (handler receive_msg), play_msg, auth_time_update, rec_msg, spin_motor and do_heartbeat are executed in parallel

# os.system('/usr/bin/cvlc /home/pi/LB/lovebird.wav vlc://quit')
os.system('/usr/bin/cvlc --play-and-exit /home/pi/LB/lovebird.wav')

loop = asyncio.get_event_loop()

loop.create_task(rec_msg())
loop.create_task(play_msg())
loop.create_task(auth_time_update())
loop.create_task(spin_motor())
loop.create_task(do_heartbeat())

loop.run_forever()

client.run_until_disconnected()
