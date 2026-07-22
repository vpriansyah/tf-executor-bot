#!/bin/bash
export DISPLAY=:99
WID=$(xdotool search --onlyvisible --class "terminal64.exe" | head -n 1)
if [ -z "$WID" ]; then
    WID=$(xdotool search --onlyvisible --name "MetaTrader" | head -n 1)
fi
echo "Found MT5 window: $WID"
if [ -n "$WID" ]; then
    xdotool key --window "$WID" Alt+f
    sleep 1
    xdotool key --window "$WID" a
    sleep 2
    xdotool type --window "$WID" "Finex"
    sleep 1
    xdotool key --window "$WID" Return
    sleep 5
else
    xdotool key Alt+f
    sleep 1
    xdotool key a
    sleep 2
    xdotool type "Finex"
    sleep 1
    xdotool key Return
    sleep 5
fi
echo "Broker search completed."
