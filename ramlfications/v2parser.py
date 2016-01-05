# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function


import re

import attr
from six import iteritems, iterkeys, itervalues


from .errors import InvalidRAMLError
from .parameters import (
    Documentation, SecurityScheme
)
from .raml import RootNode, ResourceTypeNode, TraitNode
from .utils import load_schema

# Private utility functions
from ._utils.common_utils import _get

from .create_parameters import (
    create_bodies, create_responses,
    create_security_schemes, create_uri_params_res_types, create_param_objs,
    create_resource_type_objects, resolve_scalar
)


__all__ = ["parse_raml"]


def parse_raml(loaded_raml, config):
    """
    Parse loaded RAML file into RAML/Python objects.

    :param RAMLDict loaded_raml: OrderedDict of loaded RAML file
    :returns: :py:class:`.raml.RootNode` object.
    :raises: :py:class:`.errors.InvalidRAMLError` when RAML file is invalid
    """
    validate = str(_get(config, "validate")).lower() == 'true'

    # Postpone validating the root node until the end; otherwise,
    # we end up with duplicate validation exceptions.
    attr.set_run_validators(False)

    root = create_root(loaded_raml, config)
    attr.set_run_validators(validate)

    root.security_schemes = create_sec_schemes(root.raml_obj, root)
    root.traits = create_traits(root.raml_obj, root)
    root.resource_types = create_resource_types(root.raml_obj, root)

    if validate:
        attr.validate(root)  # need to validate again for root node

        if root.errors:
            raise InvalidRAMLError(root.errors)
    return root


def create_root(raml, config):
    """
    Creates a Root Node based off of the RAML's root section.

    :param RAMLDict raml: loaded RAML file
    :returns: :py:class:`.raml.RootNode` object with API root attributes set
    """

    errors = []

    def protocols():
        explicit_protos = _get(raml, "protocols")
        implicit_protos = re.findall(r"(https|http)", base_uri())
        implicit_protos = [p.upper() for p in implicit_protos]

        return explicit_protos or implicit_protos or None

    def base_uri():
        base_uri = _get(raml, "baseUri", "")
        if "{version}" in base_uri:
            base_uri = base_uri.replace("{version}",
                                        str(_get(raml, "version")))
        return base_uri

    def base_uri_params():
        uri = _get(raml, "baseUri", "")
        return create_param_objs(raml, None, config, errors,
                                 "baseUriParameters", uri=uri, raml=raml)

    def uri_params():
        uri = _get(raml, "baseUri", "")
        base = base_uri_params()
        return create_param_objs(raml, None, config, errors, "uriParameters",
                                 uri=uri, base=base)

    def docs():
        d = _get(raml, "documentation", [])
        assert isinstance(d, list), "Error parsing documentation"
        docs = [Documentation(_get(i, "title"), _get(i, "content")) for i in d]
        return docs or None

    def schemas():
        _schemas = _get(raml, "schemas")
        if not _schemas:
            return None
        schemas = []
        for schema in _schemas:
            value = load_schema(list(itervalues(schema))[0])
            schemas.append({list(iterkeys(schema))[0]: value})
        return schemas or None

    return RootNode(
        raml_obj=raml,
        raw=raml,
        title=_get(raml, "title"),
        version=_get(raml, "version"),
        protocols=protocols(),
        base_uri=base_uri(),
        base_uri_params=base_uri_params(),
        uri_params=uri_params(),
        media_type=_get(raml, "mediaType"),
        documentation=docs(),
        schemas=schemas(),
        config=config,
        secured_by=_get(raml, "securedBy"),
        errors=errors
    )


