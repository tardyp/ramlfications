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
from ._utils.common_utils import (
    _get, __get_inherited_trait_data, merge_dicts, __resource_type_data
)
from ._utils.parameter_utils import (
    _get_attribute, _get_scheme, _remove_duplicates, _get_inherited_item,
    _replace_str_attr
)
from ._utils.parser_utils import resolve_scalar


#####
# Public functions
#####
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
    return _create_uri_params(uri, params, param_type, conf, errs, base=base,
                              root=root, raml=raml)


def create_body(mime_type, data, root, method):
    """
    Create a ``.parameters.Body`` object.
    """
    raw = {mime_type: data}
    form_params = create_param_objs(data, method, root.config, root.errors,
                                    "formParameters")
    return Body(
        mime_type=mime_type,
        raw=raw,
        schema=load_schema(_get(data, "schema")),
        example=load_schema(_get(data, "example")),
        # TODO: should create form param objects?
        form_params=form_params,
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
        body = create_body(k, v, root, method)
        body_objects.append(body)
    return body_objects or None


def create_response(code, data, root, method, inherited_resp=None):
    """Returns a ``.parameters.Response`` object"""
    headers = _create_response_headers(data, method, root)
    body = _create_response_body(data, root, method)
    desc = _get(data, "description", None)
    if inherited_resp:
        if inherited_resp.headers:
            headers = _remove_duplicates(inherited_resp.headers, headers)
        if inherited_resp.body:
            body = _remove_duplicates(inherited_resp.body, body)
        if inherited_resp.desc and not desc:
            desc = inherited_resp.desc

    # when substituting `<<parameters>>`, everything gets turned into
    # a string/unicode. Try to make it an int, and if not, validate.py
    # will certainly catch it.
    if isinstance(code, basestring):
        try:
            code = int(code)
        except ValueError:
            pass

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


# TODO: not used anymore in v2parser.py
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


def create_resource_objects(param, data, v, method, root, is_, uri=None):
    """
    Returns a list of ``.parameter`` objects as designated by ``param``
    from the given ``data``. Will parse data the object inherits if
    assigned another resource type and/or trait(s).

    :param str param: RAML-specified paramter, e.g. "resources", \
        "queryParameters"
    :param dict data: method-level ``param`` data
    :param dict v: resource-type-level ``param`` data
    :param str method: designated method
    :param root: ``.raml.RootNode`` object
    :param list is_: list of assigned traits, either ``str`` or
        ``dict`` mapping key: value pairs to ``<<parameter>>`` values
    """
    if is_:
        trait_data = __trait_data(param, root, is_)
        for t in trait_data:
            data = merge_dicts(data, t)
        for i in is_:
            if data and isinstance(i, dict):
                json_data = json.dumps(data)
                param_type = list(iterkeys(i))[0]
                param_data = list(itervalues(i))[0]
                for key, value in list(iteritems(param_data)):
                    json_data = _replace_str_attr(key, value, json_data)
                if isinstance(json_data, str):
                    data = json.loads(json_data, object_pairs_hook=OrderedDict)
    m_type, r_type = resolve_scalar(data, v, "type", None)
    type_ = m_type or r_type or None
    if type_:
        inherited = __resource_type_data(param, root, type_, method)
        params = _get(data, param, {})
        params = merge_dicts(params, inherited)
        if params and isinstance(type_, dict):
            json_data = json.dumps(params)
            param_type = type_
            param_data = list(itervalues(param_type))[0]
            for key, value in list(iteritems(param_data)):
                json_data = _replace_str_attr(key, value, json_data)
            if isinstance(json_data, str):
                params = json.loads(json_data, object_pairs_hook=OrderedDict)
        if param == "body":
            param_objs = __create_res_type_body_objects(params, method, root,
                                                        type_)
        elif param == "responses":
            param_objs = __create_res_type_response_objects(params, method,
                                                            root, type_)
        else:
            object_name = __map_object(param)
            param_objs = __create_base_param_obj(params, object_name,
                                                 root.config, root.errors,
                                                 method=method)
    else:
        if param == "body":
            param_objs = create_bodies(data, method, root)
        elif param == "responses":
            param_objs = create_responses(data, root, method)
        else:
            param_objs = create_param_objs(data, method, root.config,
                                           root.errors, param, uri=uri)
    return param_objs or None


# TODO: FIXME in order to use in parser.py
def create_uri_params_res_types(data, raw_data, method, root, inherit=False):
    m_data, r_data = resolve_scalar(data, raw_data, "uriParameters", {})
    param_data = dict(list(iteritems(m_data)) + list(iteritems(r_data)))
    if inherit:
        param_data = __get_inherited_type_params(raw_data, "uriParameters",
                                                 param_data, inherit)

    return __create_base_param_obj(param_data, URIParameter, root.config,
                                   root.errors, method=method)


############################
#
# Private, helper functions
#
############################
# TODO: clean me! i'm ugly!
def _create_uri_params(uri, params, param_type, conf, errs, base=None,
                       root=None, raml=None):
    declared = []
    param_names = []
    to_ignore = []
    if params:
        param_names = [p.name for p in params]
        declared.extend(params)
    if base:
        base_params = [p for p in base if p.name not in param_names]
        base_param_names = [p.name for p in base_params]
        param_names.extend(base_param_names)

        if param_type == "uriParameters":
            to_ignore.extend(base_param_names)
    if raml:
        if param_type == "uriParameters":
            _to_ignore = list(iterkeys(_get(raml, "baseUriParameters", {})))
            to_ignore.extend(_to_ignore)
        if param_type == "baseUriParameters":
            _to_ignore = list(iterkeys(_get(raml, "uriParameters", {})))
            to_ignore.extend(_to_ignore)
    if root:
        if root.uri_params:
            _params = root.uri_params
            root_uri = [p for p in _params if p.name not in param_names]
            declared.extend(root_uri)
            root_uri_names = [p.name for p in root_uri]
            param_names.extend(root_uri_names)
            if param_type == "baseUriParameters":
                to_ignore.extend(root_uri_names)
        if root.base_uri_params:
            _params = root.base_uri_params
            root_base_uri = [p for p in _params if p.name not in param_names]
            root_base_uri_names = [p.name for p in root_base_uri]
            param_names.extend(root_base_uri_names)
            if param_type == "uriParameters":
                to_ignore.extend(root_base_uri_names)
    return __preserve_uri_order(uri, params, conf, errs, declared, to_ignore)


def _create_response_headers(data, method, root):
    """
    Create ``.parameters.Header`` objects for a ``.parameters.Response``
    object.
    """
    headers = _get(data, "headers", default={})

    header_objects = __create_base_param_obj(headers, Header, root.config,
                                             root.errors, method=method)
    return header_objects or None


def _create_response_body(data, root, method):
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
            _body = create_body(key, raw, root, method)
            body_list.append(_body)
    if no_mime_body_data:
        _body = create_body(root.media_type, no_mime_body_data, root, method)
        body_list.append(_body)

    return body_list or None


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


def __add_missing_uri_params(missing, param_objs, config, errors, to_ignore):
    for m in missing:
        # no need to create a URI param for version
        # or should we?
        if m in to_ignore:
            continue
        if m == "version":
            continue
        data = {m: {"type", "string"}}
        _param = __create_base_param_obj(data, URIParameter, config, errors)
        param_objs.append(_param[0])
    return param_objs


# preserve order of URI and Base URI parameters
# used for RootNode, ResourceNode
def __preserve_uri_order(path, param_objs, config, errors, declared=[],
                         to_ignore=[]):
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
                                              config, errors, to_ignore)

    sorted_params = []
    for p in params:
        _param = [i for i in param_objs if i.name == p]
        if _param:
            sorted_params.append(_param[0])
    return sorted_params or None


