#!/usr/bin/env python3
"""Resource guard regression: distinguish an own WSL pre-exec ps child."""
import pathlib
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import confirm_idle


class ResourceGuardChecks(unittest.TestCase):
    def observation(self, rows, load=5):
        results = [types.SimpleNamespace(stdout='PID PPID COMMAND COMMAND\n'+rows),
                   types.SimpleNamespace(stdout=str(load))]
        with patch.object(confirm_idle.os, 'getpid', return_value=13), \
             patch.object(confirm_idle.subprocess, 'run', side_effect=results):
            return confirm_idle.observe({1, 12, 13}, windows=True)

    def test_own_pre_exec_ps_child(self):
        result = self.observation('281 13 ps ps -eo pid,ppid,comm,args\n'
                                  '282 13 python3 ps -eo pid,ppid,comm,args\n')
        self.assertTrue(result['clear'])

    def test_other_python_not_exempt(self):
        for row in ('282 14 python3 ps -eo pid,ppid,comm,args\n',
                    '282 13 python3 python3 tools/remaining.py\n',
                    '282 14 python3 python3 train.py\n'):
            with self.subTest(row=row):
                self.assertFalse(self.observation(row)['clear'])

    def test_other_workload_and_queued_shell(self):
        for row in ('200 1 worksteal /other/worksteal\n',
                    '200 1 RayTracing /other/RayTracing\n',
                    '200 1 bash bash -lc python3 tools/remaining.py --round 22\n'):
            with self.subTest(row=row):
                self.assertFalse(self.observation(row)['clear'])

    def test_own_worksteal(self):
        self.assertTrue(self.observation('200 13 worksteal /build/worksteal\n')['clear'])

    def test_load_threshold(self):
        self.assertTrue(self.observation('', load=15)['clear'])
        self.assertFalse(self.observation('', load=16)['clear'])

    def test_failed_observation(self):
        with patch.object(confirm_idle.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ps', 10)):
            self.assertFalse(confirm_idle.observe({13})['clear'])


if __name__ == '__main__':
    unittest.main()
