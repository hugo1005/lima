#!/bin/bash
while true
do
{
    cd /data/lima; python3 ./web.py;
} & {
    sleep 10
    cd /data/lima; python3 ./backend.py -e luno;
} & {
    sleep 40
    cd /data/lima; python3 ./luno_insta_arb.py
} & {	
    sleep 900
    pkill -9 -f web.py
    pkill -9 -f backend.py
}
sleep 10
echo rebooting program
done