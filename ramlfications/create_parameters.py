# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

import json
import re

try:
    from collections import OrderedDict
except ImportError:  # pragma: no cover
    from ordereddict import OrderedDict


from six import iteritems, itervalues, iterkeys

from .config import MEDIA_TYPES
from .parameters import (
    Response, Header, Body, QueryParameter, URIParameter, FormParameter,
    SecurityScheme
)
from .utils import load_schema
from . import parameter_tags
from ._utils.common_utils import _get
from ._utils.parser_utils import (
    _remove_duplicates, _get_attribute,
    _get_inherited_item, _get_scheme,
)

#####
# Public functions
#####


#####
# TODO: fixme clean me
def create_uri_params(uri, params, conf, errs, base=None, root=None,
                      raml=None):
    declared = []
    if base:
        declared = [p.name for p in base]
    if raml:
        declared = _get(raml, "uriParameters", {})
        declared = list(iterkeys(declared))
    if root:
        if root.uri_params:
            declared = [p.name for p in root.uri_params]
        if root.base_uri_params:
            declared.extend([p.name for p in root.base_uri_params])
    return __preserve_uri_order(uri, params, conf, errs, declared)


def _create_uri_params(uri, params, conf, errs, base=None, root=None,
                       raml=None):
    declared = []
    if base:
        declared = [p.name for p in base]
    if raml:
        declared = _get(raml, "uriParameters", {})
        declared = list(iterkeys(declared))
    if root:
        if root.uri_params:
            declared = [p.name for p in root.uri_params]
        if root.base_uri_params:
            declared.extend([p.name for p in root.base_uri_params])
    return __preserve_uri_order(uri, params, conf, errs, declared)


def create_param_objs(data, method, conf, errs, param_type, types=False,
                      uri=False, base=None, root=None, raml=None):
    """
    General function to create ``.parameters`` objects. Returns a list of
    ``.parameters`` objects or ``None``.

    :param dict data: data to create object
    :param str method: method associated with object, if necessary
    :param root: RootNode of the API
    :param str param_type: string name of object
    :param types: a list of ``.raml.ResourceTypeNode`` to inherit \
        from, if any.
    :param str uri: URI of the node, to preserve order of URI params
    :param base: base UriParameter objects to preserve order of URI \
        parameters and to create any that are not explicitly declared
    :param root: RootNode object to preserve order of URI parameters and \
        to create any that are not explicitly declared
    :param raml: raw RAML data to preserve order of URI parameters and \
        to create any that are not explicitly declared
    """
    params = _get_attribute(param_type, method, data)
    if types:
        params = _get_inherited_item(params, param_type, types,
                                     method, data)
    object_name = __map_object(param_type)
    params = __create_base_param_obj(params, object_name, conf, errs,
                                     method=method)
    if not uri:
        return params or None
    return _create_uri_params(uri, params, conf, errs, base=base,
                              root=root, raml=raml)


# TODO: can I clean up/get rid of this? only used when setting URI params
def _set_params(data, attr_name, root, inherit=False, **kw):
    params, inherit_objs, parent_params, root_params = [], [], [], []

    # base_uri_params -> baseUriParameters
    unparsed = __map_parsed_str(attr_name)
    # baseUriParameters -> URIParameter
    param_class = __map_object(unparsed)

    # baseUriParameters -> raw data on method & resource level
    raw_data = _get_attribute(unparsed, kw.get("method"), data)

    # create params based on raw data _params
    params = __create_base_param_obj(raw_data, param_class, root.config,
                                     root.errors)

    if params is None:
        params = []

    if inherit:
        # get inherited objects
        inherit_objs = _get_inherited_objects(attr_name, root,
                                              kw.get("type"),
                                              kw.get("method"),
                                              kw.get("traits"))

    if kw.get("parent"):
        # get parent objects
        parent_params = getattr(kw.get("parent"), attr_name, [])
    if root:
        # get root objects
        root_params = getattr(root, attr_name, [])

    # remove duplicates
    to_clean = (params, inherit_objs, parent_params, root_params)
    return __remove_duplicates(to_clean)


def create_body(mime_type, data, root):
    """
    Create a ``.parameters.Body`` object.
    """
    raw = {mime_type: data}
    return Body(
        mime_type=mime_type,
        raw=raw,
        schema=load_schema(_get(data, "schema")),
        example=load_schema(_get(data, "example")),
        # TODO: should create form param objects?
        form_params=_get(data, "formParameters"),
        config=root.config,
        errors=root.errors
    )


def create_bodies(data, method, root, resource_types=False):
    """
    Returns a list of ``.parameters.Body`` objects.
    """
    bodies = _get_attribute("body", method, data)
    if resource_types:
        bodies = _get_inherited_item(bodies, "body", resource_types,
                                     method, data)
    body_objects = []
    for k, v in list(iteritems(bodies)):
        if v is None:
            continue
        body = create_body(k, v, root)
        body_objects.append(body)
    return body_objects or None


