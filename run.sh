#! /bin/bash
nohup python run.py run --llm --nodebug modules/* > reports/lastRun/nohup.log 2>&1 &
echo $! > reports/lastRun/pid.txt