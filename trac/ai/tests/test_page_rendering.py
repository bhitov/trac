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
        """Test that the AI page renders on the live server."""
        # Skip if server isn't running
        try:
            response = requests.get('http://localhost:9876/myproject/ai', timeout=1)
        except requests.exceptions.ConnectionError:
            self.skipTest("Server not running")
        
        # Check response
        self.assertEqual(response.status_code, 200, 
                        f"Expected 200, got {response.status_code}")
        
        # Check that key elements are present
        self.assertIn('AI Ticket Assistant', response.text)
        self.assertIn('chat-messages', response.text)
        self.assertIn('chat-input', response.text)
        self.assertIn('send-button', response.text)
        
        # Check that JavaScript is included
        self.assertIn('jQuery(function($)', response.text)
        self.assertIn('sendMessage', response.text)
        
        # Check model is displayed
        self.assertIn('gpt-3.5-turbo', response.text)
    
    def test_page_structure(self):
        """Test that the rendered page has the correct structure."""
        try:
            response = requests.get('http://localhost:9876/myproject/ai', timeout=1)
        except requests.exceptions.ConnectionError:
            self.skipTest("Server not running")
        
        # Use BeautifulSoup to parse if available
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check main structure
            self.assertIsNotNone(soup.find('div', id='chat-messages'))
            self.assertIsNotNone(soup.find('input', id='chat-input'))
            self.assertIsNotNone(soup.find('button', id='send-button'))
            
            # Check title
            title = soup.find('title')
            self.assertIsNotNone(title)
            self.assertIn('AI Assistant', title.text)
            
        except ImportError:
            # Basic checks without BeautifulSoup
            self.assertIn('<div id="chat-messages"', response.text)
            self.assertIn('<input type="text" id="chat-input"', response.text)
            self.assertIn('<button id="send-button"', response.text)


def test_suite():
    return makeSuite(PageRenderingTestCase)


if __name__ == '__main__':
    unittest.main()