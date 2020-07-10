#!/bin/bash
while true
do
{
    cd documents/luno/lima; python3 ./web.py;
} & {
    cd documents/luno/lima; python3 ./backend.py;
} & {	
    sleep 600
    pkill -9 -f web.py
    pkill -9 -f backend.py
}
sleep 10
echo rebooting program
done