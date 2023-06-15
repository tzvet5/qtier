from __future__ import annotations

from typing import TYPE_CHECKING

from attr import define

from qtgqlcodegen.core.template import template_env
from qtgqlcodegen.operation.template import OPERATION_TEMPLATE, OperationTemplateContext

if TYPE_CHECKING:
    from qtgqlcodegen.config import QtGqlConfig
    from qtgqlcodegen.types import (
        QtGqlEnumDefinition,
        QtGqlInputObjectTypeDefinition,
        QtGqlInterfaceDefinition,
        QtGqlObjectType,
    )


@define
class SchemaTemplateContext:
    enums: list[QtGqlEnumDefinition]
    types: list[QtGqlObjectType]
    interfaces: list[QtGqlInterfaceDefinition]
    input_objects: list[QtGqlInputObjectTypeDefinition]
    config: QtGqlConfig

    @property
    def dependencies(self) -> list[str]:
        ret: list[str] = []
        for scalar in self.config.custom_scalars.values():
            if scalar.include_path not in ret:
                ret.append(scalar.include_path)
        return [f"#include {inc}" for inc in ret]

    @property
    def custom_scalars(self) -> list[str]:
        return [scalar.graphql_name for scalar in self.config.custom_scalars.values()]


def schema_types_template_hpp(context: SchemaTemplateContext) -> str:
    return SCHEMA_HPP_TEMPLATE.render(context=context)


def schema_types_template_cpp(context: SchemaTemplateContext) -> str:
    return SCHEMA_CPP_TEMPLATE.render(context=context)


def operation_template(context: OperationTemplateContext) -> str:
    return OPERATION_TEMPLATE.render(context=context)


SCHEMA_HPP_TEMPLATE = template_env.get_template("schema.jinja.hpp")
SCHEMA_CPP_TEMPLATE = template_env.get_template("schema.jinja.cpp")