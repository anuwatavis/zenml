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
import json
from typing import Any, ClassVar, Dict, List

from google.cloud import secretmanager

from zenml.logger import get_logger
from zenml.secret.base_secret import BaseSecretSchema
from zenml.secret.secret_schema_class_registry import SecretSchemaClassRegistry
from zenml.secrets_managers.base_secrets_manager import BaseSecretsManager
from zenml.stack.stack_component_class_registry import (
    register_stack_component_class,
)

logger = get_logger(__name__)

ZENML_SCHEMA_NAME = "zenml-schema-name"
ZENML_GROUP_KEY = "zenml-group-key"


@register_stack_component_class
class GCPSecretsManager(BaseSecretsManager):
    """Class to interact with the AWS secrets manager."""

    project_id: str

    # Class configuration
    FLAVOR: ClassVar[str] = "gcp_secrets_manager"
    CLIENT: ClassVar[Any] = None

    @classmethod
    def _ensure_client_connected(cls) -> None:
        if cls.CLIENT is None:
            cls.CLIENT = secretmanager.SecretManagerServiceClient()

    @property
    def parent_name(self):
        return f"projects/{self.project_id}"

    def register_secret(self, secret: BaseSecretSchema) -> None:
        """Registers a new secret.

        Args:
            secret: the secret to register"""
        self._ensure_client_connected()

        for k, v in secret.content.items():
            # Create the secret, this only creates an empty secret with the
            #  supplied name.
            gcp_secret = self.CLIENT.create_secret(
                request={
                    "parent": self.parent_name,
                    "secret_id": k,
                    "secret": {"replication": {"automatic": {}},
                               "labels": [(ZENML_GROUP_KEY, secret.name),
                                          (ZENML_SCHEMA_NAME, secret.TYPE)]}
                }
            )

            logger.debug("Created empty secret: %s", gcp_secret.name)

            self.CLIENT.add_secret_version(
                request={"parent": gcp_secret.name,
                         "payload": {"data": "{}".format(v).encode()}}
            )

            logger.debug("Added value to secret.")

    def get_secret(self, secret_name: str) -> BaseSecretSchema:
        """Gets a secret.

        Args:
            secret_name: the name of the secret to get

        Returns:
            The secret.

        Raises:
            RuntimeError: if the secret does not exist"""
        self._ensure_client_connected()

        # Build the resource name of the parent project.
        parent = f"projects/{self.project_id}"

        secret_contents = {}
        zenml_schema_name = None

        # List all secrets.
        for secret in self.CLIENT.list_secrets(request={"parent": parent}):
            if (ZENML_GROUP_KEY in secret.labels
                    and secret_name == secret.labels[ZENML_GROUP_KEY]):
                secret_key = secret.name.split('/')[-1]

                secret_version_name = secret.name + '/versions/latest'

                response = self.CLIENT.access_secret_version(
                    request={"name": secret_version_name})

                secret_value = response.payload.data.decode("UTF-8")
                secret_contents[secret_key] = secret_value

                zenml_schema_name = secret.labels[ZENML_SCHEMA_NAME]

        if not secret_contents:
            raise RuntimeError(f"No secrets found within the {secret_name}")

        secret_contents["name"] = secret_name

        secret_schema = SecretSchemaClassRegistry.get_class(
            secret_schema=zenml_schema_name
        )
        return secret_schema(**secret_contents)

    def get_all_secret_keys(self) -> List[str]:
        """Get all secret keys.

        Returns:
            A list of all secret keys."""
        self._ensure_client_connected()

        # Build the resource name of the parent project.
        parent = f"projects/{self.project_id}"

        set_of_secrets = set()

        # List all secrets.
        for secret in self.CLIENT.list_secrets(request={"parent": parent}):
            if ZENML_GROUP_KEY in secret.labels:
                group_key = secret.labels[ZENML_GROUP_KEY]
                set_of_secrets.add(group_key)

        return list(set_of_secrets)

    def update_secret(self, secret: BaseSecretSchema) -> None:
        """Update an existing secret.

        Args:
            secret: the secret to update"""
        self._ensure_client_connected()

        for k, v in secret.content.items():
            # Create the secret, this only creates an empty secret with the
            #  supplied name.
            parent = self.CLIENT.secret_path(self.project_id, k)
            payload = {"data": "{}".format(v).encode()}

            gcp_secret_version = self.CLIENT.add_secret_version(
                request={"parent": parent,
                         "payload": payload}
            )

    def delete_secret(self, secret_name: str) -> None:
        """Delete an existing secret. by name. In GCP a secret is a single k-v
        pair. Within ZenML a secret is a collection of k-v pairs. As such,
        deleting a secret will iterate through all secrets and delete the ones
        with the secret_name as label.

        Args:
            secret_name: the name of the secret to delete"""
        self._ensure_client_connected()

        # Build the resource name of the parent project.
        parent = f"projects/{self.project_id}"

        # Go through all gcp secrets and delete the ones with the secret_name
        #  as label.
        for secret in self.CLIENT.list_secrets(request={"parent": parent}):
            if (ZENML_GROUP_KEY in secret.labels
                    and secret_name == secret.labels[ZENML_GROUP_KEY]):
                self.CLIENT.delete_secret(request={"name": secret.name})

    def delete_all_secrets(self, force: bool = False) -> None:
        """Delete all existing secrets.

        Args:
            force: whether to force delete all secrets"""
        self._ensure_client_connected()

        parent = f"projects/{self.project_id}"

        # List all secrets.
        for secret in self.CLIENT.list_secrets(request={"parent": parent}):
            if (ZENML_GROUP_KEY in secret.labels
                    or ZENML_SCHEMA_NAME in secret.labels):
                logger.info("Deleted key-value pair {`%s`, `***`} from secret "
                            "`%s`",
                            secret.name.split('/')[-1],
                            secret.labels[ZENML_GROUP_KEY])
                self.CLIENT.delete_secret(request={"name": secret.name})

