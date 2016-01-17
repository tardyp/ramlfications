# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

from six import iterkeys

from .common_utils import (
    _get, __get_inherited_trait_data, __get_inherited_res_type_data
)


def resolve_scalar(method_data, resource_data, item, default):
    """
    Returns tuple of method-level and resource-level data for a desired
    attribute (e.g. ``description``).  Used for ``scalar`` -type attributes.
    """
    method_level = _get(method_data, item, default)
    resource_level = _get(resource_data, item, default)
    return method_level, resource_level


def resolve_inherited_scalar(item, inherit_from=[], **kwargs):
    """
    Returns data associated with item (e.g. ``protocols``) while
    preserving order of inheritance.
    """
    for obj_type in inherit_from:
        inherit_func = __map_inheritance(obj_type)
        inherited = inherit_func(item, **kwargs)
        if inherited:
            return inherited
    return None


# <---[.resolve_inherited_scalar helpers]--->
def __map_inheritance(obj_type):
    return {
        "traits": __trait,
        "types": __resource_type,
        "method": __method,
        "resource": __resource,
        "parent": __parent,
        "root": __root
    }[obj_type]


def __map_attr(attribute):
    """Map RAML attr name to ramlfications attr name"""
    return {
        "mediaType": "media_type",
        "protocols": "protocols",
        "headers": "headers",
        "body": "body",
        "responses": "responses",
        "uriParameters": "uri_params",
        "baseUriParameters": "base_uri_params",
        "queryParameters": "query_params",
        "formParameters": "form_params",
        "description": "description",
        "securedBy": "secured_by",
    }[attribute]


def __get_parent(attribute, parent):
    if parent:
        return getattr(parent, attribute, {})
    return {}


def __trait(item, **kwargs):
    root = kwargs.get("root")
    is_ = kwargs.get("is_")
    if is_:
        raml = _get(root.raw, "traits")
        return __get_inherited_trait_data(item, raml, is_, root)


def __resource_type(item, **kwargs):
    root = kwargs.get("root")
    type_ = kwargs.get("type_")
    method = kwargs.get("method")
    item = __map_attr(item)
    if type_:
        raml = _get(root.raw, "resourceTypes")
        if raml:
            data = __get_inherited_res_type_data(item, raml, type_,
                                                 method, root)
            return _get(data, item)
    return None


def __method(item, **kwargs):
    method = kwargs.get("method")
    data = kwargs.get("data")
    method_data = _get(data, method, {})
    return _get(method_data, item, {})


def __resource(item, **kwargs):
    data = kwargs.get("data")
    return _get(data, item, {})


def __parent(item, **kwargs):
    parent = kwargs.get("parent")
    return __get_parent(item, parent)


def __root(item, **kwargs):
    root = kwargs.get("root")
    item = __map_attr(item)
    return getattr(root, item, None)
# </---[.resolve_inherited_scalar helpers]--->


def parse_assigned_dicts(items):
    """
    Return a list of trait/type/scheme names if an assigned trait/
    resource type/secured_by is a dictionary.
    """
    if not items:
        return
    if isinstance(items, dict):
        return list(iterkeys(items))[0]
    if isinstance(items, list):
        item_names = []
        for i in items:
            if isinstance(i, str):
                item_names.append(i)
            elif isinstance(i, dict):
                name = list(iterkeys(i))[0]
                item_names.append(name)
        return item_names
    return items
