# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

import re

from six import iterkeys

from ramlfications import parameter_tags
from ramlfications.parameters import Body, Response


# pattern for `<<parameter>>` substitution
PATTERN = r'(<<\s*)(?P<pname>{0}\b[^\s|]*)(\s*\|?\s*(?P<tag>!\S*))?(\s*>>)'


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
