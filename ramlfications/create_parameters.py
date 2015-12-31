# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function


from six import iteritems, itervalues, iterkeys

from .config import MEDIA_TYPES
from .parameters import (
    Response, Header, Body, QueryParameter, URIParameter, FormParameter,
    SecurityScheme
)
from .utils import load_schema

from ._utils.common_utils import _get
from ._utils.parser_utils import (
    _create_base_param_obj, _remove_duplicates, _get_attribute,
    _get_inherited_item, _get_scheme, _get_res_type_attribute,
    __get_inherited_type_params, __find_set_object, _preserve_uri_order
)

#####
# Public functions
#####


# TODO: FIXME in order to use in parser.py
def create_uri_params(data, raw_data, method, root, inherit=False):
    m_data, r_data = _get_res_type_attribute(raw_data, data, "uriParameters")
    # param_data = _get_attribute("uriParameters", method, raw_data)
    param_data = dict(list(iteritems(m_data)) + list(iteritems(r_data)))
    if inherit:
        param_data = __get_inherited_type_params(raw_data, "uriParameters",
                                                 param_data, inherit)
    return __find_set_object(param_data, "uriParameters", root)


def create_param_objs(data, method, root, param_type, resource_types=False):
    """
    General function to create ``.parameters`` objects. Returns a list of
    ``.parameters`` objects or ``None``.

    :param dict data: data to create object
    :param str method: method associated with object, if necessary
    :param root: RootNode of the API
    :param str param_type: string name of object
    :param resource_types: a list of ``.raml.ResourceTypeNode`` to inherit \
        from, if any.
    """
    params = _get_attribute(param_type, method, data)
    if resource_types:
        params = _get_inherited_item(params, param_type, resource_types,
                                     method, data)
    object_name = __map_object(param_type)
    params = _create_base_param_obj(params, object_name, root.config,
                                    root.errors, method=method)
    return params or None


def create_body(mime_type, data, root):
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
    """Create response header objects."""
    headers = _get(data, "headers", default={})

    header_objects = _create_base_param_obj(headers, Header, root.config,
                                            root.errors, method=method)
    return header_objects or None


def _create_response_body(data, root):
    """Create response body objects."""
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
    secured_objects = []
    for item in secured_by:
        assigned_scheme = _get_scheme(item, root)
        if assigned_scheme:
            data = list(itervalues(assigned_scheme))[0]
            scheme = create_security_scheme(item, data, root)
            secured_objects.append(scheme)
    return secured_objects


#####
# Private, helper functions
#####
def __map_object(param_type):
    """Map raw string name to object"""
    return {
        "headers": Header,
        "body": Body,
        "responses": Response,
        "uriParameters": URIParameter,
        "baseUriParameters": URIParameter,
        "queryParameters": QueryParameter,
        "formParameters": FormParameter
    }[param_type]


def create_uri_params_node(uri, params, config, errors, base_params=None):
    declared = []
    if base_params:
        declared = [p.name for p in base_params]
    return _preserve_uri_order(uri, params, config, errors, declared)


def create_base_uri_params(uri, params, config, errors, root=None, raml=None):
    declared = []
    if raml:
        declared = _get(raml, "uriParameters", {})
        declared = list(iterkeys(declared))
    if root:
        if root.uri_params:
            declared = [p.name for p in root.uri_params]
        if root.base_uri_params:
            declared.extend([p.name for p in root.base_uri_params])
    return _preserve_uri_order(uri, params, config, errors, declared)
