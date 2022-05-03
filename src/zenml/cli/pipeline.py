#  Copyright (c) ZenML GmbH 2020. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""CLI to interact with pipelines."""
import textwrap
import types
from typing import Any, Dict, Union

import click

from zenml.cli.cli import cli
from zenml.config.config_keys import (
    PipelineConfigurationKeys,
    SourceConfigurationKeys,
    StepConfigurationKeys,
)
from zenml.exceptions import PipelineConfigurationError
from zenml.logger import get_logger
from zenml.utils import source_utils, yaml_utils

logger = get_logger(__name__)


def _get_module(
    module: types.ModuleType, config_item: Union[str, Dict[str, str]]
) -> Any:
    """Based on a config item from the config yaml the corresponding module
    attribute is loaded.

    Args:
        module: Base module to use for import if only a function/class name is
                supplied
        config_item: Config item loaded from the config yaml
                        - If it is a string it is the name of a function/class
                          in the module (e.g `step_name`)
                        - If it is a dict, it will have a relative filepath and
                          a function/class name (e.g {`file`: `steps/steps.py`,
                          `name`: `step_name`}

    Returns:
         imported function/class
    """
    if isinstance(config_item, dict):
        if SourceConfigurationKeys.FILE_ in config_item:
            module = source_utils.import_python_file(
                config_item[SourceConfigurationKeys.FILE_]
            )

        implementation_name = config_item[SourceConfigurationKeys.NAME_]
        implemented_class = _get_module_attribute(module, implementation_name)
        return implemented_class
    elif isinstance(config_item, str):
        correct_input = textwrap.dedent(
            f"""
        {SourceConfigurationKeys.NAME_}: {config_item}
        {SourceConfigurationKeys.FILE_}: optional/filepath.py
        """
        )

        raise PipelineConfigurationError(
            f"As of ZenML version 0.8.0 `str` entries are no longer supported "
            f"to define steps or materializers. Instead you will now need to "
            f"pass a dictionary. This dictionary **has to** contain a "
            f"`{SourceConfigurationKeys.NAME_}` which refers to the function/"
            f"class name. If this entity is defined outside the main module,"
            f"you will need to additionally supply a "
            f"{SourceConfigurationKeys.FILE_} with the relative forward-slash-"
            f"separated path to the file. \n"
            f"You tried to pass in `{config_item}` - however you should have "
            f"specified the name (and file) like this:"
            f" {correct_input}"
        )
    else:
        raise PipelineConfigurationError(
            f"Only `str` and `dict` values are allowed for "
            f"'step_source' attribute of a step configuration. You "
            f"tried to pass in `{config_item}` (type: "
            f"`{type(config_item).__name__}`)."
        )


def _get_module_attribute(module: types.ModuleType, attribute_name: str) -> Any:
    """Gets an attribute from a module.

    Args:
        module: The module to load the attribute from.
        attribute_name: Name of the attribute to load.

    Returns:
        The attribute value.

    Raises:
        PipelineConfigurationError: If the module does not have an attribute
            with the given name.
    """
    try:
        return getattr(module, attribute_name)
    except AttributeError:
        raise PipelineConfigurationError(
            f"Unable to load '{attribute_name}' from"
            f" file '{module.__file__}'"
        ) from None


@cli.group()
def pipeline() -> None:
    """Pipeline group"""


@pipeline.command("run", help="Run a pipeline with the given configuration.")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.argument("python_file")
def run_pipeline(python_file: str, config_path: str) -> None:
    """Runs pipeline specified by the given config YAML object.

    Args:
        python_file: Path to the python file that defines the pipeline.
        config_path: Path to configuration YAML file.
    """
    module = source_utils.import_python_file(python_file)
    config = yaml_utils.read_yaml(config_path)
    PipelineConfigurationKeys.key_check(config)

    pipeline_name = config[PipelineConfigurationKeys.NAME]
    pipeline_class = _get_module_attribute(module, pipeline_name)

    steps = {}
    for step_name, step_config in config[
        PipelineConfigurationKeys.STEPS
    ].items():
        StepConfigurationKeys.key_check(step_config)
        source = step_config[StepConfigurationKeys.SOURCE_]
        step_class = _get_module(module, source)

        step_instance = step_class()
        materializers_config = step_config.get(
            StepConfigurationKeys.MATERIALIZERS_, None
        )
        if materializers_config:
            # We need to differentiate whether it's a single materializer
            # or a dictionary mapping output names to materializers
            if isinstance(materializers_config, str):
                materializers = _get_module(module, materializers_config)
            elif isinstance(materializers_config, dict):
                materializers = {
                    output_name: _get_module(module, source)
                    for output_name, source in materializers_config.items()
                }
            else:
                raise PipelineConfigurationError(
                    f"Only `str` and `dict` values are allowed for "
                    f"'materializers' attribute of a step configuration. You "
                    f"tried to pass in `{materializers_config}` (type: "
                    f"`{type(materializers_config).__name__}`)."
                )
            step_instance = step_instance.with_return_materializers(
                materializers
            )

        steps[step_name] = step_instance
    pipeline_instance = pipeline_class(**steps).with_config(
        config_path, overwrite_step_parameters=True
    )
    logger.debug("Finished setting up pipeline '%s' from CLI", pipeline_name)
    pipeline_instance.run()
