pip list
env
pwd
ls -alh
sns_va &
VA_PID=$(jobs -p)
echo PID of VA is $VA_PID
RESULT=$(python virtaccl/examples/Corrector.py)
jobs -l
kill -9 $VA_PID
sleep 1

exit $RESULT