def create_response(code, data, root, method, inherited_resp=None):
    """Returns a ``.parameters.Response`` object"""
    headers = _create_response_headers(data, method, root)
    body = _create_response_body(data, root)
    desc = _get(data, "description", None)
    if inherited_resp:
        if inherited_resp.headers:
            headers = _remove_duplicates(inherited_resp.headers, headers)
        if inherited_resp.body:
            body = _remove_duplicates(inherited_resp.body, body)
        if inherited_resp.desc and not desc:
            desc = inherited_resp.desc

    return Response(
        code=code,
        raw={code: data},
        method=method,
        desc=desc,
        headers=headers,
        body=body,
        config=root.config,
        errors=root.errors
    )


def _create_response_headers(data, method, root):
    """
    Create ``.parameters.Header`` objects for a ``.parameters.Response``
    object.
    """
    headers = _get(data, "headers", default={})

    header_objects = __create_base_param_obj(headers, Header, root.config,
                                             root.errors, method=method)
    return header_objects or None


def _create_response_body(data, root):
    """
    Create ``.parameters.Body`` objects for a ``.parameters.Response``
    object.
    """
    body = _get(data, "body", default={})
    body_list = []
    no_mime_body_data = {}
    for key, spec in list(iteritems(body)):
        if key not in MEDIA_TYPES:
            # if a root mediaType was defined, the response body
            # may omit the mime_type definition
            if key in ('schema', 'example'):
                no_mime_body_data[key] = load_schema(spec) if spec else {}
        else:
            # spec might be '!!null'
            raw = spec or body
            _body = create_body(key, raw, root)
            body_list.append(_body)
    if no_mime_body_data:
        _body = create_body(root.media_type, no_mime_body_data, root)
        body_list.append(_body)

    return body_list or None


def create_responses(data, root, method, resource_types=None):
    """
    Returns a list of ``.parameters.Response`` objects.
    """
    response_objects = []
    responses = _get_attribute("responses", method, data)
    if resource_types:
        responses = _get_inherited_item(responses, "responses", resource_types,
                                        method, data)

    for key, value in list(iteritems(responses)):

        response = create_response(key, value, root, method)
        response_objects.append(response)
    return sorted(response_objects, key=lambda x: x.code) or None


def create_security_scheme(scheme, data, root):
    """Create a ``.parameters.SecurityScheme`` object."""
    return SecurityScheme(
        name=scheme,
        raw=data,
        type=_get(data, "type"),
        described_by=_get(data, "describedBy"),
        desc=_get(data, "description"),
        settings=_get(data, "settings"),
        config=root.config,
        errors=root.errors
    )


def create_security_schemes(secured_by, root):
    """
    Returns a list of ``.parameters.SecurityScheme`` objects.
    """
    secured_objects = []
    for item in secured_by:
        assigned_scheme = _get_scheme(item, root)
        if assigned_scheme:
            data = list(itervalues(assigned_scheme))[0]
            scheme = create_security_scheme(item, data, root)
            secured_objects.append(scheme)
    return secured_objects


############################
#
# Private, helper functions
#
############################

def __create_base_param_obj(attribute_data, param_obj, config, errors, **kw):
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


# TODO: can I clean up/get rid of this? only used once here
def __check_if_exists(param, ret_list):
    if isinstance(param, Body):
        param_name_list = [p.mime_type for p in ret_list]
        if param.mime_type not in param_name_list:
            ret_list.append(param)
            param_name_list.append(param.mime_type)

    else:
        param_name_list = [p.name for p in ret_list]
        if param.name not in param_name_list:
            ret_list.append(param)
            param_name_list.append(param.name)
    return ret_list


# TODO: refactor - this ain't pretty
def __remove_duplicates(to_clean):
    # order: resource, inherited, parent, root
    ret = []

    for param_set in to_clean:
        if param_set:
            for p in param_set:
                ret = __check_if_exists(p, ret)
    return ret or None


def __add_missing_uri_params(missing, param_objs, config, errors):
    for m in missing:
        # no need to create a URI param for version
        # or should we?
        if m == "version":
            continue
        data = {m: {"type", "string"}}
        _param = __create_base_param_obj(data, URIParameter, config, errors)
        param_objs.append(_param[0])
    return param_objs


