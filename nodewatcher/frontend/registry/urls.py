from django.conf.urls.defaults import *

urlpatterns = patterns('frontend.registry.views',
  url(r'evaluate_forms/(?P<regpoint_id>.*)/(?P<root_id>.*)$', 'evaluate_forms', name = 'evaluate_forms'),
)
