pip list
env
pwd
ls -alh
sns_va &
VA_PID=$(jobs -p)
python virtaccl/examples/Corrector.py
jobs -l
kill $VA_PID
jobs -l