# preserve order of URI and Base URI parameters
# used for RootNode, ResourceNode
def __preserve_uri_order(path, param_objs, config, errors, declared=[]):
    # if this is hit, RAML shouldn't be valid anyways.
    if isinstance(path, list):
        path = path[0]

    pattern = "\{(.*?)\}"
    params = re.findall(pattern, path)
    if not param_objs:
        param_objs = []
    # if there are URI parameters in the path but were not declared
    # inline, we should create them.
    # TODO: Probably shouldn't do it in this function, though...
    if len(params) > len(param_objs):
        if len(param_objs) > 0:
            param_names = [p.name for p in param_objs]
            missing = [p for p in params if p not in param_names]
        else:
            missing = params[::]
        # exclude any (base)uri params if already declared
        missing = [p for p in missing if p not in declared]
        param_objs = __add_missing_uri_params(missing, param_objs,
                                              config, errors)

    sorted_params = []
    for p in params:
        _param = [i for i in param_objs if i.name == p]
        if _param:
            sorted_params.append(_param[0])
    return sorted_params or None


#####
# Utility helper functions
#####
def __map_parsed_str(parsed):
    """
    Returns ``ramlfications`` attribute of an object to its raw string
    name mirrored in RAML.

    e.g. ``base_uri_params`` -> ``baseUriParameters``
    """
    name = parsed.split("_")[:-1]
    name.append("parameters")
    name = [n.capitalize() for n in name]
    name = "".join(name)
    return name[0].lower() + name[1:]


def __map_object(param_type):
    """
    Map raw string name from RAML to mirrored ``ramlfications`` object
    """
    return {
        "headers": Header,
        "body": Body,
        "responses": Response,
        "uriParameters": URIParameter,
        "baseUriParameters": URIParameter,
        "queryParameters": QueryParameter,
        "formParameters": FormParameter
    }[param_type]


#####
# Get objects for inheritance
#####


def _get_inherited_objects(attribute, root, type_, method, is_):
    """
    Returns a list of ``TraitNode`` and ``ResourceTypeNode`` objects
    that is inherited if objects have an attribute (e.g. ``responses``)
    that the child object shares.
    """
    type_objs, trait_objs = [], []
    if type_ and root.resource_types:
        type_objs = __get_resource_type(attribute, root, type_, method)
    if is_ and root.traits:
        trait_objs = __get_trait(attribute, root, is_)
    return type_objs + trait_objs


def __get_resource_type(attribute, root, type_, method):
    """
    Returns ``attribute`` (e.g. ``responses``) defined in the resource
    type, or an empty ``list``.
    """
    types = root.resource_types
    r_type = [r for r in types if r.name == type_]
    r_type = [r for r in r_type if r.method == method]
    if r_type:
        if getattr(r_type[0], attribute) is not None:
            return getattr(r_type[0], attribute)
    return []


def __get_trait(attribute, root, is_):
    """
    Returns list of ``attribute`` (e.g. ``responses``) defined in a
    trait, or an empty ``list``.
    """
    trait_objs = []
    for i in is_:
        trait = [t for t in root.traits if t.name == i]
        if trait:
            if getattr(trait[0], attribute) is not None:
                trait_objs.extend(getattr(trait[0], attribute))
    return trait_objs


# <--FIXME: URI params for resource types-->
# TODO: FIXME in order to use in parser.py
def create_uri_params_res_types(data, raw_data, method, root, inherit=False):
    m_data, r_data = resolve_scalar(data, raw_data, "uriParameters",
                                    default={})
    # param_data = _get_attribute("uriParameters", method, raw_data)
    param_data = dict(list(iteritems(m_data)) + list(iteritems(r_data)))
    if inherit:
        param_data = __get_inherited_type_params(raw_data, "uriParameters",
                                                 param_data, inherit)

    return __create_base_param_obj(param_data, URIParameter, root.config,
                                   root.errors, method=method)


def __get_inherited_type_params(data, attribute, params, resource_types):
    inherited = __get_inherited_resource(data.get("type"), resource_types)
    inherited = _get(inherited, data.get("type"))

    inherited_params = _get(inherited, attribute, {})

    return dict(list(iteritems(params)) +
                list(iteritems(inherited_params)))


def __get_inherited_resource(res_name, resource_types):
    for resource in resource_types:
        if res_name == list(iterkeys(resource))[0]:
            return resource

# </--FIXME: URI params for resource types-->


#####
# trying something new:
# for any child node that inherits shit:
# 1. get the raw data of the inherited
# 2. parse for `<<parameters>>` and func tags
# 3. merge data/data union
# 4. create the actual object
#####

# copied over from parameter_utils.py
PATTERN = r'(<<\s*)(?P<pname>{0}\b[^\s|]*)(\s*\|?\s*(?P<tag>!\S*))?(\s*>>)'


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


def _rename_me(attr, root, res_type, method):
    if not res_type:
        return {}
    raml = _get(root.raw, "resourceTypes")
    return _get_inherited_res_type_data(attr, raml, res_type, method, root)