#####
# Utility helper functions
#####
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


# Get objects for inheritance
# <--[.create_uri_params_res_types helpers]-->
def __get_inherited_type_params(data, attribute, params, resource_types):
    inherited = __get_inherited_resource(data.get("type"), resource_types)
    inherited = _get(inherited, data.get("type"))

    inherited_params = _get(inherited, attribute, {})

    return dict(list(iteritems(params)) +
                list(iteritems(inherited_params)))


def __get_inherited_resource(res_name, resource_types):
    for resource in resource_types:
        if isinstance(resource, dict):
            if res_name == list(iterkeys(resource))[0]:
                return resource
# </--[.create_uri_params_res_types helpers]-->


#####
# Resource Type data parsing -> objects
#####

# <---[.create_resource_type_object helpers]--->
def __trait_data(attr, root, _is):
    if not _is:
        return {}
    raml = _get(root.raw, "traits")
    return __get_inherited_trait_data(attr, raml, _is, root)


def __create_res_type_response_objects(data, method, root, to_replace):
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


def __create_res_type_body_objects(data, method, root, to_replace):
    if not data:
        return []
    if to_replace and isinstance(to_replace, dict):
        json_data = json.dumps(data)
        for k, v in list(iteritems(to_replace)):
            json_data = _replace_str_attr(json_data, v, k)
        data = json.loads(json_data, object_pairs_hook=OrderedDict)

    body_objs = []
    for k, v in list(iteritems(data)):
        body = create_body(k, v, root, method)
        body_objs.append(body)
    return body_objs
# </---[.create_resource_type_object helpers]--->
