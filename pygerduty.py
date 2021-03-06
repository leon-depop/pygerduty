import urllib
import urllib2
import urlparse

try:
    import json
except ImportError:
    import simplejson as json


__author__ = "Gary M. Josack <gary@dropbox.com>"
__version__ = "0.12"


# TODO:
# Support for older Integration API. (Trigger, Ack, Resolve)
# Support for Log Entries
# Support for Reports


class Error(Exception):
    pass


class BadRequest(Error):
    def __init__(self, payload, *args, **kwargs):
        # Error Reponses don't always contain all fields.
        # Sane defaults must be set.
        self.code = payload["error"].get('code', 99999)
        self.errors = payload["error"].get('errors', [])
        self.message = payload["error"].get('message', "")

        Error.__init__(self, *args, **kwargs)

    def __str__(self):
        return "%s (%s): %s" % (
            self.message, self.code, self.errors)


class NotFound(Error):
    pass


class Collection(object):

    def __init__(self, pagerduty, base_container=None):
        self.name = getattr(self, "name", False) or _lower(self.__class__.__name__)
        self.sname = getattr(self, "sname", False) or _singularize(self.name)
        self.container = (getattr(self, "container", False) or
                          globals()[_upper(self.sname)])

        self.pagerduty = pagerduty
        self.base_container = base_container

    def create(self, **kwargs):
        path = "%s" % self.name
        if self.base_container:
            path = "%s/%s/%s" % (
                self.base_container.collection.name,
                self.base_container.id, self.name)

        data = {self.sname: {}}

        # requester_id needs to be up a level
        if "requester_id" in kwargs:
            data["requester_id"] = kwargs["requester_id"]
            del kwargs["requester_id"]

        data[self.sname] = kwargs

        response = self.pagerduty.request("POST", path, data=json.dumps(data))
        return self.container(self, **response.get(self.sname, {}))

    def update(self, entity_id, **kwargs):
        path = "%s/%s" % (self.name, entity_id)
        if self.base_container:
            path = "%s/%s/%s/%s" % (
                self.base_container.collection.name,
                self.base_container.id, self.name, entity_id)

        data = {self.sname: {}}

        # requester_id needs to be up a level
        if "requester_id" in kwargs:
            data["requester_id"] = kwargs["requester_id"]
            del kwargs["requester_id"]

        data[self.sname] = kwargs

        response = self.pagerduty.request("PUT", path, data=json.dumps(data))
        return self.container(self, **response.get(self.sname, {}))

    def _list_response(self, response):
        entities = []
        for entity in response.get(self.name, []):
            entities.append(self.container(self, **entity))
        return entities

    def list(self, **kwargs):
        path = self.name
        if self.base_container:
            path = "%s/%s/%s" % (
                self.base_container.collection.name,
                self.base_container.id, self.name)
        response = self.pagerduty.request("GET", path, query_params=kwargs)
        return self._list_response(response)

    def count(self, **kwargs):
        path = "%s/count" % self.name
        response = self.pagerduty.request("GET", path, query_params=kwargs)
        return response.get("total", None)

    def show(self, entity_id, **kwargs):
        path = "%s/%s" % (self.name, entity_id)
        if self.base_container:
            path = "%s/%s/%s/%s" % (
                self.base_container.collection.name,
                self.base_container.id, self.name, entity_id)

        response = self.pagerduty.request(
            "GET", path, query_params=kwargs)
        return self.container(self, **response.get(self.sname, {}))

    def delete(self, entity_id):
        path = "%s/%s" % (self.name, entity_id)
        if self.base_container:
            path = "%s/%s/%s/%s" % (
                self.base_container.collection.name,
                self.base_container.id, self.name, entity_id)

        response = self.pagerduty.request("DELETE", path)
        return response


class MaintenanceWindows(Collection):
    def list(self, **kwargs):
        path = self.name

        if "type" in kwargs:
            path = "%s/%s" % (self.name, kwargs["type"])
            del kwargs["type"]

        response = self.pagerduty.request("GET", path, query_params=kwargs)
        return self._list_response(response)

    def update(self, entity_id, **kwargs):
        path = "%s/%s" % (self.name, entity_id)
        response = self.pagerduty.request("PUT", path, data=json.dumps(kwargs))
        return self.container(self, **response.get(self.sname, {}))


class Incidents(Collection):
    def update(self, requester_id, *args):
        path = "%s" % self.name
        data = {"requester_id": requester_id, self.name: args}
        response = self.pagerduty.request("PUT", path, data=json.dumps(data))
        return self.container(self, **response.get(self.sname, {}))


class Services(Collection):
    def disable(self, entity_id, requester_id):
        path = "%s/%s/disable" % (self.name, entity_id)
        data = {"requester_id": requester_id}
        response = self.pagerduty.request("PUT", path, data=json.dumps(data))
        return response

    def enable(self, entity_id):
        path = "%s/%s/enable" % (self.name, entity_id)
        response = self.pagerduty.request("PUT", path, data="")
        return response

    def regenerate_key(self, entity_id):
        path = "%s/%s/regenerate_key" % (self.name, entity_id)
        response = self.pagerduty.request("POST", path, data="")
        return self.container(self, **response.get(self.sname, {}))


