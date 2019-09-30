_forked from kheperV3/LoveBirds; added customization and fixed some stability issues, replaced browser-based setup by a python script_

1. Edit `/etc/wpa_supplicant/wpa_supplicant.conf` to gain access to your local Wi-Fi
2. Find out Pi's IP, then access via `ssh pi@XXX.XXX.X.XXX`
3. Configure by executing `python3 telechest/authorize.py`
4. Add to `/etc/rc.local`:

  ```
  sudo -H -u pi -i /usr/bin/python3 /home/pi/telechest/teletruhe.py &
  exit 0
  ```
