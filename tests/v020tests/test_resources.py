# -*- coding: utf-8 -*-
# Copyright (c) 2015 Spotify AB
from __future__ import absolute_import, division, print_function

import os

import pytest

from ramlfications.v2parser import parse_raml
from ramlfications.config import setup_config
from ramlfications._helpers import load_file

from tests.base import V020EXAMPLES, assert_not_set


@pytest.fixture(scope="session")
def api():
    ramlfile = os.path.join(V020EXAMPLES, "resources.raml")
    loaded_raml = load_file(ramlfile)
    conffile = os.path.join(V020EXAMPLES, "test_config.ini")
    config = setup_config(conffile)
    return parse_raml(loaded_raml, config)


def test_create_resources(api):
    res = api.resources
    assert len(res) == 3


def test_get_widgets(api):
    res = api.resources[0]

    assert res.name == "/widgets"
    assert res.display_name == "several-widgets"
    assert res.method == "get"
    desc = "[Get Several Widgets](https://developer.example.com/widgets/)\n"
    assert res.description.raw == desc
    assert res.protocols == ["HTTPS"]
    assert res.path == "/widgets"
    uri = "https://{subDomain}.example.com/v1/{external_party}/widgets"
    assert res.absolute_uri == uri
    assert res.media_type == "application/json"
    not_set = [
        "body", "parent", "traits", "is_", "responses", "uri_params",
        "base_uri_params"
    ]
    assert_not_set(res, not_set)


def test_post_gizmos(api):
    res = api.resources[1]

    assert res.name == "/gizmos"
    assert res.display_name == "several-gizmos"
    assert res.method == "post"
    assert res.description.raw == "Post several gizmos"
    assert res.protocols == ["HTTPS"]
    assert res.media_type == "application/json"
    assert res.path == "/gizmos"
    uri = "https://{subDomain}.example.com/v1/{external_party}/gizmos"
    assert res.absolute_uri == uri
    not_set = [
        "body", "parent", "traits", "is_", "responses", "uri_params",
        "base_uri_params", "query_params"
    ]
    assert_not_set(res, not_set)


def test_post_thingys(api):
    res = api.resources[2]

    assert res.name == "/thingys"
    assert res.display_name == "several-thingys"
    assert res.method == "post"
    assert res.description.raw == "Post several thingys"
    assert res.protocols == ["HTTPS"]
    assert res.media_type == "application/json"
    assert res.path == "/thingys"
    uri = "https://{subDomain}.example.com/v1/{external_party}/thingys"
    assert res.absolute_uri == uri
    not_set = [
        "parent", "traits", "is_", "responses", "uri_params",
        "base_uri_params", "query_params", "form_params"
    ]
    assert_not_set(res, not_set)


def test_headers(api):
    # get /widgets
    res = api.resources[0]
    assert len(res.headers) == 2

    h = res.headers[0]
    assert h.name == "Accept"
    assert h.display_name == "Accept"
    assert h.description.raw == "An Acceptable header for get method"
    assert h.method == "get"
    assert h.type == "string"
    not_set = [
        "example", "default", "min_length", "max_length", "minimum",
        "maximum", "enum", "repeat", "pattern", "required"
    ]
    assert_not_set(h, not_set)

    h = res.headers[1]
    assert h.name == "X-Widgets-Header"
    assert h.display_name == "X-Widgets-Header"
    assert h.description.raw == "just an extra header for funsies"
    assert h.method == "get"
    assert h.type == "string"
    not_set = [
        "example", "default", "min_length", "max_length", "minimum",
        "maximum", "enum", "repeat", "pattern", "required"
    ]
    assert_not_set(h, not_set)


def test_query_params(api):
    # get /widgets
    res = api.resources[0]
    assert len(res.query_params) == 1

    q = res.query_params[0]
    assert q.name == "ids"
    assert q.display_name == "Example Widget IDs"
    assert q.description.raw == "A comma-separated list of IDs"
    assert q.required
    assert q.type == "string"
    assert q.example == "widget1,widget2,widget3"
    not_set = [
        "default", "min_length", "max_length", "minimum",
        "maximum", "enum", "repeat", "pattern"
    ]
    assert_not_set(q, not_set)


def test_form_params(api):
    # post /gizmos
    res = api.resources[1]
    assert len(res.form_params) == 1

    ids = res.form_params[0]
    assert ids.name == "ids"
    assert ids.display_name == "Example Gizmo IDs"
    assert ids.type == "string"
    assert ids.description.raw == "A comma-separated list of IDs"
    assert ids.required
    assert ids.example == "gizmo1,gizmo2,gizmo3"
    not_set = [
        "default", "min_length", "max_length", "minimum",
        "maximum", "enum", "repeat", "pattern"
    ]
    assert_not_set(ids, not_set)


def test_body(api):
    # post /thingys
    res = api.resources[2]
    assert len(res.body) == 3

    json = res.body[0]
    assert json.mime_type == "application/json"
    assert json.schema == {"name": "string"}
    assert json.example == {"name": "Example Name"}

    xml = res.body[1]
    assert xml.mime_type == "application/xml"
    # TODO: parse XML schemas, since xmltodict doesn't seem to like schemas

    form = res.body[2]
    assert form.mime_type == "application/x-www-form-urlencoded"
    assert len(form.form_params) == 1

    f = form.form_params[0]
    assert f.name == "foo"
    assert f.display_name == "Foo"
    assert f.type == "string"
    assert f.description.raw == "The Foo Form Field"
    assert f.min_length == 5
    assert f.max_length == 50
    assert f.default == "foobar"
    not_set = [
        "minimum", "maximum", "enum", "repeat", "pattern", "required"
    ]
    assert_not_set(f, not_set)
