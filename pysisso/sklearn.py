# -*- coding: utf-8 -*-
# Copyright (c) 2020, Matgenix SRL, All rights reserved.
# Distributed open source for academic and non-profit users.
# Contact Matgenix for commercial usage.
# See LICENSE file for details.

"""Module containing a scikit-learn compliant interface to SISSO."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from custodian import Custodian  # type: ignore
from monty.os import cd, makedirs_p  # type: ignore
from sklearn.base import BaseEstimator, RegressorMixin  # type: ignore
from sklearn.preprocessing import FunctionTransformer

from pysisso.inputs import SISSODat, SISSOIn
from pysisso.jobs import SISSOJob
from pysisso.outputs import SISSOOut


def get_timestamp(tstamp: datetime|None = None) -> object:
    """Get a string representing the a time stamp.

    Args:
        tstamp: datetime.datetime object representing date and time. If set to None,
            the current time is taken.

    Returns:
        str: String representation of the time stamp.
    """
    tstamp = tstamp or datetime.now()
    return (
        f"{str(tstamp.year).zfill(4)}_{str(tstamp.month).zfill(2)}_"
        f"{str(tstamp.day).zfill(2)}_"
        f"{str(tstamp.hour).zfill(2)}_{str(tstamp.minute).zfill(2)}_"
        f"{str(tstamp.second).zfill(2)}_{str(tstamp.microsecond).zfill(6)}"
    )


class SISSORegressor(RegressorMixin, BaseEstimator):
    """SISSO regressor class compatible with scikit-learn."""

    def __init__(
        self,
        SISSOpath=None,
        ntask=1,
        task_weighting=1,
        desc_dim=2,
        restart=False,
        opset="(+)(-)",
        fcomplexity=5,
        dimclass=None,
        maxfval_lb=1e-3,
        maxfval_ub=1e5,
        subs_sis=20,
        method="L0",
        L1L0_size4L0=1,
        fit_intercept=True,
        metric="RMSE",
        nm_output=100,
        isconvex=None,
        width=None,
        nvf=None,
        vfsize=None,
        vf2sf=None,
        npf_must=None,
        L1_max_iter=None,
        L1_tole=None,
        L1_dens=None,
        L1_nlambda=None,
        L1_minrmse=None,
        L1_warm_start=None,
        L1_weighted=None,
        features_dimensions: dict|None = None,
        use_custodian: bool = True,
        custodian_job_kwargs: None|dict = None,
        custodian_kwargs: None|dict = None,
        run_dir: None|str = "SISSO_dir",
        clean_run_dir: bool = False,
    ):  # noqa: D417
        """Construct SISSORegressor object.

        For more information on running the SISSO code see
        https://github.com/rouyang2017/SISSO/blob/master/SISSO_Guide.pdf

        Args:
            use_custodian: Whether to use custodian (currently mandatory).
            custodian_job_kwargs: Keyword arguments for custodian job.
            custodian_kwargs: Keyword arguments for custodian.
            run_dir: Name of the directory where SISSO is run. If None, the directory
                will be set automatically. It then contains a timestamp and is unique.
            clean_run_dir: Whether to clean the run directory after SISSO has run.
        """
        self.SISSOpath = SISSOpath

        self.ntask = ntask
        self.task_weighting = task_weighting
        self.desc_dim = desc_dim
        self.restart = restart
        self.opset = opset
        self.fcomplexity = fcomplexity
        self.dimclass = dimclass
        self.maxfval_lb = maxfval_lb
        self.maxfval_ub = maxfval_ub
        self.subs_sis = subs_sis
        self.method = method
        self.L1L0_size4L0 = L1L0_size4L0  # pylint: disable=C0103
        self.fit_intercept = fit_intercept
        self.metric = metric
        self.nm_output = nm_output
        self.isconvex = isconvex
        self.width = width
        self.nvf = nvf
        self.vfsize = vfsize
        self.vf2sf = vf2sf
        self.npf_must = npf_must
        self.L1_max_iter = L1_max_iter  # pylint: disable=C0103
        self.L1_tole = L1_tole  # pylint: disable=C0103
        self.L1_dens = L1_dens  # pylint: disable=C0103
        self.L1_nlambda = L1_nlambda  # pylint: disable=C0103
        self.L1_minrmse = L1_minrmse  # pylint: disable=C0103
        self.L1_warm_start = L1_warm_start  # pylint: disable=C0103
        self.L1_weighted = L1_weighted  # pylint: disable=C0103
        self.features_dimensions = features_dimensions
        self.use_custodian = use_custodian
        self.custodian_job_kwargs = custodian_job_kwargs
        self.custodian_kwargs = custodian_kwargs
        self.run_dir = run_dir
        self.clean_run_dir = clean_run_dir

        if not self.use_custodian:
            raise NotImplementedError

    def fit(self, X, y, index=None, columns=None, tasks=None):
        """Fit a SISSO regression based on inputs X and output y.

        This method supports Multi-Task SISSO. For Single-Task SISSO, y must have a
        shape (n_samples) or (n_samples, 1).

        For Multi-Task SISSO, y must have a shape (n_samples, n_tasks) and can
        contain NaN values in order to represent incomplete samples. The arrays will
        be reshaped to fit SISSO's input files. NaNs will be automatically removed.

        For example, if 2 of 10 samples have NaN for the first task, 1 sample has Nan
        for the second task and 4 samples have Nan for the third task, the final
        output array (y) will have a shape (3*10-2-1-4, 1), i.e. (23, 1), while the
        final input array (X) will have a shape (23, n_features).

        Args:
            X: Feature vectors as an array-like of shape (n_samples, n_features).
            y: Target values as an array-like of shape (n_samples,)
                or (n_samples, n_tasks).
            index: List of string identifiers for each sample. If None, "sampleN"
                with N=[1, ..., n_samples] will be used.
            columns: List of string names of the features. If None, "featN"
                with N=[1, ..., n_features] will be used.
            tasks: When Multi-Task SISSO is used, this is the list of string names
                that will be used for each task/property. If None, "taskN"
                with N=[1, ..., n_tasks] will be used.

        """
        self.sisso_in = SISSOIn.from_sisso_keywords(  # pylint: disable=W0201
            ptype=1,
            ntask=self.ntask,
            task_weighting=self.task_weighting,
            desc_dim=self.desc_dim,
            restart=self.restart,
            rung=self.rung,
            opset=self.opset,
            fcomplexity=self.fcomplexity,
            dimclass=self.dimclass,
            maxfval_lb=self.maxfval_lb,
            maxfval_ub=self.maxfval_ub,
            subs_sis=self.subs_sis,
            method=self.method,
            L1L0_size4L0=self.L1L0_size4L0,
            fit_intercept=self.fit_intercept,
            metric=self.metric,
            nm_output=self.nm_output,
            isconvex=self.isconvex,
            width=self.width,
            nvf=self.nvf,
            vfsize=self.vfsize,
            vf2sf=self.vf2sf,
            npf_must=self.npf_must,
            L1_max_iter=self.L1_max_iter,
            L1_tole=self.L1_tole,
            L1_dens=self.L1_dens,
            L1_nlambda=self.L1_nlambda,
            L1_minrmse=self.L1_minrmse,
            L1_warm_start=self.L1_warm_start,
            L1_weighted=self.L1_weighted,
        )

        # Set up columns. These columns are used by the SISSO model wrapper afterwards
        # for the prediction
        if columns is None and isinstance(X, pd.DataFrame):
            columns = list(X.columns)
        self.columns = columns or [  # pylint: disable=W0201
            "feat{:d}".format(ifeat) for ifeat in range(1, X.shape[1] + 1)
        ]
        if len(self.columns) != X.shape[1]:
            raise ValueError("Columns should be of the size of the second axis of X.")

        if index is None and isinstance(X, pd.DataFrame):
            index = list(X.index)
        index = index or [
            "sample{:d}".format(ii) for ii in range(1, X.shape[0] + 1)
        ]

        if len(index) != len(y) or len(index) != len(X):
            raise ValueError("Index, X and y should have same size.")


        if y.ndim == 1 or (y.ndim == 2 and y.shape[1] == 1):  # Single-Task SISSO
            self.ntasks = 1  # pylint: disable=W0201
            X = np.array(X)
            X = pd.DataFrame(X, index = index, columns = self.columns)
            y = np.array(y)
            y = pd.Series(y, index = index)
            nsample = int(y.notna().sum(axis=0))

            data = X
            data.insert(0, "target", y)
            data.insert(0, "identifier", index)
        elif y.ndim == 2 and y.shape[1] > 1:  # Multi-Task SISSO
            self.ntasks = y.shape[1]  # pylint: disable=W0201
            tasks = tasks or ["task{:d}".format(ii) for ii in range(1, self.ntasks + 1)]
            X = np.array(X)
            X = pd.DataFrame(X, index = index, columns = self.columns)
            y = np.array(y)
            y = pd.DataFrame(y, index = index, columns = tasks)
            nsample = y.notna().sum(axis=0).to_list()

            y = y.stack(dropna=True)
            y.name = 'target'
            y.index.names = ('identifier', 'task')
            y = y.reset_index().set_index('identifier')
            data = y.join(X)
            data.insert(0, "identifier", data.index)
            data = data.sort_values('task')
            data = data.drop('task', axis=1)
        else:
            raise ValueError("Wrong shapes.")

        # Set up SISSODat and SISSOIn
        sisso_dat = SISSODat(
            data=data, features_dimensions=self.features_dimensions, nsample=nsample
        )
        self.sisso_in.set_keywords_for_SISSO_dat(sisso_dat=sisso_dat)

        # Run SISSO
        if self.run_dir is None:
            makedirs_p("SISSO_runs")
            timestamp = get_timestamp()
            self.run_dir = tempfile.mkdtemp(
                suffix=None, prefix=f"SISSO_dir_{timestamp}_", dir="SISSO_runs"
            )
        else:
            makedirs_p(self.run_dir)
        with cd(self.run_dir):
            self.sisso_in.to_file(filename="SISSO.in")
            sisso_dat.to_file(filename="train.dat")

            job = SISSOJob(SISSO_exe=self.SISSOpath)
            c = Custodian(jobs=[job], handlers=[], validators=[])
            c.run()

            self.sisso_out = SISSOOut.from_file()
            

        # Clean run directory
        if (
            self.clean_run_dir
        ):  # TODO: add check here to not remove "." if the user passes . ?
            shutil.rmtree(self.run_dir)

    def predict(self, X, index=None):
        """Predict output based on a fitted SISSO regression.

        Args:
            X: Feature vectors as an array-like of shape (n_samples, n_features).
            index: List of string identifiers for each sample. If None, "sampleN"
                with N=[1, ..., n_samples] will be used.
        """
        X = np.array(X)
        index = index or ["item{:d}".format(ii) for ii in range(X.shape[0])]
        data = pd.DataFrame(X, index=index, columns=self.columns)
        return self.sisso_out.model.predict(data)

    @classmethod
    def OMP(
        cls,
        desc_dim,
        use_custodian: bool = True,
        custodian_job_kwargs: None|dict = None,
        custodian_kwargs: None|dict = None,
        run_dir: None|str = "SISSO_dir",
        clean_run_dir: bool = False,
    ):
        """Construct SISSORegressor for Orthogonal Matching Pursuit (OMP).

        OMP is usually the first step to be performed before applying SISSO.
        Indeed, one starts with a relatively small set of base input descriptors
        (usually less than 20), that are then combined together by SISSO. One way to
        obtain this small set is to use the OMP algorithm (which is a particular case
        of the SISSO algorithm itself).

        Args:
            desc_dim: Number of descriptors to get with OMP.
            use_custodian: Whether to use custodian (currently mandatory).
            custodian_job_kwargs: Keyword arguments for custodian job.
            custodian_kwargs: Keyword arguments for custodian.
            run_dir: Name of the directory where SISSO is run. If None, the directory
                will be set automatically. It then contains a timestamp and is unique.
            clean_run_dir: Whether to clean the run directory after SISSO has run.

        Returns:
            SISSORegressor: SISSO regressor with OMP parameters.
        """
        return cls(
            opset="(+)(-)(*)(/)(exp)(exp-)(^-1)(^2)(^3)(sqrt)(cbrt)(log)(|-|)(scd)(^6)",
            rung=0,
            desc_dim=desc_dim,
            subs_sis=1,
            method="L0",
            L1L0_size4L0=None,
            features_dimensions=None,
            use_custodian=use_custodian,
            custodian_job_kwargs=custodian_job_kwargs,
            custodian_kwargs=custodian_kwargs,
            run_dir=run_dir,
            clean_run_dir=clean_run_dir,
        )

    @classmethod
    def from_SISSOIn(cls, sisso_in: SISSOIn):
        """Construct SISSORegressor from a SISSOIn object.

        Args:
            sisso_in: SISSOIn object containing the inputs for a SISSO run.

        Returns:
            SISSORegressor: SISSO regressor.
        """
        raise NotImplementedError


class SISTransformer(FunctionTransformer):
    def __init__(self, descriptors):
         """Construct SISTransformer object.

         Args:
             descriptors: FeatureSpace object containing combinatorial
             feature space basis. It is best obtained from a fitted
             SISSO estimator object
         """

        FunctionTransformer(
            func=self.transformer_function,
            feature_names_out=self.transformer_feature_names_out,
            kw_args={"descriptors": descriptors}
        )

    @staticmethod
    def transformer_function(X, descriptors):
       SISfeatures = []
       for desc in descriptors:
           SISfeatures.append(desc.evaluate(X))
           SISfeatures[-1].name = desc.descriptor_string
        return X
        
    @staticmethod
    def transformer_feature_names_out(transformerself, input_features):
        params = transformerself.get_params()
        return params["kw_args"]["descriptors"]
