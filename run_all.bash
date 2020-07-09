#!/bin/bash
while true
do
{
    cd documents/luno/lima; python3 ./web.py;
} & {
    cd documents/luno/lima; python3 ./backend.py;
} & {	
    sleep 30m
    pkill -9 -f web.py
    pkill -9 -f backend.py
}
sleep 7
echo rebooting program
done