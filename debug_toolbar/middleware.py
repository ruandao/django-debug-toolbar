"""
Debug Toolbar middleware
"""

import re
import threading
import time

from functools import lru_cache

import debug_toolbar

try:
    from django.urls import reverse, resolve, Resolver404
except ImportError: # django < 2.0
    from django.core.urlresolvers import reverse, resolve, Resolver404
from django.conf import settings
from django.utils.module_loading import import_string

from debug_toolbar import settings as dt_settings
from debug_toolbar.cache import cache
from debug_toolbar.toolbar import DebugToolbar

_HTML_TYPES = ("text/html", "application/xhtml+xml", "application/json")


def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    if request.META.get("REMOTE_ADDR", None) not in settings.INTERNAL_IPS:
        return False

    return bool(settings.DEBUG)


@lru_cache()
def get_show_toolbar():
    # If SHOW_TOOLBAR_CALLBACK is a string, which is the recommended
    # setup, resolve it to the corresponding callable.
    func_or_path = dt_settings.get_config()["SHOW_TOOLBAR_CALLBACK"]
    if isinstance(func_or_path, str):
        return import_string(func_or_path)
    else:
        return func_or_path


class DebugToolbarMiddleware:
    """
    Middleware to set up Debug Toolbar on incoming request and render toolbar
    on outgoing response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Decide whether the toolbar is active for this request. Don't render
        # the toolbar during AJAX requests.
        show_toolbar = get_show_toolbar()
        if not show_toolbar(request):
            return self.get_response(request)

        toolbar = DebugToolbar(request, self.get_response)

        # Activate instrumentation ie. monkey-patch.
        for panel in toolbar.enabled_panels:
            panel.enable_instrumentation()
        try:
            # Run panels like Django middleware.
            response = toolbar.process_request(request)
        finally:
            # Deactivate instrumentation ie. monkey-unpatch. This must run
            # regardless of the response. Keep 'return' clauses below.
            for panel in reversed(toolbar.enabled_panels):
                panel.disable_instrumentation()

        # Check for responses where the toolbar can't be inserted.
        content_encoding = response.get("Content-Encoding", "")
        content_type = response.get("Content-Type", "").split(";")[0]
        if any(
            (
                getattr(response, "streaming", False),
                "gzip" in content_encoding,
                content_type not in _HTML_TYPES,
            )
        ):
            return response

        # Collapse the toolbar by default if SHOW_COLLAPSED is set.
        if toolbar.config["SHOW_COLLAPSED"] and "djdt" not in request.COOKIES:
            response.set_cookie("djdt", "hide", 864000)


        if toolbar:
            # for django-debug-toolbar >= 1.4
            for panel in reversed(toolbar.enabled_panels):
                if hasattr(panel, 'generate_stats'):
                    panel.generate_stats(request, response)

            cache_key = "%f" % time.time()
            cache.set(cache_key, toolbar.render_toolbar())

            response['X-debug-data-url'] = request.build_absolute_uri(
                reverse('debug_data', urlconf=debug_toolbar.urls, kwargs={'cache_key': cache_key}))

        return response

    @staticmethod
    def generate_server_timing_header(response, panels):
        data = []

        for panel in panels:
            stats = panel.get_server_timing_stats()
            if not stats:
                continue

            for key, record in stats.items():
                # example: `SQLPanel_sql_time=0; "SQL 0 queries"`
                data.append(
                    '{}_{}={}; "{}"'.format(
                        panel.panel_id, key, record.get("value"), record.get("title")
                    )
                )

        if data:
            response["Server-Timing"] = ", ".join(data)
        return response
