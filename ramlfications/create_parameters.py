# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function

from six import iteritems

from .config import MEDIA_TYPES
from .parameters import (
    Response, Header, Body, QueryParameter, URIParameter, FormParameter
)
from .utils import load_schema

from ._utils.common_utils import _get
from ._utils.parser_utils import (
    _create_base_param_obj, _remove_duplicates, _get_attribute,
    _get_inherited_item
)


# TODO: FIXME in order to use in parser.py
def create_uri_params(data, method, root, resource_types=False):
    params = _get_attribute("uriParameters", method, data)
    if resource_types:
        params = _get_inherited_item(params, "uriParameters", resource_types,
                                     method, data)
    params = _create_base_param_obj(params, URIParameter, root.config,
                                    root.errors, method=method)
    return params or None


def create_base_uri_params(data, method, root, resource_types=False):
    params = _get_attribute("baseUriParameters", method, data)
    if resource_types:
        params = _get_inherited_item(params, "baseUriParameters",
                                     resource_types, method, data)
    params = _create_base_param_obj(params, URIParameter, root.config,
                                    root.errors, method=method)
    return params or None


def create_query_params(data, method, root, resource_types=False):
    params = _get_attribute("queryParameters", method, data)
    if resource_types:
        params = _get_inherited_item(params, "queryParameters", resource_types,
                                     method, data)

    params = _create_base_param_obj(params, QueryParameter, root.config,
                                    root.errors, method=method)
    return params or None


def create_form_params(data, method, root, resource_types=False):
    params = _get_attribute("formParameters", method, data)
    if resource_types:
        params = _get_inherited_item(params, "formParameters", resource_types,
                                     method, data)
    params = _create_base_param_obj(params, FormParameter, root.config,
                                    root.errors, method=method)
    return params or None


def create_headers(data, method, root, resource_types=False):
    headers = _get_attribute("headers", method, data)
    if resource_types:
        headers = _get_inherited_item(headers, "headers", resource_types,
                                      method, data)
    headers = _create_base_param_obj(headers, Header, root.config,
                                     root.errors, method=method)
    return headers or None


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
