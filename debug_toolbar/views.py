from django.http import HttpResponse
from django.utils.html import escape
from django.utils.translation import gettext as _

from debug_toolbar.cache import cache
from django.shortcuts import render_to_response
from django.views.decorators.clickjacking import xframe_options_exempt

from debug_toolbar.decorators import require_show_toolbar
from debug_toolbar.toolbar import DebugToolbar


@require_show_toolbar
def render_panel(request):
    """Render the contents of a panel"""
    toolbar = DebugToolbar.fetch(request.GET["store_id"])
    if toolbar is None:
        content = _(
            "Data for this panel isn't available anymore. "
            "Please reload the page and retry."
        )
        content = "<p>%s</p>" % escape(content)
    else:
        panel = toolbar.get_panel_by_id(request.GET["panel_id"])
        content = panel.content
    return HttpResponse(content)



@xframe_options_exempt
def debug_data(request, cache_key):
    html = cache.get(cache_key)

    if html is None:
        return render_to_response('debug-data-unavailable.html')

    return HttpResponse(html, content_type="text/html; charset=utf-8")
