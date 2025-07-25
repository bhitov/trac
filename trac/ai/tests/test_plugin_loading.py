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

"""Tests for AI plugin loading and registration."""

import unittest
from pkg_resources import parse_version

from trac.core import ComponentManager
from trac.test import EnvironmentStub, makeSuite
from trac.web.main import RequestDispatcher


class PluginLoadingTestCase(unittest.TestCase):
    """Test that the AI plugin loads correctly."""
    
    def setUp(self):
        # Create environment with AI plugin explicitly enabled
        self.env = EnvironmentStub(enable=['trac.ai.*'])
        self.env.config.set('ai', 'openai_api_key', 'test-key')
    
    def test_ai_components_loaded(self):
        """Test that AI components are properly loaded."""
        from trac.ai.context_service import ContextService
        from trac.ai.search_service import FuzzySearchService
        from trac.ai.chat_handler import ChatHandler
        
        # Check that components are enabled
        self.assertTrue(self.env.is_component_enabled(ContextService))
        self.assertTrue(self.env.is_component_enabled(FuzzySearchService))
        self.assertTrue(self.env.is_component_enabled(ChatHandler))
        
        # Check that we can instantiate them
        context = ContextService(self.env)
        search = FuzzySearchService(self.env)
        handler = ChatHandler(self.env)
        
        self.assertIsNotNone(context)
        self.assertIsNotNone(search)
        self.assertIsNotNone(handler)
    
    def test_request_handler_registration(self):
        """Test that ChatHandler is registered as a request handler."""
        from trac.ai.chat_handler import ChatHandler
        from trac.web.api import IRequestHandler
        
        # Create handler instance
        handler = ChatHandler(self.env)
        
        # Check that ChatHandler can match AI requests
        class MockRequest:
            def __init__(self, path):
                self.path_info = path
        
        req = MockRequest('/ai')
        self.assertTrue(handler.match_request(req), 
                       "ChatHandler should match /ai requests")
    
    def test_template_provider_registration(self):
        """Test that ChatHandler provides templates."""
        from trac.ai.chat_handler import ChatHandler
        from trac.web.chrome import ITemplateProvider
        
        handler = ChatHandler(self.env)
        
        # Check template directories
        template_dirs = handler.get_templates_dirs()
        self.assertTrue(len(template_dirs) > 0, 
                       "Handler should provide template directories")
        self.assertTrue(any('ai' in str(d) for d in template_dirs),
                       "Template directories should contain 'ai'")
    
    def test_request_dispatcher_knows_ai_handler(self):
        """Test that RequestDispatcher can route to AI handler."""
        dispatcher = RequestDispatcher(self.env)
        
        # Create a mock request for /ai
        class MockRequest:
            def __init__(self, path):
                self.path_info = path
                self.method = 'GET'
                self.args = {}
        
        # Test various AI paths
        test_paths = ['/ai', '/ai/', '/ai/chat']
        
        for path in test_paths:
            req = MockRequest(path)
            
            # Get handler for this request
            chosen_handler = None
            for handler in dispatcher.handlers:
                if handler.match_request(req):
                    chosen_handler = handler
                    break
            
            self.assertIsNotNone(chosen_handler, f"No handler found for {path}")
            
            # Verify it's our ChatHandler
            from trac.ai.chat_handler import ChatHandler
            self.assertIsInstance(chosen_handler, ChatHandler)
    
    def test_configuration_options(self):
        """Test that configuration options are properly defined."""
        from trac.ai.chat_handler import ChatHandler
        
        handler = ChatHandler(self.env)
        
        # Check that options are accessible
        self.assertEqual(handler.openai_api_key, 'test-key')
        self.assertEqual(handler.openai_model, 'gpt-3.5-turbo')
        self.assertEqual(handler.max_context_tickets, '20')
        self.assertEqual(handler.search_threshold, '20')
    
    def test_plugin_version_info(self):
        """Test that the plugin provides version information."""
        # This would typically be in setup.py, but we can check the module
        import trac.ai
        self.assertTrue(hasattr(trac.ai, '__all__'))
        self.assertIn('ContextService', trac.ai.__all__)
        self.assertIn('FuzzySearchService', trac.ai.__all__)
        self.assertIn('ChatHandler', trac.ai.__all__)


def test_suite():
    return makeSuite(PluginLoadingTestCase)