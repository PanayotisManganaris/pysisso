# -*- coding: utf-8 -*-
# Copyright (c) 2020, Matgenix SRL, All rights reserved.
# Distributed open source for academic and non-profit users.
# Contact Matgenix for commercial usage.
# See LICENSE file for details.

"""Module containing classes to parse SISSO output files."""

from __future__ import annotations

import os
import re
from typing import Callable, Mapping

import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from monty.json import MSONable  # type: ignore

from pysisso.utils import list_of_ints, list_of_strs, matrix_of_floats, str_to_bool


class SISSOVersion(MSONable):
    """Class containing information about the SISSO version used."""

    def __init__(self, header_string: str, version: list[int]):
        """Construct SISSOVersion object.

        Args:
            header_string: Header string found in the SISSO.out output file.
            version: Version of SISSO extracted from the header string.
        """
        self.header_string = header_string
        self.version = version

    @classmethod
    def from_string(cls, string: str):
        """Construct SISSOVersion from string.

        Args:
            string: First line from the SISSO.out output file.
        """
        version_sp = string.split(",")[0].split(".")
        return cls(
            header_string=string.strip(),
            version=version_sp[1:]
        )


def scd(x):
    """Get Standard Cauchy Distribution of x.

    The Standard Cauchy Distribution (SCD) of x is :

    SCD(x) = (1.0 / pi) * 1.0 / (1.0 + x^2)

    Args:
        x: Value(s) for which the Standard Cauchy Distribution is needed.

    Returns:
        Standard Cauchy Distribution at value(s) x.
    """
    return 1.0 / (np.pi * (1.0 + x * x))


class SISSODescriptor(MSONable):
    """
    Class containing one composed descriptor.

    Class constructors provided to parse various sources
    """

    def __init__(self, descriptor_id: int, descriptor_string: str):
        """Construct SISSODescriptor object.

        Args:
            descriptor_id: Integer identifier of this descriptor.
            descriptor_string: String description of this descriptor.
        """
        self.descriptor_id = descriptor_id
        self.descriptor_string = descriptor_string
        self.evalstring = self._decode_function(self.descriptor_string)["evalstring"]

    def evaluate(self, df):  # pylint: disable=W0613
        """Evaluate the descriptor from a given Dataframe.

        Args:
            df: panda's Dataframe to evaluate SISSODescriptor

        Returns:
            float: Value of this descriptor for the samples in the dataframe.

        WARNING: this uses python eval which is inherently unsafe.
        """
        return eval(self.evalstring)  # nosec, pylint: disable=W0123

    def __str__(self):
        """Return string representation of this SISSODescriptor.

        Returns:
            str: String representation of this SISSODescriptor.
        """
        return self.descriptor_string

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def _decode_function(string):
        """Get valid python expression based on string."""
        OPERATORS_REPLACEMENT = [
            "exp(-",
            "exp(",
            "sin(",
            "cos(",
            "sqrt(",
            "cbrt(",
            "log(",
            "abs(",
            "scd(",
            ")^-1",
            ")^2",
            ")^3",
            ")^6",
            "+",
            "-",
            "*",
            "/",
            "(",
            ")",
        ]

        # Get the list of base features needed
        # First replace the operators with "#"
        replaced_string = string
        for op in OPERATORS_REPLACEMENT:
            replaced_string = replaced_string.replace(op, "#" * len(op))
        # Get the features in order of the string and get the unique list of features
        if replaced_string[0] != "#" or replaced_string[-1] != "#":
            raise ValueError('%s should start and end with "#"' % replaced_string)
        features_in_string = []
        in_feature_word = False
        ichar_start = None
        inputs = []
        for ichar, char in enumerate(replaced_string):
            if in_feature_word and char == "#":
                in_feature_word = False
                featname = replaced_string[ichar_start:ichar]
                if featname not in inputs:
                    inputs.append(featname)
                features_in_string.append(
                    {"featname": featname, "istart": ichar_start, "iend": ichar}
                )
            elif not in_feature_word and char != "#":
                in_feature_word = True
                ichar_start = ichar

        # Prepare string to be formatted from features
        prev_ichar = None
        out = []
        for fdict in features_in_string:
            out.append(string[prev_ichar : fdict["istart"]])
            prev_ichar = fdict["iend"]
            out.append("df['{}']".format(fdict["featname"]))
        out.append(string[prev_ichar:None])
        evalstring = "".join(out)

        # Replace operators in the string with numpy operators
        evalstring = evalstring.replace("sin(", "np.sin(")
        evalstring = evalstring.replace("cos(", "np.cos(")
        evalstring = evalstring.replace("exp(", "np.exp(")
        evalstring = evalstring.replace("log(", "np.log(")
        evalstring = evalstring.replace("sqrt(", "np.sqrt(")
        evalstring = evalstring.replace("cbrt(", "np.cbrt(")
        evalstring = evalstring.replace("abs(", "np.abs(")
        evalstring = evalstring.replace(")^2", ")**2")
        evalstring = evalstring.replace(")^3", ")**3")
        evalstring = evalstring.replace(")^6", ")**6")
        evalstring = evalstring.replace(")^-1", ")**-1")

        return {
            "evalstring": evalstring,
            "features_in_string": features_in_string,
            "inputs": inputs,
        }

    @classmethod
    def from_string(cls, string: str):
        """Construct SISSODescriptor from string.

        The string must be the line of the descriptor in the SISSO.out output file,
            e.g. : 1:[((feature1-feature2)+(feature3-feature4))]

        Args:
            string: Substring from the SISSO.out output file corresponding to one
                descriptor of SISSO.
        """
        sp = string.split(":")
        return cls(descriptor_id=int(sp[0]), descriptor_string=sp[1][1:-1])

