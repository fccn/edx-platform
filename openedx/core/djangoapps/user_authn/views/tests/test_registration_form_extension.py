"""
Tests for the extended profile helpers in registration_form.

These deliberately do not mock get_registration_extension_form or
get_extended_profile_model. The existing suites patch both, which is why the
deprecated-setting path was never exercised and two crashes reached a live
environment: a NameError from an undefined logger, and a model write on sites
that never opted in to model backed storage.
"""

from django import forms
from django.test import TestCase
from django.test.utils import override_settings

from common.djangoapps.student.models import UserProfile
from openedx.core.djangoapps.user_authn.views.registration_form import (
    get_extended_profile_model,
    get_registration_extension_form,
)

DEPRECATED_FORM = "openedx.core.djangoapps.user_authn.views.tests.test_registration_form_extension.PlainForm"
MODEL_FORM = "openedx.core.djangoapps.user_authn.views.tests.test_registration_form_extension.ProfileModelForm"


class PlainForm(forms.Form):
    """A form with no Meta.model, the historical shape for this extension point."""

    favourite_colour = forms.CharField(required=False)


class ProfileModelForm(forms.ModelForm):
    """A model backed form, the shape PROFILE_EXTENSION_FORM expects."""

    class Meta:
        model = UserProfile
        fields = ["bio"]


class DeprecatedSettingTest(TestCase):
    """REGISTRATION_EXTENSION_FORM must keep working and must stay meta only."""

    @override_settings(REGISTRATION_EXTENSION_FORM=DEPRECATED_FORM, PROFILE_EXTENSION_FORM=None)
    def test_deprecated_setting_still_builds_a_form(self):
        # This is the call that returned a 500 in a live environment, because the
        # deprecation warning it logs referenced a logger the module never defined.
        form = get_registration_extension_form()

        assert isinstance(form, PlainForm)

    @override_settings(REGISTRATION_EXTENSION_FORM=DEPRECATED_FORM, PROFILE_EXTENSION_FORM=None)
    def test_deprecated_setting_exposes_no_model(self):
        # Returning a model here is what made account settings write rows on sites
        # that only ever configured the old setting.
        assert get_extended_profile_model() is None


class ProfileExtensionFormTest(TestCase):
    """PROFILE_EXTENSION_FORM is the one that opts a site in to model storage."""

    @override_settings(REGISTRATION_EXTENSION_FORM=None, PROFILE_EXTENSION_FORM=MODEL_FORM)
    def test_model_backed_form_exposes_its_model(self):
        assert get_extended_profile_model() is UserProfile

    @override_settings(REGISTRATION_EXTENSION_FORM=None, PROFILE_EXTENSION_FORM=DEPRECATED_FORM)
    def test_form_without_a_model_degrades_instead_of_raising(self):
        # A plain Form has no Meta.model. The handler for that case logs, so it
        # raised a NameError of its own and masked the error it was handling.
        assert get_extended_profile_model() is None

    @override_settings(REGISTRATION_EXTENSION_FORM=None, PROFILE_EXTENSION_FORM="does.not.exist.Form")
    def test_unimportable_form_degrades_instead_of_raising(self):
        assert get_extended_profile_model() is None
        assert get_registration_extension_form() is None

    @override_settings(REGISTRATION_EXTENSION_FORM=None, PROFILE_EXTENSION_FORM=None)
    def test_no_setting_means_no_form_and_no_model(self):
        assert get_registration_extension_form() is None
        assert get_extended_profile_model() is None