def _trait_data(attr, root, _is):
    if not _is:
        return {}
    raml = _get(root.raw, "traits")
    return _get_inherited_trait_data(attr, raml, _is, root)


def _get_inherited_trait_data(attr, traits, name, root):
    if isinstance(name, dict):
        name = list(iterkeys(name))

    trait_raml = [t for t in traits if list(iterkeys(t))[0] in name]
    trait_data = []
    for n in name:
        for t in trait_raml:
            t_raml = _get(t, n, {})
            attribute_data = _get(t_raml, attr, {})
            trait_data.append({attr: attribute_data})
    return trait_data


def _get_inherited_res_type_data(attr, types, name, method, root):
    if isinstance(name, dict):
        name = list(iterkeys(name))[0]
    res_type_raml = [r for r in types if list(iterkeys(r))[0] == name]
    if res_type_raml:
        res_type_raml = _get(res_type_raml[0], name, {})
        raw = _get(res_type_raml, method, None)
        if not raw:
            raw = _get(res_type_raml, method + "?", {})
        attribute_data = _get(raw, attr, {})
        if res_type_raml.get("type"):
            inherited = _rename_me(attr, root, res_type_raml.get("type"),
                                   method)
            attribute_data = merge_dicts(attribute_data, inherited)
        return attribute_data
    return {}


def _x_create_response_objects(data, method, root, to_replace):
    if not data:
        return []
    if to_replace and isinstance(to_replace, dict):
        json_data = json.dumps(data)
        for k, v in list(iteritems(to_replace)):
            json_data = _replace_str_attr(json_data, v, k)
        data = json.loads(json_data, object_pairs_hook=OrderedDict)

    resp_objs = []
    for k, v in list(iteritems(data)):
        resp = create_response(k, v, root, method)
        resp_objs.append(resp)
    return sorted(resp_objs, key=lambda x: x.code)


def _x_create_body_objects(data, method, root, to_replace):
    if not data:
        return []
    if to_replace and isinstance(to_replace, dict):
        json_data = json.dumps(data)
        for k, v in list(iteritems(to_replace)):
            json_data = _replace_str_attr(json_data, v, k)
        data = json.loads(json_data, object_pairs_hook=OrderedDict)

    body_objs = []
    for k, v in list(iteritems(data)):
        body = create_body(k, v, root)
        body_objs.append(body)
    return body_objs


def _x_create_header_objects(data, method, root, to_replace):
    if not data:
        return []
    if to_replace and isinstance(to_replace, dict):
        json_data = json.dumps(data)
        for k, v in list(iteritems(to_replace)):
            json_data = _replace_str_attr(json_data, v, k)
        data = json.loads(json_data, object_pairs_hook=OrderedDict)

    kw = dict(method=method)
    return __create_base_param_obj(data, Header, root.config,
                                   root.errors, **kw)


def create_resource_type_objects(param, data, v, method, root, is_):
    if is_:
        trait_data = _trait_data(param, root, is_)
        for t in trait_data:
            data = merge_dicts(data, t)
    if _get(v, "type"):
        inherited = _rename_me(param, root, _get(v, "type"), method)
        params = _get(data, param, {})
        params = merge_dicts(params, inherited, ret={})
        if param == "body":
            params = _x_create_body_objects(params, method, root,
                                            _get(v, "type"))
        elif param == "responses":
            params = _x_create_response_objects(params, method, root,
                                                _get(v, "type"))
        else:
            object_name = __map_object(param)
            params = __create_base_param_obj(params, object_name, root.config,
                                             root.errors, method=method)
    else:
        if param == "body":
            params = create_bodies(data, method, root)
        elif param == "responses":
            params = create_responses(data, root, method)
        else:
            params = create_param_objs(data, method, root.config, root.errors,
                                       param)
    return params or None


def merge_dicts(data, inherited_data, ret={}):
    if not isinstance(data, dict):
        return data
    data_keys = list(iterkeys(data))
    inherited_keys = list(iterkeys(inherited_data))

    data_only = [d for d in data_keys if d not in inherited_keys]
    inherit_only = [i for i in inherited_keys if i not in data_keys]
    both = [d for d in data_keys if d in inherited_keys]

    for d in data_only:
        ret[d] = data.get(d)
    for i in inherit_only:
        ret[i] = inherited_data.get(i)

    for b in both:
        b_data = data.get(b)
        b_inherited = inherited_data.get(b)
        ret[b] = {}
        ret[b] = merge_dicts(b_data, b_inherited, ret[b])

    return ret


def resolve_scalar(method_data, resource_data, item, default):
    method_level = _get(method_data, item, default)
    resource_level = _get(resource_data, item, default)
    return method_level, resource_level
