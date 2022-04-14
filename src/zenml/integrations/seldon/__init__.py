#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
"""
The Seldon Core integration allows you to use the Seldon Core model serving
platform to implement continuous model deployment.
"""
from zenml.enums import StackComponentType
from zenml.integrations.constants import SELDON
from zenml.integrations.integration import Integration
from zenml.integrations.utils import register_flavor

SELDON_MODEL_DEPLOYER_FLAVOR = "seldon"


class SeldonIntegration(Integration):
    """Definition of Seldon Core integration for ZenML."""

    NAME = SELDON
    REQUIREMENTS = [
        "kubernetes==18.20.0",
    ]

    @classmethod
    def activate(cls) -> None:
        """Activate the Seldon Core integration"""
        from zenml.integrations.seldon import services  # noqa

    @classmethod
    def declare(cls) -> None:
        """Declare the stack component flavors for the Seldon Core."""
        register_flavor(
            flavor=SELDON_MODEL_DEPLOYER_FLAVOR,
            source="zenml.integrations.seldon.model_deployers.SeldonModelDeployer",
            stack_component_type=StackComponentType.MODEL_DEPLOYER,
            integration=cls.NAME,
        )


SeldonIntegration.check_installation()
