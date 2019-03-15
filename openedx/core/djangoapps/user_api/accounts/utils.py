# -*- coding: utf-8 -*-
"""
Utility methods for the account settings.
"""
import random
import re
import string
from urlparse import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _
from six import text_type

from completion import waffle as completion_waffle
from completion.models import BlockCompletion
from openedx.core.djangoapps.site_configuration.models import SiteConfiguration
from openedx.core.djangoapps.theming.helpers import get_config_value_from_site_or_settings, get_current_site
from util.password_policy_validators import password_complexity
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import ItemNotFoundError


def validate_social_link(platform_name, new_social_link):
    """
    Given a new social link for a user, ensure that the link takes one of the
    following forms:

    1) A valid url that comes from the correct social site.
    2) A valid username.
    3) A blank value.
    """
    formatted_social_link = format_social_link(platform_name, new_social_link)

    # Ensure that the new link is valid.
    if formatted_social_link is None:
        required_url_stub = settings.SOCIAL_PLATFORMS[platform_name]['url_stub']
        raise ValueError(_(
            ' Make sure that you are providing a valid username or a URL that contains "' +
            required_url_stub + '". To remove the link from your edX profile, leave this field blank.'
        ))


def format_social_link(platform_name, new_social_link):
    """
    Given a user's social link, returns a safe absolute url for the social link.

    Returns the following based on the provided new_social_link:
    1) Given an empty string, returns ''
    1) Given a valid username, return 'https://www.[platform_name_base][username]'
    2) Given a valid URL, return 'https://www.[platform_name_base][username]'
    3) Given anything unparseable, returns None
    """
    # Blank social links should return '' or None as was passed in.
    if not new_social_link:
        return new_social_link

    url_stub = settings.SOCIAL_PLATFORMS[platform_name]['url_stub']
    username = _get_username_from_social_link(platform_name, new_social_link)
    if not username:
        return None

    # For security purposes, always build up the url rather than using input from user.
    return 'https://www.{}{}'.format(url_stub, username)


def _get_username_from_social_link(platform_name, new_social_link):
    """
    Returns the username given a social link.

    Uses the following logic to parse new_social_link into a username:
    1) If an empty string, returns it as the username.
    2) Given a URL, attempts to parse the username from the url and return it.
    3) Given a non-URL, returns the entire string as username if valid.
    4) If no valid username is found, returns None.
    """
    # Blank social links should return '' or None as was passed in.
    if not new_social_link:
        return new_social_link

    # Parse the social link as if it were a URL.
    parse_result = urlparse(new_social_link)
    url_domain_and_path = parse_result[1] + parse_result[2]
    url_stub = re.escape(settings.SOCIAL_PLATFORMS[platform_name]['url_stub'])
    username_match = re.search('(www\.)?' + url_stub + '(?P<username>.*?)[/]?$', url_domain_and_path, re.IGNORECASE)
    if username_match:
        username = username_match.group('username')
    else:
        username = new_social_link

    # Ensure the username is a valid username.
    if not _is_valid_social_username(username):
        return None

    return username


def _is_valid_social_username(value):
    """
    Given a particular string, returns whether the string can be considered a safe username.
    This is a very liberal validation step, simply assuring forward slashes do not exist
    in the username.
    """
    return '/' not in value


def retrieve_last_sitewide_block_completed(username):
    """
    Completion utility
    From a string 'username' or object User retrieve
    the last course block marked as 'completed' and construct a URL

    :param username: str(username) or obj(User)
    :return: block_lms_url

    """
    if not completion_waffle.waffle().is_enabled(completion_waffle.ENABLE_COMPLETION_TRACKING):
        return

    if not isinstance(username, User):
        userobj = User.objects.get(username=username)
    else:
        userobj = username
    latest_completions_by_course = BlockCompletion.latest_blocks_completed_all_courses(userobj)

    known_site_configs = [
        other_site_config.get_value('course_org_filter') for other_site_config in SiteConfiguration.objects.all()
        if other_site_config.get_value('course_org_filter')
    ]

    current_site_configuration = get_config_value_from_site_or_settings(
        name='course_org_filter',
        site=get_current_site()
    )

    # courses.edx.org has no 'course_org_filter'
    # however the courses within DO, but those entries are not found in
    # known_site_configs, which are White Label sites
    # This is necessary because the WL sites and courses.edx.org
    # have the same AWS RDS mySQL instance
    candidate_course = None
    candidate_block_key = None
    latest_date = None
    # Go through dict, find latest
    for course, [modified_date, block_key] in latest_completions_by_course.items():
        if not current_site_configuration:
            # This is a edx.org
            if course.org in known_site_configs:
                continue
            if not latest_date or modified_date > latest_date:
                candidate_course = course
                candidate_block_key = block_key
                latest_date = modified_date

        else:
            # This is a White Label site, and we should find candidates from the same site
            if course.org not in current_site_configuration:
                # Not the same White Label, or a edx.org course
                continue
            if not latest_date or modified_date > latest_date:
                candidate_course = course
                candidate_block_key = block_key
                latest_date = modified_date

    if not candidate_course:
        return

    lms_root = SiteConfiguration.get_value_for_org(candidate_course.org, "LMS_ROOT_URL", settings.LMS_ROOT_URL)

    try:
        item = modulestore().get_item(candidate_block_key, depth=1)
    except ItemNotFoundError:
        item = None

    if not (lms_root and item):
        return

    return u"{lms_root}/courses/{course_key}/jump_to/{location}".format(
        lms_root=lms_root,
        course_key=text_type(item.location.course_key),
        location=text_type(item.location),
    )


