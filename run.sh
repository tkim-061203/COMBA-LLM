#! /bin/bash
# echo $@
nohup python run.py $@ > reports/lastRun/nohup.log 2>&1 &
echo $! > reports/lastRun/pid.txt