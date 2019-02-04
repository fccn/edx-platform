""" Overrides for Docker-based devstack. """

from .devstack import *  # pylint: disable=wildcard-import, unused-wildcard-import

FEATURES.update({
    'ENABLE_COURSEWARE_SEARCH': True,
    'ENABLE_COURSE_DISCOVERY': True,
    'ENABLE_DASHBOARD_SEARCH': True,
})
