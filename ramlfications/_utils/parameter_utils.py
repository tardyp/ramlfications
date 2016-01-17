# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

import re

try:
    from collections import OrderedDict
except ImportError:  # NOCOV
    from ordereddict import OrderedDict

from six import iterkeys, iteritems

from .common_utils import _get
from ramlfications import parameter_tags
from ramlfications.parameters import Body, Response


# pattern for `<<parameter>>` substitution
PATTERN = r'(<<\s*)(?P<pname>{0}\b[^\s|]*)(\s*\|?\s*(?P<tag>!\S*))?(\s*>>)'


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


# TODO: not sure I need this here ... I'm essentially creating another
#       object rather than inherit/assign, like with types & traits
def _get_scheme(item, root):
    schemes = root.raw.get("securitySchemes", [])
    for s in schemes:
        if item == list(iterkeys(s))[0]:
            return s


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


# <--[._get_inherited_item helpers] -->
# TODO: can I clean up/get rid of this? only used twice here
def __get_inherited_type_data(data, resource_types):
    inherited = __get_inherited_resource(data.get("type"), resource_types)
    return _get(inherited, data.get("type"))


# just parsing raw data, no objects
# TODO: can I clean up/get rid of this? only used once here
def __get_inherited_resource(res_name, resource_types):
    for resource in resource_types:
        if res_name == list(iterkeys(resource))[0]:
            return resource


def __get_res_type_attribute(res_data, method_data, item, default={}):
    method_level = _get(method_data, item, default)
    resource_level = _get(res_data, item, default)
    return method_level, resource_level
# </--[._get_inherited_item helpers] -->


def _get_inherited_item(current_items, item_name, res_types, method, data):
    resource = __get_inherited_type_data(data, res_types)
    res_data = _get(resource, method, {})

    method_ = _get(resource, method, {})
    m_data, r_data = __get_res_type_attribute(res_data, method_, item_name)
    items = dict(
        list(iteritems(current_items)) +
        list(iteritems(r_data)) +
        list(iteritems(m_data))
    )
    return items


def _replace_str_attr(param, new_value, current_str):
    """
    Replaces ``<<parameters>>`` with their assigned value, processed with \
    any function tags, e.g. ``!pluralize``.
    """
    p = re.compile(PATTERN.format(param))
    ret = re.findall(p, current_str)
    if not ret:
        return current_str
    for item in ret:
        to_replace = "".join(item[0:3]) + item[-1]
        tag_func = item[3]
        if tag_func:
            tag_func = tag_func.strip("!")
            tag_func = tag_func.strip()
            func = getattr(parameter_tags, tag_func)
            if func:
                new_value = func(new_value)
        current_str = current_str.replace(to_replace, str(new_value), 1)
    return current_str
