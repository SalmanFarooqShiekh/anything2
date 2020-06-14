#!/bin/bash

echo "> Before:"
ps -e | egrep "amazon.py"


kill $(ps -e | egrep -m 1 "amazon.py" | egrep -o "^\\d* ")


echo
echo "> After:"
ps -e | egrep "amazon.py"

