#!/usr/bin/env python3

import os
from telethon import TelegramClient, events, sync


def main():
    api_id = 1199490
    api_hash = '78fc29abd4ede127b2488e9e273cfb66'
    client = TelegramClient('love_session', api_id, api_hash)
    client.connect()

    if not client.is_user_authorized():
        phone = input('please input your phone number (+XXxxx): ')
        client.send_code_request(phone, force_sms=True)
        key = input('please insert the key you have received: ')
        me = client.sign_in(phone=phone, code=key)

        peer = input('please insert your peer\'s telegram account name (@xxx): ')
        peer_file = open('/home/pi/peer', 'w')
        peer_file.write(peer.strip())
        peer_file.close()

        allow_others = ''
        while allow_others not in ['y', 'n']:
            allow_others = input('play messages from other users? (y/n): ')
        allow_others_file = open('/home/pi/allow_others', 'w')
        allow_others_file.write(allow_others)
        allow_others_file.close()
    else:
        print('already authorized.')


if __name__ == '__main__':
    main()