class SISSOModel(MSONable):
    """
    Class containing one SISSO model.

    Class constructors provided to parse various sources
    """

    def __init__(
        self,
        dimension: int,
        descriptors: list[SISSODescriptor],
        coefficients: list[list[float]],
        intercept: list[float],
        rmse: list[float]|None = None,
        maxae: list[float]|None = None,
    ):
        """Construct SISSOModel object.

        Args:
            dimension: Dimension of the model.
            descriptors: list of descriptors used in the model.
            coefficients: Coefficient of each descriptor for each task/property.
            intercept: Intercept of the model for each task/property.
            rmse: Root Mean Squared Error of the model on the training data for each
                task/property.
            maxae: Maximum Absolute Error of the model on the training data for each
                task/property.
        """
        self.dimension = dimension
        self.descriptors = descriptors
        self.coefficients = coefficients
        self.intercept = intercept
        self.rmse = rmse
        self.maxae = maxae

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict values from input DataFrame.

        The input DataFrame should have the columns needed by the different SISSO
            descriptors.

        Args:
            df: panda's DataFrame containing the base features needed to apply the
                model.

        Returns:
            ndarray: Predicted values from the model.
        """
        out = np.array([[intercept] * len(df) for intercept in self.intercept]).T
        for idescr, descr in enumerate(self.descriptors):
            for itask, coeffs in enumerate(self.coefficients):
                dval = coeffs[idescr] * descr.evaluate(df)
                out[:, itask] += dval  # pylint: disable=E1137
        return out

    @classmethod
    def from_string(cls, string: str):
        """Construct SISSOModel object from string.

        The string must be the excerpt corresponding to one model in the SISSO.out
        output file, containing "@@@@descriptor"

        Args:
            string: String from the SISSO.out output file corresponding to one model
                of SISSO.
        """
        lines = string.split("\n")
        dimension = int(lines[0].split()[-1])
        descriptors: list[SISSODescriptor]|None = None
        coefficients = []
        intercept = []
        rmse = []
        maxae = []
        for line in lines:
            if "@@@descriptor" in line:
                descriptors = []
                continue
            if descriptors is not None and len(descriptors) < dimension:
                descriptors.append(SISSODescriptor.from_string(line))
                continue
            if "coefficients_" in line:
                coefficients.append([float(nn) for nn in line.split(":")[1].split()])
            elif "Intercept_" in line:
                intercept.append(float(line.split(":")[1]))
            elif "RMSE,MaxAE_" in line:
                sp = line.split()
                rmse.append(float(sp[1]))
                maxae.append(float(sp[2]))

        if descriptors is None:  # pragma: no cover, wrong SISSO output
            raise ValueError("Descriptor not found")

        return cls(
            dimension=dimension,
            descriptors=descriptors,
            coefficients=coefficients,
            intercept=intercept,
            rmse=rmse,
            maxae=maxae,
        )


    @classmethod
    def from_models_files(cls, top_file:str, coeff_file:str):
        raise NotImplementedError("not yet equipped to extract alternative models")

class SISSOIteration(MSONable):
    """
    Class containing one SISSO iteration as reported by SISSO.out

    Object contains information generally relevant to the execution of
    iterations in general, but in particular is contains the linear
    models generated by the Sparsifying Operator.
    """
    def __init__(
        self,
        iteration_number: int,
        sisso_model: SISSOModel,
        feature_spaces: Mapping[str, int],
        SIS_subspace_size: int,
        cpu_time: float,
    ):
        """Construct SISSOIteration object.

        Args:
            iteration_number: Number of the iteration.
            sisso_model: SISSO model of this iteration.
            feature_spaces: Number of features in each feature rung.
            SIS_subspace_size: Size of the SIS subspace.
            cpu_time: CPU time for this SISSO iteration.
        """
        self.iteration_number = iteration_number
        self.sisso_model = sisso_model
        self.feature_spaces = feature_spaces
        self.SIS_subspace_size = SIS_subspace_size
        self.cpu_time = cpu_time

    @classmethod
    def from_string(cls, string: str):
        """Construct SISSOIteration object from string.

        The string must be the excerpt corresponding to one iteration in SISSO.out,
        i.e. it must start with "Dimension: N" and end with a report of the time used
        by DI

        Args:
            string: String from the SISSO.out output file corresponding to one
                iteration of SISSO.
        """
        sisso_model = SISSOModel.from_string(string)

        r_feature_spaces = r"Total number of features in the space phi.*?\n"
        match_feature_spaces = re.findall(r_feature_spaces, string)
        feature_spaces = {
            mfs.split()[-2][:-1]: int(mfs.split()[-1]) for mfs in match_feature_spaces
        }

        r_SIS_subspace_size = r"Size of the SIS-selected subspace.*?\n"
        match_SIS_subspace_size = re.findall(r_SIS_subspace_size, string)
        SIS_subspace_size = int(match_SIS_subspace_size[0].split()[-1])

        r_cputime = r"Time \(second\) used for this DI:.*?\n"
        match_cputime = re.findall(r_cputime, string)
        cpu_time = float(match_cputime[0].split()[-1])

        return cls(
            iteration_number=sisso_model.dimension,
            sisso_model=sisso_model,
            feature_spaces=feature_spaces,
            SIS_subspace_size=SIS_subspace_size,
            cpu_time=cpu_time,
        )


class SISSOParams(MSONable):
    """Class containing input parameters extracted from the SISSO output file."""

    PARAMS: list[tuple[str, str, type|Callable]] = [
        ("property_type", "Property type:", int),
        ("total_number_properties", "Number of tasks:", int),
        ("descriptor_dimension", "Descriptor dimension:", int),
        ("number_of_samples", "Number of samples for each task:", list_of_ints),
        ("n_scalar_features", "Number of scalar features:", int),
        (
            "n_rungs",
            r"Tier of the feature space:",
            int,
        ),
        (
            "max_feature_complexity",
            r"Maximal feature complexity \(number of operators in a feature\):",
            int,
        ),
        (
            "dimension_types",
            "Units of the input primary features (each represented by a vector):",
            matrix_of_floats,
        ),
        (
            "lower_bound_maxabs_value",
            r"The feature will be discarded if the minimum of the maximal abs. value in it <",
            float,
        ),
        (
            "upper_bound_maxabs_value",
            r"The faature will be discarded if the maximum of the maximal abs\. value in it >",
            float,
        ),
        (
            "SIS_subspaces_sizes",
            r"Size of the SIS-selected \(single\) subspace :",
            list_of_ints,
        ),
        ("operators", "Operators for feature construction:", list_of_strs),
        ("sparsification_method", "Method for sparse regression:", str),
        ("n_topmodels", "Number of the top-ranked models to output:", int),
        ("fit_intercept", "Fitting intercept:", str_to_bool),
        ("metric", "Metric for model selection:", str),
    ]

    def __init__(
        self,
        property_type: int|None = None,
        descriptor_dimension: int|None = None,
        total_number_properties: int|None = None,
        task_weighting: list[int]|None = None,
        number_of_samples: list[int]|None = None,
        n_scalar_features: int|None = None,
        n_rungs: int|None = None,
        max_feature_complexity: int|None = None,
        n_dimension_types: int|None = None,
        dimension_types: inty|None = None,
        lower_bound_maxabs_value: float|None = None,
        upper_bound_maxabs_value: float|None = None,
        SIS_subspaces_sizes: list[int]|None = None,
        operators: list[str]|None = None,
        sparsification_method: str|None = None,
        n_topmodels: int|None = None,
        fit_intercept: bool|None = None,
        metric: str|None = None,
    ):  # noqa: D417
        """Construct SISSOParams object.

        All arguments not listed below are arguments from the SISSO code. For more
        information, see https://github.com/rouyang2017/SISSO.
        """
        self.property_type = property_type
        self.descriptor_dimension = descriptor_dimension
        self.total_number_properties = total_number_properties
        self.task_weighting = task_weighting
        self.number_of_samples = number_of_samples
        self.n_scalar_features = n_scalar_features
        self.n_rungs = n_rungs
        self.max_feature_complexity = max_feature_complexity
        self.n_dimension_types = n_dimension_types
        self.dimension_types = dimension_types
        self.lower_bound_maxabs_value = lower_bound_maxabs_value
        self.upper_bound_maxabs_value = upper_bound_maxabs_value
        self.SIS_subspaces_sizes = SIS_subspaces_sizes
        self.operators = operators
        self.sparsification_method = sparsification_method
        self.n_topmodels = n_topmodels
        self.fit_intercept = fit_intercept
        self.metric = metric

    @classmethod
    def from_string(cls, string: str):
        """Construct SISSOParams object from string. No validation necessary"""
        kwargs = {}
        for class_var, output_var_str, var_type in cls.PARAMS:
            if class_var == "dimension_types":
                match = re.search(
                    r"(  (?:\d+\.\d* )+(?:\d+\.\d*)\n)+", string
                )
                if match is not None:
                    kwargs[class_var] = var_type(match[0])
            else:
                matches = re.findall(r"{}.*?\n".format(output_var_str), string)
                if len(matches) != 1:
                    kwargs[class_var] = var_type(matches[0].split()[-1])
        return cls(**kwargs)

    def __str__(self):
        """Return string representation of the SISSO parameters.

        Returns:
            str: String representation of this SISSOParams object.
        """
        out = ["Parameters for SISSO :"]
        for class_var, _, _ in self.PARAMS:
            out.append(
                " - {} : {}".format(class_var, str(self.__getattribute__(class_var)))
            )
        return "\n".join(out)


class SISSOOut(MSONable):
    """Class containing the results contained in the SISSO output file (SISSO.out)."""

    def __init__(
        self,
        params: SISSOParams,
        iterations: list[SISSOIteration],
        version: SISSOVersion,
        cpu_time: float|None,
    ):
        """Construct SISSOOut object.

        Args:
            params: Parameters used for SISSO (as a SISSOParams object).
            iterations: list of SISSO iterations.
            version: Information about the version of SISSO used as a SISSOVersion
                object.
            cpu_time: Wall-clock CPU time from the output file.
        """
        self.params = params
        self.iterations = iterations
        self.version = version
        self.cpu_time = cpu_time

    @classmethod
    def from_file(cls, filepath: str = "SISSO.out", allow_unfinished: bool = False):
        """Read in SISSOOut data from file.

        Args:
            filepath: Path of the file to extract output.
            allow_unfinished: Whether to allow parsing of unfinished SISSO runs.
        """
        with open(filepath, "r") as f:
            string = f.read()

        r = r"Have a nice day !"
        match = re.search(r, string) 
        if not match and not allow_unfinished:
            raise ValueError(
                "SISSO.out should end with 'Have a nave day !'"
            )

        params = SISSOParams.from_string(string)
        
        r = r"Dimension:.*?(?=Time \(second\) used for this DI:).*?\n"
        match = re.findall(r, string, re.DOTALL)
        iterations = []
        for iteration_string in match:
            iterations.append(
                SISSOIteration.from_string(iteration_string)
            )

        with open(filepath, "r") as f:
            header_lines = [next(f) for x in range(3)]
        header = header_lines[2]
        version = SISSOVersion.from_string(header)

        r = r"Total time \(second\):.*\n"
        match = re.search(r, string)
        cpu_time = float(match[0].split()[-1])

        return cls(
            params=params, iterations=iterations, version=version, cpu_time=cpu_time
        )

    @property
    def model(self):
        """Model for this SISSO run.

        The last model is provided (with the highest dimension).
        """
        return self.iterations[-1].sisso_model

    @property
    def models(self):
        """Models (for all dimensions) for this SISSO run."""
        return [it.sisso_model for it in self.iterations]


class FeatureSpace(MSONable):
    """Class containing the SIS selected features.

    This class is a container for the space_DDDd.expressions files (DDD being the
    dimension of the descriptor) that are stored in the SIS_subspaces directory.
    """
    def __init__(
        self,
        path: str = 'SIS_subspaces/Uspace.expressions',
    ):
        self.descriptors: list[SISSODescriptor] = []

        if os.path.isfile(path):
            with open(path, 'r') as f:
                for num, line in enumerate(f):
                    self.descriptors.append(
                        SISSODescriptor(num, line.split()[0])
                    )
        else:
            warnings.warn(
                "No SIS subspaces recovered for storage, ensure SISSO returns",
                "subspaces directory"
            )

    def __iter__(self):
        return self.descriptors.__iter__()

class TopModels(MSONable):
    """Class containing summary info of the top N models from SISSO.

    This class is a container for the topNNNN_DDDd files (NNNN being the number of
    models in the file and DDD the dimension of the descriptor) that are stored in
    the models directory.
    """


class TopModelsCoefficients(MSONable):
    """Class containing the coefficients of the features for the top N models.

    This class is a container for the topNNNN_DDDd_coeff files (NNNN being the number
    of models in the file and DDD the dimension of the descriptor) that are stored
    in the models directory.
    """


class DescriptorsDataModels(MSONable):  # pragma: no cover, reading full SISSO.out
    """Class containing the true and predicted data for the best descriptors/models.

    This class is a container for the desc_DDDd_pPPP.dat files (DDD being the
    dimension of the descriptor and PPP the property number in case of multi-task
    SISSO) that are stored in the desc_dat directory.

    Note: see if we want to implement this class, everything might be contained in
        SISSO.out and its SISSOOut object.
    """

    def __init__(self, data):
        """Construct this DescriptorsDataModels object.

        Args:
            data: Data for this DescriptorsDataModels object.
        """
        self.data = data

    @classmethod
    def from_file(cls, filepath):
        """Construct this DescriptorsDataModels object from file.

        Args:
            filepath: File to construct this DescriptorsDataModels from.

        Returns:
            DescriptorsDataModels: DescriptorsDataModels object.
        """
        if filepath.endswith(".dat"):
            return cls.from_dat_file(filepath)
        else:
            raise ValueError("The from_file method is working only with .dat files")

    @classmethod
    def from_dat_file(cls, filepath):
        """Construct this DescriptorsDataModels object from .dat file.

        Args:
            filepath: File to construct this DescriptorsDataModels from.

        Returns:
            DescriptorsDataModels: DescriptorsDataModels object.
        """
        data = pd.read_csv(filepath, delim_whitespace=True)
        return cls(data=data)


class ResidualData(MSONable):
    """Class containing the residuals for the training data computed at each iteration.

    This class is a container for the res_DDDd_pPPP.dat files (DDD being the dimension
    of the descriptor and PPP the property number in case of multi-task SISSO)
    that are stored in the residual directory.
    """
