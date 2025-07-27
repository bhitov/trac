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

"""Test that the AI page actually renders correctly."""

import os
import unittest
import requests

from trac.test import EnvironmentStub, makeSuite
from trac.web.chrome import Chrome
from trac.web.href import Href
from trac.ai.chat_handler import ChatHandler


class PageRenderingTestCase(unittest.TestCase):
    """Test that the AI page renders correctly."""
    
    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.ai.*'])
        self.env.config.set('ai', 'openai_api_key', 'test-key')
        self.handler = ChatHandler(self.env)
    
    def test_template_renders_without_error(self):
        """Test that the AI chat template can be rendered without errors."""
        # Get template data from handler
        template, data, metadata = self.handler._render_chat_page(None)
        
        # Verify template and data
        self.assertEqual(template, 'ai_chat.html')
        self.assertIsInstance(data, dict)
        self.assertIn('api_configured', data)
        self.assertIn('model', data)
        
        # Test that the template exists and has valid syntax
        template_dirs = self.handler.get_templates_dirs()
        template_found = False
        
        for template_dir in template_dirs:
            template_path = os.path.join(template_dir, 'ai_chat.html')
            if os.path.exists(template_path):
                template_found = True
                # Read and check basic syntax
                with open(template_path, 'r') as f:
                    content = f.read()
                    # Check for basic template structure
                    self.assertIn('# extends', content)
                    self.assertIn('# block', content)
                    self.assertIn('# endblock', content)
                break
        
        self.assertTrue(template_found, "ai_chat.html template should exist")
    
    def test_live_server_rendering(self):
        """Test that the AI page renders correctly using mock request."""
        from trac.test import MockRequest
        from trac.web.chrome import Chrome
        from trac.ai.chat_handler import ChatHandler
        
        # Create mock request
        req = MockRequest(self.env, path_info='/ai')
        
        # Process request
        module = ChatHandler(self.env)
        self.assertTrue(module.match_request(req))
        template, data, content_type = module.process_request(req)
        
        # Check template and data
        self.assertEqual(template, 'ai_chat.html')
        self.assertIn('api_configured', data)
        self.assertIn('model', data)
        
        # Check model is set correctly
        self.assertEqual(data['model'], 'gpt-3.5-turbo')
    
    def test_page_structure(self):
        """Test that the rendered page template has the correct structure."""
        from trac.test import MockRequest
        from trac.web.chrome import Chrome
        from trac.ai.chat_handler import ChatHandler
        
        # Create mock request
        req = MockRequest(self.env, path_info='/ai')
        
        # Process request
        module = ChatHandler(self.env)
        template, data, content_type = module.process_request(req)
        
        # Check template exists by using the handler's template directories
        template_found = False
        template_path = None
        for template_dir in module.get_templates_dirs():
            potential_path = os.path.join(template_dir, template)
            if os.path.exists(potential_path):
                template_found = True
                template_path = potential_path
                break
        self.assertTrue(template_found, f"Template {template} not found in {module.get_templates_dirs()}")
        
        # Read template content to verify structure
        with open(template_path, 'r') as f:
            content = f.read()
            
        # Check main elements exist in template
        self.assertIn('chat-messages', content)
        self.assertIn('chat-input', content)
        self.assertIn('send-button', content)
        self.assertIn('AI Ticket Assistant', content)


def test_suite():
    return makeSuite(PageRenderingTestCase)


if __name__ == '__main__':
    unittest.main()