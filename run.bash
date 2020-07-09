#!/bin/bash

osascript -e 'tell app "Terminal"
	do script "cd documents/luno/lima; python3 ./web.py"
end tell'

osascript -e 'tell app "Terminal"
	do script "cd documents/luno/lima; python3 ./backend.py"
end tell'