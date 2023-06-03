#!/usr/bin bash

virtualenv venv_ken
source venv_ken/bin/activate
pip install --upgrade pip
pip install pip-review
pip-review --auto
pip install numpy
pip install opencv-python
MACOSRETURN=$(system_profiler SPDisplaysDataType | grep Resolution)
RES=${MACOSRETURN#          Resolution: }
RES=${RES%Retina}
searchstring="x"
rest=${RES#*$searchstring}
SPLIT=$(( ${#RES} - ${#rest} - ${#searchstring} ))
XEND=$SPLIT-1
YSTART=$SPLIT+2
X=${RES:0:$XEND}
Y=${RES:$YSTART}
ARG=($X,$Y)
python core.py $ARG