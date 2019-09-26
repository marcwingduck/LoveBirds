# initial version by Louis Ros
#!/usr/bin/env python3.5

import os
import sys
import time
import signal
import asyncio
import subprocess
import RPi.GPIO as GPIO
from telethon import TelegramClient, events, sync


recent_interaction = False  # auto play messages after interaction
autoplay_timeout = 0        # timeout (in 0.5 seconds)
is_recording = False        # flag if recording is taking place
rec_duration = 0            # duration of latest recording (in 0.5 seconds)
messages_to_play = -1       # number of voice messages waiting
allow_all_users = True      # allow users other than your peer to send messages

GPIO.setmode(GPIO.BCM)

rec_btn_pin = 23   # sound card button
rec_led_pin = 25   # sound card led (mic+)
play_led_pin = 22  # extra notification led
servo_pin = 17     # extra servo motor signal

GPIO.setup(rec_btn_pin, GPIO.IN)
GPIO.setup(rec_led_pin, GPIO.OUT)
GPIO.setup(play_led_pin, GPIO.OUT)
GPIO.setup(servo_pin, GPIO.OUT)


async def time_update():
    """
    update timers.
    counts half-seconds of current recording (basically counts the time the button is pressed).
    counts down a timer (also in half-seconds) when the last interaction (button-press) took place.
    """
    global recent_interaction
    global autoplay_timeout
    global rec_duration
    global is_recording

    while True:
        await asyncio.sleep(0.5)
        if is_recording:
            rec_duration += 1
        if recent_interaction:
            autoplay_timeout -= 1
            if autoplay_timeout == 0:
                recent_interaction = False


async def rec_msg():
    """
    record and send a voice message
    initial button-press triggers subprocess that records voice message until the button is released.
    convert to .oga using opusenc and send via telegram client.
    """
    global rec_duration
    global recent_interaction
    global autoplay_timeout
    global is_recording

    rec_led = GPIO.PWM(rec_led_pin, 100)
    rec_led.start(0)

    while True:
        await asyncio.sleep(0.2)
        if GPIO.input(rec_btn_pin) == GPIO.LOW:  # button got pressed

            # prepare recording
            rec_led.ChangeDutyCycle(100)  # turns on the recording led
            is_recording = True
            rec_duration = 0  # init duration counter

            # record until button is released
            cmd = '/usr/bin/arecord --rate=44000 /home/pi/recordings/rec.wav'
            proc = await asyncio.create_subprocess_shell(cmd)
            while GPIO.input(rec_btn_pin) == GPIO.LOW:
                await asyncio.sleep(0.2)  # wait until button is released

            # button got released
            proc.send_signal(signal.SIGHUP)  # hang up subprocess
            await proc.wait()                # wait for it to finish

            # end recording
            rec_led.ChangeDutyCycle(0)  # turn off led
            is_recording = False
            recent_interaction = True  # triggers playing queued messages
            autoplay_timeout = 40  # 20 seconds from now incoming recordings will be auto-played

            # convert to .oga
            if rec_duration > 1:
                conv_cmd = '/usr/bin/opusenc /home/pi/recordings/rec.wav /home/pi/recordings/rec.oga'
                conv_proc = await asyncio.create_subprocess_shell(conv_cmd)
                await conv_proc.wait()
                await client.send_file(peer, '/home/pi/recordings/rec.oga', caption='', allow_cache=False, voice_note=True)
        else:
            rec_led.ChangeDutyCycle(0)


async def play_msg():
    """
    play arrived messages (if any) after recent_interaction was set to True.
    this happens in rec_msg function because it interacts with the recording button...
    """
    global messages_to_play
    global recent_interaction
    global autoplay_timeout

    playing = 0

    while True:
        if recent_interaction and messages_to_play >= 0:
            while playing <= messages_to_play:
                proc = await asyncio.create_subprocess_shell('/usr/bin/cvlc --play-and-exit /home/pi/recordings/play' + str(playing) + '.ogg')
                await proc.wait()
                playing += 1
                if playing <= messages_to_play:
                    await asyncio.sleep(1)
            playing = 0
            messages_to_play = -1
            recent_interaction = True  # prolong recent interaction
            autoplay_timeout = 40
        await asyncio.sleep(0.2)


