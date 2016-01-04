# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

import re

from six import iterkeys, iteritems

try:
    from collections import OrderedDict
except ImportError:  # NOCOV
    from ordereddict import OrderedDict

from ramlfications.parameters import (
    Header, Body, Response, URIParameter, QueryParameter,
    FormParameter
)

from .common_utils import _get


#####
# parameters.py object creation
#####
# TODO: not sure I need this here ... I'm essentially creating another
#       object rather than inherit/assign, like with types & traits
def _get_scheme(item, root):
    schemes = root.raw.get("securitySchemes", [])
    for s in schemes:
        if item == list(iterkeys(s))[0]:
            return s


#####
# General Helper Functions
#####

def _lookup_resource_type(assigned, root):
    """
    Returns ``ResourceType`` object

    :param str assigned: The string name of the assigned resource type
    :param root: RAML root object
    """
    res_types = root.resource_types
    if res_types:
        res_type_obj = [r for r in res_types if r.name == assigned]
        if res_type_obj:
            return res_type_obj[0]


# used for traits & resource nodes
def _map_param_unparsed_str_obj(param):
    return {
        "queryParameters": QueryParameter,
        "uriParameters": URIParameter,
        "formParameters": FormParameter,
        "baseUriParameters": URIParameter,
        "headers": Header
    }[param]


# TODO: refactor - this ain't pretty
# Note: this is only used in `create_node`
def _remove_duplicates(inherit_params, resource_params):
    ret = []
    if not resource_params:
        return inherit_params
    if isinstance(resource_params[0], Body):
        _params = [p.mime_type for p in resource_params]
    elif isinstance(resource_params[0], Response):
        _params = [p.code for p in resource_params]
    else:
        _params = [p.name for p in resource_params]

    for p in inherit_params:
        if isinstance(p, Body):
            if p.mime_type not in _params:
                ret.append(p)
        elif isinstance(p, Response):
            if p.code not in _params:
                ret.append(p)
        else:
            if p.name not in _params:
                ret.append(p)
    ret.extend(resource_params)
    return ret or None


#####
# Creating Named Parameter-like Objects
#####
def _create_base_param_obj(attribute_data, param_obj, config, errors, **kw):
    """Helper function to create a BaseParameter object"""
    objects = []

    for key, value in list(iteritems(attribute_data)):
        if param_obj is URIParameter:
            required = _get(value, "required", default=True)
        else:
            required = _get(value, "required", default=False)
        kwargs = dict(
            name=key,
            raw={key: value},
            desc=_get(value, "description"),
            display_name=_get(value, "displayName", key),
            min_length=_get(value, "minLength"),
            max_length=_get(value, "maxLength"),
            minimum=_get(value, "minimum"),
            maximum=_get(value, "maximum"),
            default=_get(value, "default"),
            enum=_get(value, "enum"),
            example=_get(value, "example"),
            required=required,
            repeat=_get(value, "repeat", False),
            pattern=_get(value, "pattern"),
            type=_get(value, "type", "string"),
            config=config,
            errors=errors
        )
        if param_obj is Header:
            kwargs["method"] = _get(kw, "method")

        item = param_obj(**kwargs)
        objects.append(item)

    return objects or None


# TODO: can I clean up/get rid of this? only used twice here
def _x_get_inherited_type_data(data, resource_types):
    inherited = _x_get_inherited_resource(data.get("type"), resource_types)
    return _get(inherited, data.get("type"))


# just parsing raw data, no objects
# TODO: can I clean up/get rid of this? only used once here
def _x_get_inherited_resource(res_name, resource_types):
    for resource in resource_types:
        if res_name == list(iterkeys(resource))[0]:
            return resource


def _get_inherited_item(current_items, item_name, res_types, method, data):
    resource = _x_get_inherited_type_data(data, res_types)
    res_data = _get(resource, method, {})

    method_ = _get(resource, method, {})
    m_data, r_data = _get_res_type_attribute(res_data, method_, item_name)
    items = dict(
        list(iteritems(current_items)) +
        list(iteritems(r_data)) +
        list(iteritems(m_data))
    )
    return items


def _get_res_type_attribute(res_data, method_data, item, default={}):
    method_level = _get(method_data, item, default)
    resource_level = _get(res_data, item, default)
    return method_level, resource_level


#####
# Ineloquently handling Trait & Resource Type parameter inheritance
#####

# <---[._get_attribute helpers]--->
def __get_method(attribute, method, raw_data):
    """Returns ``attribute`` defined at the method level, or ``None``."""
    ret = _get(raw_data, method, {})
    ret = _get(ret, attribute, {})
    return ret


def __get_resource(attribute, raw_data):
    """Returns ``attribute`` defined at the resource level, or ``None``."""
    return _get(raw_data, attribute, {})