def create_sec_schemes(raml_data, root):
    """
    Parse security schemes into ``SecurityScheme`` objects

    :param dict raml_data: Raw RAML data
    :param RootNode root: Root Node
    :returns: list of :py:class:`.parameters.SecurityScheme` objects
    """
    def _map_object_types(item):
        return {
            "headers": headers,
            "body": body,
            "responses": responses,
            "queryParameters": query_params,
            "uriParameters": uri_params,
            "formParameters": form_params,
            "usage": usage,
            "mediaType": media_type,
            "protocols": protocols,
            "documentation": documentation,
        }[item]

    def headers(header_data):
        return create_param_objs(header_data, method, root.config, root.errors,
                                 "headers")

    def body(body_data):
        return create_bodies(body_data, method, root)

    def responses(resp_data):
        return create_responses(resp_data, root, method)

    def query_params(param_data):
        return create_param_objs(param_data, method, root.config, root.errors,
                                 "queryParameters")

    def uri_params(param_data):
        return create_param_objs(param_data, None, root.config, root.errors,
                                 "uriParameters")

    def form_params(param_data):
        return create_param_objs(param_data, method, root.config, root.errors,
                                 "formParameters")

    def usage(desc_by_data):
        return _get(desc_by_data, "usage")

    def media_type(desc_by_data):
        return _get(desc_by_data, "mediaType")

    def protocols(desc_by_data):
        return _get(desc_by_data, "protocols")

    def documentation(desc_by_data):
        d = _get(desc_by_data, "documentation", [])
        assert isinstance(d, list), "Error parsing documentation"
        docs = [Documentation(_get(i, "title"), _get(i, "content")) for i in d]
        return docs or None

    def set_property(node, obj, node_data):
        func = _map_object_types(obj)
        item_objs = func({obj: node_data})
        setattr(node, func.__name__, item_objs)

    def initial_wrap(key, data):
        return SecurityScheme(
            name=key,
            raw=data,
            type=_get(data, "type"),
            described_by=_get(data, "describedBy", {}),
            desc=_get(data, "description"),
            settings=_get(data, "settings"),
            config=root.config,
            errors=root.errors
        )

    def final_wrap(node):
        for obj, node_data in list(iteritems(node.described_by)):
            set_property(node, obj, node_data)
        return node

    method = None
    schemes = _get(raml_data, "securitySchemes", [])
    scheme_objs = []
    for s in schemes:
        name = list(iterkeys(s))[0]
        data = list(itervalues(s))[0]
        node = initial_wrap(name, data)
        node = final_wrap(node)
        scheme_objs.append(node)
    return scheme_objs or None


def create_traits(raml_data, root):
    """
    Parse traits into ``Trait`` objects.

    :param dict raml_data: Raw RAML data
    :param RootNode root: Root Node
    :returns: list of :py:class:`.raml.TraitNode` objects
    """
    def query_params():
        return create_param_objs(data, method, root.config, root.errors,
                                 "queryParameters")

    def uri_params():
        return create_param_objs(data, None, root.config, root.errors,
                                 "uriParameters")

    def form_params():
        return create_param_objs(data, method, root.config, root.errors,
                                 "formParameters")

    def base_uri_params():
        return create_param_objs(data, method, root.config, root.errors,
                                 "baseUriParameters")

    def headers():
        return create_param_objs(data, method, root.config, root.errors,
                                 "headers")

    def body():
        return create_bodies(data, method, root)

    def responses():
        return create_responses(data, root, method)

    def wrap(key, data):
        return TraitNode(
            name=key,
            raw=data,
            root=root,
            query_params=query_params(),
            uri_params=uri_params(),
            form_params=form_params(),
            base_uri_params=base_uri_params(),
            headers=headers(),
            body=body(),
            responses=responses(),
            desc=_get(data, "description"),
            media_type=_get(data, "mediaType"),
            usage=_get(data, "usage"),
            protocols=_get(data, "protocols"),
            errors=root.errors
        )

    traits = _get(raml_data, "traits", [])
    trait_objects = []
    method = None
    for trait in traits:
        name = list(iterkeys(trait))[0]
        data = list(itervalues(trait))[0]
        trait_objects.append(wrap(name, data))
    return trait_objects or None


