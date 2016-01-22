# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

from six import iterkeys, iteritems

from .common_utils import (
    _get, __get_inherited_trait_data, __get_inherited_res_type_data,
    merge_dicts
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


def resolve_scalar_data(param, resolve_from, **kwargs):
    ret = {}
    for obj_type in resolve_from:
        func = __map_data_inheritance(obj_type)
        inherited = func(param, **kwargs)
        ret[obj_type] = inherited
    return _merge_resolve_scalar_data(ret, resolve_from)


def _merge_resolve_scalar_data(resolved, resolve_from):
    # TODO hmm should this happen...
    if len(resolve_from) == 0:
        return resolved
    if len(resolve_from) == 1:
        return _get(resolved, resolve_from.pop(0), {})

    # the prefered should always be first in resolved_from
    data = _get(resolved, resolve_from.pop(0))
    for item in resolve_from:
        data = merge_dicts(data, _get(resolved, item, {}))
    return data


def __map_data_inheritance(obj_type):
    return {
        "traits": __trait_data,
        "types": __resource_type_data,
        "method": __method_data,
        "resource": __resource_data,
        "parent": __parent_data,
        "root": __root_data,
    }[obj_type]


def __trait_data(item, **kwargs):
    root = kwargs.get("root_")
    is_ = kwargs.get("is_")
    if is_:
        root_trait = _get(root.raw, "traits")
        if root_trait:
            # returns a list of params
            data = __get_inherited_trait_data(item, root_trait, is_, root)
            ret = {}
            for i in data:
                _data = _get(i, item)
                for k, v in list(iteritems(_data)):
                    ret[k] = v
            return ret
    return {}


def __resource_type_data(item, **kwargs):
    root = kwargs.get("root_")
    type_ = kwargs.get("type_")
    method = kwargs.get("method")
    item = __map_attr(item)
    if type_:
        root_resource_types = _get(root.raw, "resourceTypes", {})
        if root_resource_types:
            item = __reverse_map_attr(item)
            data = __get_inherited_res_type_data(item, root_resource_types,
                                                 type_, method, root)
            return data
    return {}


def __method_data(item, **kwargs):
    data = kwargs.get("data")
    return _get(data, item, {})


def __resource_data(item, **kwargs):
    data = kwargs.get("resource_data")
    return _get(data, item, {})


def __parent_data(item, **kwargs):
    data = kwargs.get("parent_data")
    return _get(data, item, {})


def __root_data(item, **kwargs):
    root = kwargs.get("root_")
    return _get(root.raw, item, {})


# <---[.resolve_inherited_scalar helpers]--->
def __map_inheritance(obj_type):
    return {
        "traits": __trait,
        "types": __resource_type,
        "method": __method,
        "resource": __resource,
        "parent": __parent,
        "root": __root,
        "rootx": _x_root
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


def __reverse_map_attr(attribute):
    """Map RAML attr name to ramlfications attr name"""
    return {
        "media_ype": "mediaType",
        "protocols": "protocols",
        "headers": "headers",
        "body": "body",
        "responses": "responses",
        "uri_params": "uriParameters",
        "base_uri_params": "baseUriParameters",
        "query_params": "queryParameters",
        "form_params": "formParameters",
        "description": "description",
        "secured_by": "securedBy",
    }[attribute]


def __get_parent(attribute, parent):
    if parent:
        return getattr(parent, attribute, {})
    return {}


def __trait(item, **kwargs):
    root = kwargs.get("root_", kwargs.get("root"))
    is_ = kwargs.get("is_")
    if is_ and root:
        raml = _get(root.raw, "traits")
        if raml:
            data = __get_inherited_trait_data(item, raml, is_, root)
            return _get(data, item)


def __resource_type(item, **kwargs):
    root = kwargs.get("root", kwargs.get("root_"))
    type_ = kwargs.get("type_")
    method = kwargs.get("method")
    item = __map_attr(item)
    if type_ and root:
        raml = _get(root.raw, "resourceTypes")
        if raml:
            data = __get_inherited_res_type_data(item, raml, type_,
                                                 method, root)

            return data
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


def _x_root(item, **kwargs):
    root = kwargs.get("root", kwargs.get("root_"))
    item = _get(root.raw, item)
    return item


def __root(item, **kwargs):
    root = kwargs.get("root", kwargs.get("root_"))
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
