from django import dispatch
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _

from registration import signals as registration_signals

from . import utils

# Argument is user which has logged in
user_login = dispatch.Signal(providing_args=["request", "user"])

# Arugment is user which has logged out if any
user_logout = dispatch.Signal(providing_args=["request", "user"])


def user_login_message(sender, request, user, **kwargs):
    """
    Gives a success login message to the user.
    """

    messages.success(request, _("You have been successfully logged in."), fail_silently=True)

user_login.connect(user_login_message, dispatch_uid=__name__ + '.user_login_message')


def set_language(sender, request, user, **kwargs):
    """
    Sets Django language preference based on user profile.
    """

    request.session['django_language'] = user.profile.language

user_login.connect(set_language, dispatch_uid=__name__ + '.set_language')


def user_logout_message(sender, request, user, **kwargs):
    """
    Gives a success logout message to the user.
    """

    messages.success(request, _("You have been successfully logged out."), fail_silently=True)

user_logout.connect(user_logout_message, dispatch_uid=__name__ + '.user_logout_message')