async def spin_servo():
    """
    servo task.
    spins the attached servo once a new message has arrived.
    """
    # init, move to center and disable
    servo = GPIO.PWM(servo_pin, 50)
    servo.start(7.5)
    await asyncio.sleep(0.2)
    servo.ChangeDutyCycle(0)

    prev_messages_to_play = -1

    while True:
        await asyncio.sleep(0.2)
        if messages_to_play > prev_messages_to_play:
            for dc in range(750, 600, -10):
                servo.ChangeDutyCycle(dc / 100.)
                await asyncio.sleep(0.02)
            for dc in range(600, 900, 10):
                servo.ChangeDutyCycle(dc / 100.)
                await asyncio.sleep(0.02)
            for _ in range(2):
                for dc in range(900, 800, -10):
                    servo.ChangeDutyCycle(dc / 100.)
                    await asyncio.sleep(0.01)
                for dc in range(800, 900, 10):
                    servo.ChangeDutyCycle(dc / 100.)
                    await asyncio.sleep(0.01)
            for dc in range(900, 750, -10):
                servo.ChangeDutyCycle(dc / 100.)
                await asyncio.sleep(0.01)
            servo.ChangeDutyCycle(0)  # detach again
        prev_messages_to_play = messages_to_play


async def blink_led():
    """
    led notification if there are new messages.
    """
    play_led = GPIO.PWM(play_led_pin, 100)
    play_led.start(0)

    while True:
        if messages_to_play >= 0:
            for dc in range(0, 20, 2):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            for dc in range(20, -1, -2):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.05)

            for dc in range(0, 101, 2):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            for dc in range(100, -1, -2):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.06)

            for dc in range(0, 8, 2):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            for dc in range(7, -1, -1):
                play_led.ChangeDutyCycle(dc)
                await asyncio.sleep(0.01)
            await asyncio.sleep(1)
        else:
            play_led.ChangeDutyCycle(0)
            await asyncio.sleep(0.1)


"""
initialization of the application and user for telegram
init of the name of the correspondant with the file /boot/PEER.txt
declaration of the handler for the messages arrival
filtering of message coming from the correspondant
download of file .oga renamed .ogg

"""
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
    print(phone)
    os.remove('/home/pi/phone')

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

peer_file = open('/boot/PEER.txt', 'r')
peer = peer_file.readline().strip()
if not peer:
    print('no peer provided.')
    sys.exit(1)

# create temporary directory for voice messages
if not os.path.exists('/home/pi/recordings'):
    os.mkdir('/home/pi/recordings')


@client.on(events.NewMessage)
async def receive_msg(event):
    """
    new message event handler.
    """
    global messages_to_play

    # print(event.stringify())
    from_name = '@' + event.sender.username

    if event.media.document.mime_type == 'audio/ogg':
        if peer == from_name or allow_all_users:
            message = await client.download_media(event.media)
            messages_to_play += 1
            if not recent_interaction and messages_to_play >= 0:
                cmd = '/usr/bin/cvlc --play-and-exit /home/pi/LB/lovebird.wav'
                proc = await asyncio.create_subprocess_shell(cmd)
                await proc.wait()
            name = '/home/pi/recordings/play' + str(messages_to_play) + '.ogg'
            os.rename(message, name)
            await asyncio.sleep(0.2)


# main sequence (handler receive_msg), play_msg, auth_time_update, rec_msg, spin_motor and do_heartbeat are executed in parallel

subprocess.run(['/usr/bin/cvlc', '--play-and-exit', '/home/pi/LB/lovebird.wav'])

loop = asyncio.get_event_loop()

loop.create_task(rec_msg())
loop.create_task(play_msg())
loop.create_task(time_update())
loop.create_task(spin_servo())
loop.create_task(blink_led())

loop.run_forever()

client.run_until_disconnected()
