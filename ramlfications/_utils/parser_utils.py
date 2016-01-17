# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function


from .common_utils import _get


def resolve_scalar(method_data, resource_data, item, default):
    """
    Returns tuple of method-level and resource-level data for a desired
    attribute (e.g. ``description``).  Used for ``scalar`` -type attributes.
    """
    method_level = _get(method_data, item, default)
    resource_level = _get(resource_data, item, default)
    return method_level, resource_level
