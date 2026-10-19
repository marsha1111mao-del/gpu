#!/usr/bin/env python3
"""Capture RK3588 UART output through the Raspberry Pi lease owner."""
import importlib.util
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'resources', ROOT/'scripts/maintenance/lab-resources.py')
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


class PiUartCapture:
    def __init__(self, output, stop_path, seconds=600):
        self.output_path = Path(output)
        self.stop_path = stop_path
        self.seconds = seconds
        self.output = None
        self.reader = None

    def start(self):
        ssh, env = resources.ssh('pi')
        subprocess.run(ssh+['rm -f '+shlex.quote(self.stop_path)],
                       env=env, check=True)
        self.output = self.output_path.open('wb')
        code = ('import os,select,sys,time; from pathlib import Path\n'
                'fd=os.open("/dev/ttyUSB0",os.O_RDONLY|os.O_NONBLOCK)\n'
                f'end=time.monotonic()+{self.seconds}\n'
                f'while time.monotonic()<end and not Path({self.stop_path!r}).exists():\n'
                ' if select.select([fd],[],[],1)[0]:\n'
                '  data=os.read(fd,65536)\n'
                '  if data: sys.stdout.buffer.write(data);sys.stdout.buffer.flush()\n')
        self.reader = subprocess.Popen(
            ssh+['stty -F /dev/ttyUSB0 1500000 raw -echo && python3 -u -c '+
                 shlex.quote(code)],
            env=env, stdout=self.output, stderr=subprocess.DEVNULL)

    def stop(self):
        if self.reader is None:
            return
        ssh, env = resources.ssh('pi')
        try:
            subprocess.run(ssh+['touch '+shlex.quote(self.stop_path)],
                           env=env, timeout=12, check=True)
            self.reader.wait(timeout=8)
        finally:
            if self.reader.poll() is None:
                self.reader.terminate()
                self.reader.wait(timeout=8)
            subprocess.run(ssh+['rm -f '+shlex.quote(self.stop_path)],
                           env=env, timeout=12, check=True)
            self.output.close()
            self.reader = None
            self.output = None