def generate_password(length=12, chars=string.letters + string.digits):  # pylint: disable=too-many-locals
    """Generate a valid random password"""
    if length < 8:
        raise ValueError("password must be at least 8 characters")

    password = ''
    choice = random.SystemRandom().choice
    min_uppercase, min_lowercase, min_digits, min_words = 1, 1, 1, 1
    min_punctuation = 0
    password_length = max(length, settings.PASSWORD_MIN_LENGTH)
    non_ascii_characters = [u'£', u'¥', u'€', u'©', u'®', u'™', u'†', u'§', u'¶', u'π', u'μ', u'±']

    if settings.FEATURES.get('ENFORCE_PASSWORD_POLICY'):
        complexity = password_complexity()
        min_uppercase = complexity.get('UPPER', 0)
        min_lowercase = complexity.get('LOWER', 0)
        min_punctuation = complexity.get('PUNCTUATION', 0)
        min_words = complexity.get('WORDS', min_words)
        min_non_ascii = complexity.get('NON ASCII', 0)

        # Merge DIGITS and NUMERIC policy
        min_numeric = complexity.get('NUMERIC', 0)
        min_digits = complexity.get('DIGITS', 0)
        min_digits = max(min_digits, min_numeric)

        # Lowercase and uppercase are alphabetic
        min_alphabetic = complexity.get('ALPHABETIC', 0)
        if min_alphabetic > min_uppercase + min_lowercase:
            min_lowercase = min_alphabetic - min_uppercase

    # We need to be able to delete values of the choice source sequence,
    # because, _validate_password_complexity function, groups the validations policy inside
    # of a set() iterable, which is a collection of unique elements,
    # and repeated characters are no allowed.
    digits = string.digits
    list_digits = list(digits)
    for _ in xrange(min_digits):
        digit = choice(list_digits)
        password += digit
        del list_digits[list_digits.index(digit)]

    lowercase = string.lowercase
    list_lowercase = list(lowercase)
    for _ in xrange(min_lowercase):
        lower = choice(list_lowercase)
        password += lower
        del list_lowercase[list_lowercase.index(lower)]

    uppercase = string.uppercase
    list_uppercase = list(uppercase)
    for _ in xrange(min_uppercase):
        upper = choice(list_uppercase)
        password += upper
        del list_uppercase[list_uppercase.index(upper)]

    punctuation = string.punctuation
    list_punctuation = list(punctuation)
    for _ in xrange(min_punctuation):
        punct = choice(list_punctuation)
        password += punct
        del list_punctuation[list_punctuation.index(punct)]

    non_ascii = non_ascii_characters
    list_non_ascii = list(non_ascii)
    for _ in xrange(min_non_ascii):
        non = choice(list_non_ascii)
        password += non
        del list_non_ascii[list_non_ascii.index(non)]

    policies = min_uppercase + min_lowercase + min_digits + min_punctuation
    password += ''.join([choice(chars) for _i in xrange(password_length - policies)])

    password_list = list(password)
    random.shuffle(password_list)

    password = ''.join(password_list)

    if min_words > 1:
        # Add the number of spaces to have the number of words required
        word_size = password_length / min_words
        password = ''.join(l + ' ' * (n % word_size == word_size - 1 and n < length - 1) for n, l in enumerate(password))

    return password
