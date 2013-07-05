from django.conf import urls

urlpatterns = urls.patterns('',
    # Registry
    urls.url(r'^registry/', urls.include('nodewatcher.core.registry.urls', namespace='registry')),

    # Accounts
    urls.url(r'account/', urls.include('nodewatcher.extra.account.urls')),
    urls.url(r'^user/(?P<username>[\w.@+-]+)/$', 'nodewatcher.extra.account.views.user', name='user_page'),

    # Frontend
    urls.url(r'^', urls.include('nodewatcher.core.frontend.urls')),
)