def create_resource_types(raml_data, root):
    """
    Parse resourceTypes into ``ResourceTypeNode`` objects.

    :param dict raml_data: Raw RAML data
    :param RootNode root: Root Node
    :returns: list of :py:class:`.raml.ResourceTypeNode` objects
    """
    # TODO: move this outside somewhere - config?
    accepted_methods = _get(root.config, "http_optional")

    #####
    # Set ResourceTypeNode attributes
    #####

    def headers(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("headers", method_data,
                                            resource_data, method(meth),
                                            root, _is)

    def body(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("body", method_data, resource_data,
                                            method(meth), root, _is)

    def responses(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("responses", method_data,
                                            resource_data, method(meth),
                                            root, _is)

    def uri_params(method_data, resource_data):
        inherit = False
        if _get(v, "type"):
            inherit = resource_types
        return create_uri_params_res_types(method_data, resource_data, method,
                                           root, inherit)

    def base_uri_params(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("baseUriParameters", method_data,
                                            resource_data, method(meth),
                                            root, _is)

    def query_params(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("queryParameters", method_data,
                                            resource_data, method(meth),
                                            root, _is)

    def form_params(method_data, resource_data):
        _is = is_(method_data, resource_data)
        return create_resource_type_objects("formParameters", method_data,
                                            resource_data, method(meth),
                                            root, _is)

    def description(method_data, resource_data):
        m, r = resolve_scalar(method_data, resource_data, "description",
                              default=None)
        return m or r or None

    def type_(method_data, resource_data):
        m, r = resolve_scalar(method_data, resource_data, "type", None)
        return m or r or None

    def method(meth):
        if not meth:
            return None
        if "?" in meth:
            return meth[:-1]
        return meth

    def optional():
        if meth:
            return "?" in meth

    def protocols(method_data, resource_data):
        m, r = resolve_scalar(method_data, resource_data, "protocols",
                              default=None)
        return m or r or root.protocols

    def is_(method_data, resource_data):
        m, r = resolve_scalar(method_data, resource_data, "is", default=[])
        return m + r or None

    def traits(method_data, resource_data):
        assigned = is_(method_data, resource_data)
        if assigned:
            if root.traits:
                trait_objs = []
                for trait in assigned:
                    if isinstance(trait, dict):
                        trait = list(iterkeys(trait))
                    objs = [t for t in root.traits if t.name in trait]
                    if objs:
                        for o in objs:
                            trait_objs.append(o)
                return trait_objs or None

    def secured_by(method_data, resource_data):
        m, r = resolve_scalar(method_data, resource_data, "securedBy",
                              default=[])
        return m + r or None

    def security_schemes_(method_data, resource_data):
        secured = secured_by(method_data, resource_data)
        if secured:
            return create_security_schemes(secured, root)
        return None

    def wrap(key, method_data, meth, resource_data):
        return ResourceTypeNode(
            name=key,
            raw=method_data,
            root=root,
            headers=headers(method_data, resource_data),
            body=body(method_data, resource_data),
            responses=responses(method_data, resource_data),
            uri_params=uri_params(method_data, resource_data),
            base_uri_params=base_uri_params(method_data, resource_data),
            query_params=query_params(method_data, resource_data),
            form_params=form_params(method_data, resource_data),
            media_type=_get(resource_data, "mediaType"),
            desc=description(method_data, resource_data),
            type=type_(method_data, resource_data),
            method=method(meth),
            usage=_get(resource_data, "usage"),
            optional=optional(),
            is_=is_(method_data, resource_data),
            traits=traits(method_data, resource_data),
            secured_by=secured_by(method_data, resource_data),
            security_schemes=security_schemes_(method_data, resource_data),
            display_name=_get(method_data, "displayName", key),
            protocols=protocols(method_data, resource_data),
            errors=root.errors
        )

    resource_types = _get(raml_data, "resourceTypes", [])
    resource_type_objects = []

    for res in resource_types:
        for k, v in list(iteritems(res)):
            if isinstance(v, dict):
                for meth in list(iterkeys(v)):
                    if meth in accepted_methods:
                        method_data = _get(v, meth, {})
                        resource = wrap(k, method_data, meth, v)
                        resource_type_objects.append(resource)
            else:
                meth = None
                resource = wrap(k, {}, meth, v)
                resource_type_objects.append(resource)

    return resource_type_objects or None
