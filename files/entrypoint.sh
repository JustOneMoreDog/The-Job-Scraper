#!/bin/bash

/usr/sbin/apachectl
sudo -u hunter $(cd /app && /usr/bin/python3 /app/main.py)
