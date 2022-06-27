# -*- coding: utf-8 -*-
# Copyright (c) 2020, Matgenix SRL, All rights reserved.
# Distributed open source for academic and non-profit users.
# Contact Matgenix for commercial usage.
# See LICENSE file for details.

"""Module containing the custodian jobs for SISSO."""

import subprocess

from custodian.custodian import Job  # type: ignore
from os.path import isfile, expanduser
from monty.os.path import which  # type: ignore


class SISSOJob(Job):
    """Custodian Job to run SISSO."""

    INPUT_FILE = "SISSO.in"
    TRAINING_DATA_DILE = "train.dat"

    def __init__(
        self,
        SISSO_exe: Union[str,None] = None,
        nprocs: int = 1,
        stdout_file: str = "SISSO.log",
        stderr_file: str = "SISSO.err",
    ):
        """Construct SISSOJob class.

        Args:
            SISSO_exe: Name of the SISSO executable.
            nprocs: Number of processors for the job.
            stdout_file: Name of the output file (default: SISSO.log).
            stderr_file: Name of the error file (default: SISSO.err).
        """
        self.SISSO_exe = SISSO_exe
        self.nprocs = nprocs
        self.stdout_file = stdout_file
        self.stderr_file = stderr_file

    def setup(self):  # pragma: no cover
        """Not needed for SISSO."""
        pass

    def run(self) -> subprocess.Popen:
        """Run SISSO.

        Returns:
            a Popen process.
        """
        exe = expanduser(self.SISSO_exe) if self.SISSO_exe else which("SISSO")
        if exe is None or not isfile(exe):
            raise ValueError(
                "SISSOJob requires path/to/a/SISSO executable to be provided\n"
                'or for "SISSO" to be in the path.\n'
                f'you provided "{=self.SISSO_exe}".\n'
                "Make sure the path includes the SISSO binary explicitly. Otherwise"
                "download the SISSO code at https://github.com/rouyang2017/SISSO "
                "and compile the executable and pass it's name."
                )
            )

        if (
            self.nprocs > 1
        ):  # pragma: no cover # Reason: obviously not yet implemented section of code.
            raise NotImplementedError("Running SISSO with MPI not yet implemented.")
        else:
            cmd = exe

        with open(self.stdout_file, "w") as f_stdout, open(
                self.stderr_file, "w", buffering=1) as f_stderr:
            p = subprocess.Popen(cmd, stdin=None, stdout=f_stdout, stderr=f_stderr)
        return p

    def postprocess(self):
        """Not needed for SISSO."""
