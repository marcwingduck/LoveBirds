#!/usr/bin/env python3

import os
import sys
import time
import signal
import pigpio
import asyncio
import subprocess
from telethon import TelegramClient, events, sync


recent_interaction = False  # auto play messages after interaction
autoplay_timeout = 0        # timeout (in 0.5 seconds)
is_recording = False        # flag if recording is taking place
rec_duration = 0            # duration of latest recording (in 0.5 seconds)
messages_to_play = -1       # number of voice messages waiting
allow_others = True         # allow users other than your peer to send messages

rec_btn_pin = 23   # sound card button
rec_led_pin = 25   # sound card led (mic+)
play_led_pin = 22  # extra notification led
servo_pin = 17     # extra servo motor signal

io = pigpio.pi()

if not io.connected:
    print('pigpio not connected. $sudo pigpiod')
    sys.exit(0)

io.set_mode(rec_btn_pin, pigpio.INPUT)
io.set_mode(rec_led_pin, pigpio.OUTPUT)
io.set_mode(play_led_pin, pigpio.OUTPUT)
io.set_mode(servo_pin, pigpio.OUTPUT)


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

    io.set_PWM_dutycycle(rec_led_pin, 100)

    while True:
        await asyncio.sleep(0.2)
        if io.read(rec_btn_pin) == 0:  # button got pressed

            # prepare recording
            io.set_PWM_dutycycle(rec_led_pin, 100)  # turns on the recording led
            is_recording = True
            rec_duration = 0  # init duration counter

            # record until button is released
            cmd = '/usr/bin/arecord --rate=44000 /home/pi/recordings/rec.wav'
            proc = await asyncio.create_subprocess_shell(cmd)
            while io.read(rec_btn_pin) == 0:
                await asyncio.sleep(0.2)  # wait until button is released

            # button got released
            proc.send_signal(signal.SIGHUP)  # hang up subprocess
            await proc.wait()                # wait for it to finish

            # end recording
            io.set_PWM_dutycycle(rec_btn_pin, 0)  # turn off led
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
            io.set_PWM_dutycycle(rec_led_pin, 0)


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
                cmd = '/usr/bin/opusdec --force-wav --quiet recordings/play' + str(playing) + '.ogg - | /usr/bin/aplay'
                proc = await asyncio.create_subprocess_shell(cmd)
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
    io.set_servo_pulsewidth(servo_pin, 0)
    await asyncio.sleep(0.1)

    prev_messages_to_play = -1

    while True:
        if messages_to_play > prev_messages_to_play:
            for dc in range(1500, 1200, -10):
                io.set_servo_pulsewidth(servo_pin, dc)
                await asyncio.sleep(0.02)
            for dc in range(1200, 1800, 10):
                io.set_servo_pulsewidth(servo_pin, dc)
                await asyncio.sleep(0.02)
            for _ in range(2):
                for dc in range(1800, 1600, -10):
                    io.set_servo_pulsewidth(servo_pin, dc)
                    await asyncio.sleep(0.01)
                for dc in range(1600, 1800, 10):
                    io.set_servo_pulsewidth(servo_pin, dc)
                    await asyncio.sleep(0.01)
            for dc in range(1800, 1500, -10):
                io.set_servo_pulsewidth(servo_pin, dc)
                await asyncio.sleep(0.01)
            io.set_servo_pulsewidth(servo_pin, 0)
        prev_messages_to_play = messages_to_play
        await asyncio.sleep(0.5)


async def blink_led():
    """
    led notification if there are new messages.
    """
    io.set_PWM_dutycycle(play_led_pin, 0)

    while True:
        if messages_to_play >= 0:
            for dc in range(0, 20, 2):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.01)
            for dc in range(20, -1, -2):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.05)

            for dc in range(0, 101, 2):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.01)
            for dc in range(100, -1, -2):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.06)

            for dc in range(0, 8, 2):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.01)
            for dc in range(7, -1, -1):
                io.set_PWM_dutycycle(play_led_pin, dc)
                await asyncio.sleep(0.01)
            await asyncio.sleep(1)
        else:
            io.set_PWM_dutycycle(play_led_pin, 0)
        await asyncio.sleep(1)


def main():
    global peer
    global client
    global allow_others

    api_id = 1199490
    api_hash = '78fc29abd4ede127b2488e9e273cfb66'
    client = TelegramClient('love_session', api_id, api_hash)
    client.connect()

    if not client.is_user_authorized():
        print('not authorized to use telegram. please execute authorize.py!')
        sys.exit(0)

    peer_file = open('/home/pi/peer', 'r')
    peer = peer_file.readline().strip()
    if not peer:
        print('no peer provided.')
        sys.exit(1)

    if os.path.exists('/home/pi/allow_others'):
        allow_others = True

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
            if from_name == peer or allow_others:
                message = await client.download_media(event.media)
                messages_to_play += 1
                if not recent_interaction and messages_to_play >= 0:
                    cmd = '/usr/bin/aplay /home/pi/telechest/notification.wav'
                    proc = await asyncio.create_subprocess_shell(cmd)
                    await proc.wait()
                name = '/home/pi/recordings/play' + \
                    str(messages_to_play) + '.ogg'
                os.rename(message, name)
                await asyncio.sleep(0.2)

    subprocess.run(['/usr/bin/aplay', '/home/pi/telechest/notification.wav'])

    loop = asyncio.get_event_loop()

    loop.create_task(rec_msg())
    loop.create_task(play_msg())
    loop.create_task(time_update())
    loop.create_task(spin_servo())
    loop.create_task(blink_led())

    loop.run_forever()

    client.run_until_disconnected()


if __name__ == "__main__":
    main()
