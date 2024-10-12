from time import sleep

import pytest
import subprocess

from epics import caget


@pytest.fixture(scope="session")
def va_process():
    # Start VA as a background process
    proc = subprocess.Popen(["sns_va"])

    # Wait for the VA to start serving PVs
    sleep(4.0)
    print('VA should be ready by now')
    yield proc

    # Tear down: stop the background process when tests are done
    proc.terminate()
    proc.wait()


def test_pv_connection(va_process):

    assert va_process.poll() is None
    x = caget('SCL_Diag:BPM04:xAvg', connection_timeout=0.1)
    assert x is not None


def test_bad_pv(va_process):

    assert va_process.poll() is None
    x = caget('BAD:PV:Name', connection_timeout=0.1)
    assert x is None

