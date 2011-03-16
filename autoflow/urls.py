from django.conf.urls.defaults import *

urlpatterns = patterns('',
	(r'^create_process/(?P<flowID>\d+)/(?P<formID>\d+)/$','workflow.views.create_process'),
	(r'^process/(?P<id>\d+)/$','workflow.views.view_process'),
)