class Alerts(Collection):
    pass


class Overrides(Collection):
    pass


class Entries(Collection):
    pass


class Schedules(Collection):
    pass


class Users(Collection):
    pass


class NotificationRules(Collection):
    pass


class ContactMethods(Collection):
    pass


class EmailFilters(Collection):
    pass


class Container(object):
    def __init__(self, collection, **kwargs):
        # This class depends on the existance on the _kwargs attr.
        # Use object's __setattr__ to initialize.
        object.__setattr__(self, "_kwargs", {})

        self.collection = collection
        self.pagerduty = collection.pagerduty

        def _check_kwarg(key, value):
            if isinstance(value, dict):
                container = globals().get(_upper(_singularize(key)))
                if container is not None and issubclass(container, Container):
                    _collection = globals().get(_upper(_pluralize(key)),
                                                Collection)
                    return container(_collection(self.pagerduty), **value)
                else:
                    return Container(Collection(self.pagerduty), **value)
            return value

        for key, value in kwargs.iteritems():
            if isinstance(value, list):
                self._kwargs[key] = []
                for item in value:
                    sname = _singularize(key)
                    self._kwargs[key].append(_check_kwarg(sname, item))
            else:
                self._kwargs[key] = _check_kwarg(key, value)

    def __getattr__(self, name):
        if name not in self._kwargs:
            raise AttributeError(name)
        return self._kwargs[name]

    def __setattr__(self, name, value):
        if name not in self._kwargs:
            return object.__setattr__(self, name, value)
        self._kwargs[name] = value

    def __str__(self):
        attrs = ["%s=%s" % (k, repr(v)) for k, v in self._kwargs.iteritems()]
        return "<%s: %s>" % (self.__class__.__name__, ", ".join(attrs))

    def __repr__(self):
        return str(self)


class Incident(Container):
    pass


class Alert(Container):
    pass


class EmailFilter(Container):
    pass


class MaintenanceWindow(Container):
    pass


class Override(Container):
    pass


class NotificationRule(Container):
    pass


class ContactMethod(Container):
    pass


class EscalationPolicy(Container):
    pass


class ScheduleLayer(Container):
    pass


class Service(Container):
    def __init__(self, *args, **kwargs):
        Container.__init__(self, *args, **kwargs)
        self.email_filters = EmailFilters(self.pagerduty, self)


class Schedule(Container):
    def __init__(self, *args, **kwargs):
        Container.__init__(self, *args, **kwargs)
        self.overrides = Overrides(self.pagerduty, self)
        self.users = Users(self.pagerduty, self)
        self.entries = Entries(self.pagerduty, self)


class User(Container):
    def __init__(self, *args, **kwargs):
        Container.__init__(self, *args, **kwargs)
        self.notification_rules = NotificationRules(self.pagerduty, self)
        self.contact_methods = ContactMethods(self.pagerduty, self)


class Entry(Container):
    pass


class PagerDuty(object):
    def __init__(self, subdomain, api_token, timeout=10):
        self.subdomain = subdomain
        self.api_token = api_token
        self._host = "%s.pagerduty.com" % subdomain
        self._api_base = "https://%s/api/v1/" % self._host
        self.timeout = timeout

        # Collections
        self.incidents = Incidents(self)
        self.alerts = Alerts(self)
        self.schedules = Schedules(self)
        self.users = Users(self)
        self.services = Services(self)
        self.maintenance_windows = MaintenanceWindows(self)

    def request(self, method, path, query_params=None, data=None,
                extra_headers=None):
        headers = {
            "Content-type": "application/json",
            "Authorization": "Token token=%s" % self.api_token,
        }

        if extra_headers:
            headers.update(extra_headers)

        if query_params is not None:
            query_params = urllib.urlencode(query_params)

        url = urlparse.urljoin(self._api_base, path)
        if query_params:
            url += "?%s" % query_params

        request = urllib2.Request(url, data=data, headers=headers)
        request.get_method = lambda: method.upper()

        try:
            response = urllib2.urlopen(request).read()
        except urllib2.HTTPError, err:
            if err.code / 100 == 2:
                response = err.read()
            elif err.code == 400:
                raise BadRequest(json.loads(err.read()))
            elif err.code == 404:
                raise NotFound("Endpoint (%s) Not Found." % path)
            else:
                raise
        try:
            response = json.loads(response)
        except ValueError:
            response = None

        return response


def _lower(string):
    """Custom lower string function.

    Examples:
        FooBar -> foo_bar
    """
    if not string:
        return ""

    new_string = [string[0].lower()]
    for char in string[1:]:
        if char.isupper():
            new_string.append("_")
        new_string.append(char.lower())

    return "".join(new_string)


def _upper(string):
    """Custom upper string function.

    Examples:
        foo_bar -> FooBar
    """
    return string.title().replace("_", "")


def _singularize(string):
    """Hacky singularization function."""

    if string.endswith("ies"):
        return string[:-3] + "y"
    if string.endswith("s"):
        return string[:-1]
    return string


def _pluralize(string):
    """Hacky pluralization function."""

    if string.endswith("y"):
        return string[:-1] + "ies"
    if not string.endswith("s"):
        return string + "s"
    return string
