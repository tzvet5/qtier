from __future__ import annotations

import inspect
from typing import Any
from typing import TYPE_CHECKING

from attrs import define
from jinja2 import Environment
from jinja2 import PackageLoader
from jinja2 import select_autoescape


if TYPE_CHECKING:  # pragma: no cover
    from qtgqlcodegen.config import QtGqlConfig
    from qtgqlcodegen.compiler.operation import QtGqlOperationDefinition, QtGqlQueriedField
    from qtgqlcodegen.objecttype import (
        QtGqlEnumDefinition,
        QtGqlInputObjectTypeDefinition,
        QtGqlInterfaceDefinition,
        QtGqlObjectTypeDefinition,
    )


template_env = Environment(
    loader=PackageLoader("qtgqlcodegen"),
    autoescape=select_autoescape(),
    variable_start_string="👉",  # originally {{ variable }}, using 👉 variable 👈 because C++ uses curly brackets.
    variable_end_string="👈",
)


def wrap_curly_filter(v: str, ignore: bool = False) -> str:
    if ignore:
        return v
    return "{" + v + "}"


template_env.filters["wrapcurly"] = wrap_curly_filter

SCHEMA_TEMPLATE = template_env.get_template("schema.jinja.cpp")
HANDLERS_TEMPLATE = template_env.get_template("handlers.jinja.py")
CONFIG_TEMPLATE = template_env.get_template("config.jinja.py")
CMAKE_TEMPLATE = template_env.get_template("CMakeLists.jinja.txt")


@define
class TemplateContext:
    enums: list[QtGqlEnumDefinition]
    types: list[QtGqlObjectTypeDefinition]
    interfaces: list[QtGqlInterfaceDefinition]
    queries: list[QtGqlOperationDefinition]
    mutations: list[QtGqlOperationDefinition]
    subscriptions: list[QtGqlOperationDefinition]
    input_objects: list[QtGqlInputObjectTypeDefinition]
    config: QtGqlConfig

    @property
    def dependencies(self) -> list[str]:
        def build_import_statement(t: type[Any]) -> str:
            mod = inspect.getmodule(t)
            assert mod
            return f"from {mod.__name__} import {t.__name__}"

        ret = [build_import_statement(scalar) for scalar in self.config.custom_scalars.values()]
        ret.append(build_import_statement(self.config.base_object))
        return ret

    @property
    def custom_scalars(self) -> list[str]:
        return [scalar.__name__ for scalar in self.config.custom_scalars.values()]

    @property
    def base_object_name(self) -> str:
        return self.config.base_object.__name__


def schema_types_template(context: TemplateContext) -> str:
    return SCHEMA_TEMPLATE.render(context=context)


def handlers_template(context: TemplateContext) -> str:
    return HANDLERS_TEMPLATE.render(context=context)


def cmake_template(context: TemplateContext) -> str:
    return CMAKE_TEMPLATE.render(context=context)


@define
class ConfigContext:
    p_field: QtGqlQueriedField

    @property
    def choices(self):
        if self.p_field.choices:
            return {
                type_name: {
                    selection.name: selection.as_conf_string() or "None" for selection in selections
                }
                for type_name, selections in self.p_field.choices.items()
            }
        else:
            return {}

    @property
    def selections(self) -> dict[str, str]:
        if self.p_field.selections:
            return {
                selection.name: selection.as_conf_string() for selection in self.p_field.selections
            }
        else:
            return {}


def config_template(context: ConfigContext):
    return CONFIG_TEMPLATE.render(context=context)
