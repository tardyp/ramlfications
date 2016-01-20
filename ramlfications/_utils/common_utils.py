# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function


from six import iterkeys


#####
# General Helper functions
#####

# general
def _get(data, item, default=None):
    """
    Helper function to catch empty mappings in RAML. If item is optional
    but not in the data, or data is ``None``, the default value is returned.

    :param data: RAML data
    :param str item: RAML key
    :param default: default value if item is not in dict
    :param bool optional: If RAML item is optional or needs to be defined
    :ret: value for RAML key
    """
    try:
        return data.get(item, default)
    except AttributeError:
        return default


def __get_inherited_res_type_data(attr, types, name, method, root):
    if isinstance(name, dict):
        name = list(iterkeys(name))[0]
    res_type_raml = [r for r in types if list(iterkeys(r))[0] == name]
    if res_type_raml:
        res_type_raml = _get(res_type_raml[0], name, {})
        raw = _get(res_type_raml, method, None)
        if not raw:
            if method:
                raw = _get(res_type_raml, method + "?", {})
        attribute_data = _get(raw, attr, {})
        if res_type_raml.get("type"):
            inherited = __resource_type_data(attr, root,
                                             res_type_raml.get("type"),
                                             method)
            attribute_data = merge_dicts(attribute_data, inherited)
        return attribute_data
    return {}


def __get_inherited_trait_data(attr, traits, name, root):
    names = []
    for n in name:
        if isinstance(n, dict):
            n = list(iterkeys(n))[0]
        names.append(n)

    trait_raml = [t for t in traits if list(iterkeys(t))[0] in names]
    trait_data = []
    for n in names:
        for t in trait_raml:
            t_raml = _get(t, n, {})
            attribute_data = _get(t_raml, attr, {})
            trait_data.append({attr: attribute_data})
    return trait_data


def __resource_type_data(attr, root, res_type, method):
    if not res_type:
        return {}
    raml = _get(root.raw, "resourceTypes")
    if raml:
        return __get_inherited_res_type_data(attr, raml, res_type,
                                             method, root)


def merge_dicts(child, parent, path=[]):
    "merges parent into child"
    if path is None:
        path = []
    if not parent:
        return child
    for key in parent:
        if key in child:
            if isinstance(child[key], dict) and isinstance(parent[key], dict):
                merge_dicts(child[key], parent[key], path + [str(key)])
            elif child[key] == parent[key]:
                pass  # same leaf value
            else:
                print('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            child[key] = parent[key]
    return child
