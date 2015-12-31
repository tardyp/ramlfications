# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB

from __future__ import absolute_import, division, print_function


import copy
import re

import attr
from six import iteritems, iterkeys, itervalues


from .errors import InvalidRAMLError
from .parameters import (
    Documentation, URIParameter, SecurityScheme
)
from .raml import RootNode, ResourceNode, ResourceTypeNode, TraitNode
from .utils import load_schema

# Private utility functions
from ._utils.common_utils import _get
from ._utils.parser_utils import (
    _lookup_resource_type, _set_param_trait_object,
    _create_base_param_obj, _get_attribute, get_inherited, _get_data_union,
    _get_res_type_attribute, _get_inherited_attribute,
    _set_params, _parse_assigned_dicts
)

from .create_parameters import (
    create_response, create_bodies, create_responses,
    create_security_schemes, create_uri_params, create_param_objs,
    create_uri_params_node, create_base_uri_params
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
    root.resources = create_resources(root.raml_obj, [], root,
                                      parent=None)

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
        data = _get(raml, "baseUriParameters", {})
        params = _create_base_param_obj(data, URIParameter, config, errors)
        uri = _get(raml, "baseUri", "")
        return create_base_uri_params(uri, params, config, errors, raml=raml)

    def uri_params():
        data = _get(raml, "uriParameters", {})
        params = _create_base_param_obj(data, URIParameter, config, errors)
        uri = _get(raml, "baseUri", "")
        base = base_uri_params()
        return create_uri_params_node(uri, params, config, errors, base)

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
        return create_param_objs(header_data, method, root, "headers")

    def body(body_data):
        return create_bodies(body_data, method, root)

    def responses(resp_data):
        return create_responses(resp_data, root, method)

    def query_params(param_data):
        return create_param_objs(param_data, method, root, "queryParameters")

    def uri_params(param_data):
        return _set_param_trait_object(param_data, "uriParameters", root)

    def form_params(param_data):
        return create_param_objs(param_data, method, root, "formParameters")

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
        return create_param_objs(data, method, root, "queryParameters")

    def uri_params():
        return _set_param_trait_object(data, "uriParameters", root)

    def form_params():
        return create_param_objs(data, method, root, "formParameters")

    def base_uri_params():
        return create_param_objs(data, method, root, "baseUriParameters")

    def headers():
        return create_param_objs(data, method, root, "headers")

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

    def headers(data):
        inherit = False
        if _get(v, "type"):
            inherit = resource_types
        return create_param_objs(data, method(meth), root, "headers", inherit)

    def body(data):
        inherit = False
        if _get(v, "type"):
            inherit = resource_types
        body_objects = create_bodies(data, method(meth), root, inherit)

        return body_objects or None

    def responses(data):
        inherit = False
        if _get(v, "type"):
            inherit = resource_types
        return create_responses(data, root, method(meth), inherit)

    def uri_params(data):
        inherit = False
        if _get(v, "type"):
            inherit = resource_types
        return create_uri_params(data, v, method, root, inherit)

    def base_uri_params(data):
        return create_param_objs(data, method, root, "baseUriParameters",
                                 inherit)

    def query_params(data):
        return create_param_objs(data, method, root, "queryParameters",
                                 inherit)

    def form_params(data):
        return create_param_objs(data, method, root, "formParameters",
                                 inherit)

    def description():
        # prefer the resourceType method description
        if meth:
            method_attr = _get(v, meth)
            desc = _get(method_attr, "description")
            return desc or _get(v, "description")
        return _get(v, "description")

    def type_():
        return _get(v, "type")

    def method(meth):
        if not meth:
            return None
        if "?" in meth:
            return meth[:-1]
        return meth

    def optional():
        if meth:
            return "?" in meth

    def protocols(data):
        m, r = _get_res_type_attribute(v, data, "protocols", None)
        return m or r or root.protocols

    def is_(data):
        m, r = _get_res_type_attribute(v, data, "is", default=[])
        return m + r or None

    def traits(data):
        assigned = is_(data)
        if assigned:
            if root.traits:
                trait_objs = []
                for trait in assigned:
                    obj = [t for t in root.traits if t.name == trait]
                    if obj:
                        trait_objs.append(obj[0])
                return trait_objs or None

    def secured_by(data):
        m, r = _get_res_type_attribute(v, data, "securedBy", [])
        return m + r or None

    def security_schemes_(data):
        secured = secured_by(data)
        if secured:
            return create_security_schemes(secured, root)
        return None

    def wrap(key, data, meth, _v):
        return ResourceTypeNode(
            name=key,
            raw=data,
            root=root,
            headers=headers(data),
            body=body(data),
            responses=responses(data),
            uri_params=uri_params(data),
            base_uri_params=base_uri_params(data),
            query_params=query_params(data),
            form_params=form_params(data),
            media_type=_get(v, "mediaType"),
            desc=description(),
            type=type_(),
            method=method(meth),
            usage=_get(v, "usage"),
            optional=optional(),
            is_=is_(data),
            traits=traits(data),
            secured_by=secured_by(data),
            security_schemes=security_schemes_(data),
            display_name=_get(data, "displayName", key),
            protocols=protocols(data),
            errors=root.errors
        )

    inherit = False
    resource_types = _get(raml_data, "resourceTypes", [])
    if resource_types != []:
        inherit = resource_types
    resource_type_objects = []
    child_res_type_objects = []
    child_res_type_names = []

    for res in resource_types:
        for k, v in list(iteritems(res)):
            if isinstance(v, dict):
                if "type" in list(iterkeys(v)):
                    child_res_type_objects.append({k: v})
                    child_res_type_names.append(k)

                else:
                    for meth in list(iterkeys(v)):
                        if meth in accepted_methods:
                            method_data = _get(v, meth, {})
                            resource = wrap(k, method_data, meth, v)
                            resource_type_objects.append(resource)
            else:
                meth = None
                resource = wrap(k, {}, meth, v)
                resource_type_objects.append(resource)

    while child_res_type_objects:
        child = child_res_type_objects.pop()
        name = list(iterkeys(child))[0]
        data = list(itervalues(child))[0]
        parent = data.get("type")
        if parent in child_res_type_names:
            continue
        p_data = [r for r in resource_types if list(iterkeys(r))[0] == parent]
        p_data = p_data[0].get(parent)
        res_data = _get_data_union(data, p_data)

        for meth in list(iterkeys(res_data)):
            if meth in accepted_methods:
                method_data = _get(res_data, meth, {})
                comb_data = dict(list(iteritems(method_data)) +
                                 list(iteritems(res_data)))
                resource = ResourceTypeNode(
                    name=name,
                    raw=res_data,
                    root=root,
                    headers=headers(method_data),
                    body=body(method_data),
                    responses=responses(method_data),
                    uri_params=uri_params(comb_data),
                    base_uri_params=base_uri_params(comb_data),
                    query_params=query_params(method_data),
                    form_params=form_params(method_data),
                    media_type=_get(v, "mediaType"),
                    desc=description(),
                    type=_get(res_data, "type"),
                    method=method(meth),
                    usage=_get(res_data, "usage"),
                    optional=optional(),
                    is_=is_(res_data),
                    traits=traits(res_data),
                    secured_by=secured_by(res_data),
                    security_schemes=security_schemes_(res_data),
                    display_name=_get(method_data, "displayName", name),
                    protocols=protocols(res_data),
                    errors=root.errors
                )
                resource_type_objects.append(resource)

    return resource_type_objects or None


def create_resources(node, resources, root, parent):
    """
    Recursively traverses the RAML file via DFS to find each resource
    endpoint.

    :param dict node: Dictionary of node to traverse
    :param list resources: List of collected ``ResourceNode`` s
    :param RootNode root: The ``RootNode`` of the API
    :param ResourceNode parent: Parent ``ResourceNode`` of current ``node``
    :returns: List of :py:class:`.raml.ResourceNode` objects.
    """
    for k, v in list(iteritems(node)):
        if k.startswith("/"):
            avail = _get(root.config, "http_optional")
            methods = [m for m in avail if m in list(iterkeys(v))]
            if "type" in list(iterkeys(v)):
                assigned = _lookup_resource_type(_get(v, "type"), root)
                if hasattr(assigned, "method"):
                    if not assigned.optional:
                        methods.append(assigned.method)
                        methods = list(set(methods))
            if methods:
                for m in methods:
                    child = create_node(name=k,
                                        raw_data=v,
                                        method=m,
                                        parent=parent,
                                        root=root)
                    resources.append(child)
            # inherit resource type methods
            elif "type" in list(iterkeys(v)):
                if hasattr(assigned, "method"):
                    method = assigned.method
                else:
                    method = None
                child = create_node(name=k,
                                    raw_data=v,
                                    method=method,
                                    parent=parent,
                                    root=root)
                resources.append(child)
            else:
                child = create_node(name=k,
                                    raw_data=v,
                                    method=None,
                                    parent=parent,
                                    root=root)
                resources.append(child)
            resources = create_resources(child.raw, resources, root, child)
    return resources


def create_node(name, raw_data, method, parent, root):
    """
    Create a Resource Node object.

    :param str name: Name of resource node
    :param dict raw_data: Raw RAML data associated with resource node
    :param str method: HTTP method associated with resource node
    :param ResourceNode parent: Parent node object of resource node, if any
    :param RootNode api: API ``RootNode`` that the resource node is attached to
    :returns: :py:class:`.raml.ResourceNode` object
    """
    #####
    # Node attribute functions
    #####
    def path():
        """Set resource's relative URI path."""
        parent_path = ""
        if parent:
            parent_path = parent.path
        return parent_path + name

    def absolute_uri():
        """Set resource's absolute URI path."""
        uri = root.base_uri + res_path
        if res_protos:
            uri = uri.split("://")
            if len(uri) == 2:
                uri = uri[1]
            if root.protocols:
                _proto = list(set(root.protocols) & set(res_protos))
                # if resource protocols and root protocols share a protocol
                # then use that one
                if _proto:
                    uri = _proto[0].lower() + "://" + uri
                # if no shared protocols, use the first of the resource
                # protocols
                else:
                    uri = res_protos[0].lower() + "://" + uri
        return uri

    def protocols():
        """Set resource's supported protocols."""
        kwargs = dict(root=root,
                      is_=assigned_traits,
                      type_=assigned_type,
                      method=method,
                      data=raw_data,
                      parent=parent)
        # in order of preference:
        objects_to_inherit = [
            "method", "traits", "types", "resource", "parent"
        ]
        inherited = get_inherited("protocols", objects_to_inherit, **kwargs)
        default = [root.base_uri.split("://")[0].upper()]
        return inherited or default

    def headers():
        """Set resource's supported headers."""
        return create_param_objs(raw_data, method, root, "headers")

    def body():
        """Set resource's supported request/response body."""
        return create_bodies(raw_data, method, root)

    def responses():
        """Set resource's expected responses."""
        resps = _get_attribute("responses", method, raw_data)
        resp_objs = _get_inherited_attribute("responses", root, res_type,
                                             method, assigned_traits)
        resp_codes = [r.code for r in resp_objs]
        for k, v in list(iteritems(resps)):
            if k in resp_codes:
                resp = [r for r in resp_objs if r.code == k][0]
                index = resp_objs.index(resp)
                inherit_resp = resp_objs.pop(index)
                resp = create_response(k, v, root, method, inherit_resp)
                resp_objs.insert(index, resp)  # preserve order
            else:
                resp = create_response(k, v, root, method)
                resp_objs.append(resp)

        return resp_objs or None

    def uri_params():
        """Set resource's URI parameters."""
        kw = dict(type=assigned_type, traits=assigned_traits,
                  method=method, parent=parent)
        params = _set_params(raw_data, "uri_params", root, inherit=True, **kw)
        uri = absolute_uri()
        return create_uri_params_node(uri, params, root.config, root.errors,
                                      res_base_uri_params)

    def base_uri_params():
        """Set resource's base URI parameters."""
        kw = dict(type=assigned_type, traits=assigned_traits, method=method)
        params = _set_params(raw_data, "base_uri_params", root,
                             inherit=True, **kw)
        return create_base_uri_params(root.base_uri, params, root.config,
                                      root.errors, root=root)

    def query_params():
        return create_param_objs(raw_data, method, root, "queryParameters")

    def form_params():
        """Set resource's form parameters."""
        return create_param_objs(raw_data, method, root, "formParameters")

    def media_type_():
        """Set resource's supported media types."""
        if method is None:
            return None
        kw = dict(root=root,
                  is_=assigned_traits,
                  type_=assigned_type,
                  method=method,
                  data=raw_data)
        # in order of preference:
        objects_to_inherit = [
            "method", "traits", "types", "resource", "root"
        ]
        return get_inherited("mediaType", objects_to_inherit, **kw)

    def description():
        """Set resource's description."""
        desc = _get(raw_data, "description")
        try:
            desc = _get(_get(raw_data, method), "description")
            if desc is None:
                raise AttributeError
        except AttributeError:
            if res_type:
                assigned = _lookup_resource_type(assigned_type, root)
                try:
                    if assigned.method == method:
                        desc = assigned.description.raw
                except AttributeError:
                    pass
            else:
                desc = _get(raw_data, "description")
        return desc

    def is_():
        """Set resource's assigned trait names."""
        is_list = []
        res_level = _get(raw_data, "is")
        if res_level:
            assert isinstance(res_level, list), "Error parsing trait"
            is_list.extend(res_level)
        method_level = _get(raw_data, method, {})
        if method_level:
            method_level = _get(method_level, "is")
            if method_level:
                assert isinstance(method_level, list), "Error parsing trait"
                is_list.extend(method_level)
        return is_list or None

    def traits():
        """Set resource's assigned trait objects."""
        if assigned_traits and root.traits:
            trait_objs = []
            for trait in assigned_traits:
                obj = [t for t in root.traits if t.name == trait]
                if obj:
                    obj = copy.deepcopy(obj[0])
                    trait_objs.append(obj)
            return trait_objs or None

    # TODO: wow this function sucks.
    def type_():
        """Set resource's assigned resource type name."""
        method_data = _get(raw_data, method, {})
        assigned_type = _get(method_data, "type")
        if assigned_type:
            return assigned_type

        assigned_type = _get(raw_data, "type")
        return assigned_type

    def resource_type():
        """Set resource's assigned resource type objects."""
        if res_type and root.resource_types:
            res_types = root.resource_types
            type_obj = [r for r in res_types if r.name == assigned_type]
            type_obj = [r for r in type_obj if r.method == method]
            # such a hack - current implementation of replacing/substituting
            # `<<parameters>>` would otherwise overwrite the root traits.
            # damn python object referencing.
            # root.resource_types = copy.copy(root.resource_types)
            if type_obj:
                obj = copy.deepcopy(type_obj[0])
                return obj

    def secured_by():
        """
        Set resource's assigned security scheme names and related paramters.
        """
        if method is not None:
            method_level = _get(raw_data, method, {})
            if method_level:
                secured_by = _get(method_level, "securedBy")
                if secured_by:
                    return secured_by
        resource_level = _get(raw_data, "securedBy")
        if resource_level:
            return resource_level
        root_level = root.secured_by
        if root_level:
            return root_level

    def security_schemes_():
        """Set resource's assigned security scheme objects."""
        if assigned_sec_schemes:
            return create_security_schemes(assigned_sec_schemes, root)

    # removing some repeated function calls from within above closures
    res_path = path()
    res_is = is_()
    res_type = type_()
    secured = secured_by()
    assigned_sec_schemes = _parse_assigned_dicts(secured)
    assigned_traits = _parse_assigned_dicts(res_is)
    assigned_type = _parse_assigned_dicts(res_type)
    res_protos = protocols()
    res_base_uri_params = base_uri_params()

    node = ResourceNode(
        name=name,
        raw=raw_data,
        method=method,
        parent=parent,
        root=root,
        display_name=_get(raw_data, "displayName", name),
        path=res_path,
        absolute_uri=absolute_uri(),
        protocols=res_protos,
        headers=headers(),
        body=body(),
        responses=responses(),
        uri_params=uri_params(),
        base_uri_params=base_uri_params(),
        query_params=query_params(),
        form_params=form_params(),
        media_type=media_type_(),
        desc=description(),
        is_=res_is,
        traits=traits(),
        type=res_type,
        resource_type=resource_type(),
        secured_by=secured_by(),
        security_schemes=security_schemes_(),
        errors=root.errors
    )

    if res_type:
        node._parse_resource_type_parameters()
        node._inherit_type_test()
        node._inherit_type()
    if res_is:
        node._parse_trait_parameters()
        node._inherit_trait_objects()
    return node
