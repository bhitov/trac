# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""Tests for the AI chatbot plugin."""

import unittest

from trac.ai.tests import (
    test_context_service,
    test_search_service,
    test_chat_handler,
    test_integration,
    test_plugin_loading,
    test_scenarios,
    test_requirements_verification,
    test_error_handling,
    test_security
)


def test_suite():
    """Return the complete test suite for AI plugin."""
    suite = unittest.TestSuite()
    
    # Add all test suites
    suite.addTest(test_context_service.test_suite())
    suite.addTest(test_search_service.test_suite())
    suite.addTest(test_chat_handler.test_suite())
    suite.addTest(test_integration.test_suite())
    suite.addTest(test_plugin_loading.test_suite())
    suite.addTest(test_scenarios.test_suite())
    suite.addTest(test_requirements_verification.test_suite())
    suite.addTest(test_error_handling.test_suite())
    suite.addTest(test_security.test_suite())
    
    return suite


# For pytest discovery
__all__ = [
    'test_context_service',
    'test_search_service', 
    'test_chat_handler',
    'test_integration',
    'test_plugin_loading',
    'test_scenarios',
    'test_requirements_verification',
    'test_error_handling',
    'test_security'
]