# </---[._get_attribute helpers]--->


# <---[parser.create_node]--->
def _get_attribute(attribute, method, raw_data):
    """
    Returns raw data of desired named parameter object, e.g. \
    ``headers``, for both the resource-level data as well as
    method-level data.
    """
    if method:
        method_level = __get_method(attribute, method, raw_data)
    else:
        method_level = {}
    resource_level = __get_resource(attribute, raw_data)
    return OrderedDict(list(iteritems(method_level)) +
                       list(iteritems(resource_level)))


def __get_resource_type(attribute, root, type_, method):
    """Returns ``attribute`` defined in the resource type, or ``None``."""
    if type_ and root.resource_types:
        types = root.resource_types
        r_type = [r for r in types if r.name == type_]
        r_type = [r for r in r_type if r.method == method]
        if r_type:
            if hasattr(r_type[0], attribute):
                if getattr(r_type[0], attribute) is not None:
                    return getattr(r_type[0], attribute)
    return []


def __get_trait(attribute, root, is_):
    """Returns ``attribute`` defined in a trait, or ``None``."""

    if is_:
        traits = root.traits
        if traits:
            trait_objs = []
            for i in is_:
                trait = [t for t in traits if t.name == i]
                if trait:
                    if hasattr(trait[0], attribute):
                        if getattr(trait[0], attribute) is not None:
                            trait_objs.extend(getattr(trait[0], attribute))
            return trait_objs
    return []


#####
# Inheriting from Named Parameter Objects
# (attributes from already created objects)
####

def __map_inheritance(nodetype):
    return {
        "traits": __trait,
        "types": __resource_type,
        "method": __method,
        "resource": __resource,
        "parent": __parent,
        "root": __root
    }[nodetype]


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
    return __get_trait(item, root, is_)


def __resource_type(item, **kwargs):
    root = kwargs.get("root")
    type_ = kwargs.get("type_")
    method = kwargs.get("method")
    item = __map_attr(item)
    return __get_resource_type(item, root, type_, method)


def __method(item, **kwargs):
    method = kwargs.get("method")
    data = kwargs.get("data")
    return __get_method(item, method, data)


def __resource(item, **kwargs):
    data = kwargs.get("data")
    return __get_resource(item, data)


def __parent(item, **kwargs):
    parent = kwargs.get("parent")
    return __get_parent(item, parent)


def __root(item, **kwargs):
    root = kwargs.get("root")
    item = __map_attr(item)
    return getattr(root, item, None)


# Resources to iterate through objects (types, traits, etc) to
# inherit data from
def get_inherited(item, inherit_from=[], **kwargs):
    for nodetype in inherit_from:
        inherit_func = __map_inheritance(nodetype)
        inherited = inherit_func(item, **kwargs)
        if inherited:
            return inherited
    return None


#####
# Merging inherited values so child takes precendence
####

# confession: had to look up set theory!

def __is_scalar(item):
    scalar_props = [
        "type", "enum", "pattern", "minLength", "maxLength",
        "minimum", "maximum", "example", "repeat", "required",
        "default", "description", "usage", "schema", "example",
        "displayName"
    ]
    return item in scalar_props


def __get_sets(child, parent):
    child_keys = []
    parent_keys = []
    if child:
        child_keys = list(iterkeys(child))
    if parent:
        parent_keys = list(iterkeys(parent))
    child_diff = list(set(child_keys) - set(parent_keys))
    parent_diff = list(set(parent_keys) - set(child_keys))
    intersection = list(set(child_keys).intersection(parent_keys))
    opt_inters = [i for i in child_keys if str(i) + "?" in parent_keys]
    intersection = intersection + opt_inters

    return child, parent, child_diff, parent_diff, intersection


def _get_data_union(child, parent):
    # FIXME: should bring this over from config, not hard code
    methods = [
        'get', 'post', 'put', 'delete', 'patch', 'head', 'options',
        'trace', 'connect', 'get?', 'post?', 'put?', 'delete?', 'patch?',
        'head?', 'options?', 'trace?', 'connect?'
    ]
    union = {}
    child, parent, c_diff, p_diff, inters = __get_sets(child, parent)

    for i in c_diff:
        union[i] = child.get(i)
    for i in p_diff:
        if i in methods and not i.endswith("?"):
                union[i] = parent.get(i)
        if i not in methods:
            union[i] = parent.get(i)
    for i in inters:
        if __is_scalar(i):
            union[i] = child.get(i)
        else:
            _child = child.get(i, {})
            _parent = parent.get(i, {})
            union[i] = _get_data_union(_child, _parent)
    return union


#####
# Traits & Security Schemes
#####
# return list of traits/schemes if an assigned trait/secured_by is a dictionary
def _parse_assigned_dicts(items):
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
