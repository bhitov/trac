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

"""Live server tests for AI plugin to diagnose loading issues."""

import unittest
import requests
import subprocess
import time
import os
from unittest.mock import patch

from trac.test import EnvironmentStub, makeSuite
from trac.core import ComponentManager
from trac.web.main import RequestDispatcher
from trac.config import Configuration


# Change this to your actual project path if different
PROJECT_PATH = '/Users/bhitov/code/g2p6/amp-trac/myproject'


class LiveServerDiagnosticsTestCase(unittest.TestCase):
    """Diagnostic tests to understand why AI plugin isn't loading."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.server_url = "http://localhost:9876/myproject"
        cls.project_path = os.path.abspath(PROJECT_PATH)
        cls.trac_ini_path = os.path.join(cls.project_path, 'conf', 'trac.ini')
    
    def test_server_is_running(self):
        """Test that the server is actually running."""
        try:
            response = requests.get(f"{self.server_url}/wiki", timeout=5)
            self.assertEqual(response.status_code, 200, 
                           "Server should be running at http://localhost:9876")
        except requests.exceptions.ConnectionError:
            self.fail("Server is not running. Please start it with ./start_server.sh")
    
    def test_config_file_exists(self):
        """Test that config file exists and is readable."""
        self.assertTrue(os.path.exists(self.trac_ini_path), 
                       f"Config file should exist at {self.trac_ini_path}")
        
        # Read config
        config = Configuration(self.trac_ini_path)
        sections = list(config.sections())
        self.assertIn('components', sections, "Config should have [components] section")
        self.assertIn('ai', sections, "Config should have [ai] section")
    
    def test_ai_plugin_enabled_in_config(self):
        """Test that AI plugin is enabled in configuration."""
        config = Configuration(self.trac_ini_path)
        
        # Check components section
        ai_enabled = config.get('components', 'trac.ai.*')
        self.assertEqual(ai_enabled, 'enabled', 
                        "trac.ai.* should be 'enabled' in [components] section")
        
        # Check AI configuration
        api_key = config.get('ai', 'openai_api_key')
        self.assertTrue(api_key and api_key.startswith('sk-'), 
                       "OpenAI API key should be configured")
    
    def test_plugin_modules_exist(self):
        """Test that plugin modules are importable."""
        modules = [
            'trac.ai',
            'trac.ai.chat_handler',
            'trac.ai.context_service',
            'trac.ai.search_service'
        ]
        
        for module in modules:
            try:
                __import__(module)
                self.assertTrue(True, f"{module} imported successfully")
            except ImportError as e:
                self.fail(f"Failed to import {module}: {e}")
    
    def test_ai_endpoints_response(self):
        """Test various AI endpoints and their responses."""
        endpoints = [
            ('/ai', 'GET'),
            ('/ai/', 'GET'),
            ('/ai/chat', 'POST'),
        ]
        
        for endpoint, method in endpoints:
            url = f"{self.server_url}{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, timeout=5)
            else:
                response = requests.post(url, 
                                       json={'message': 'test'},
                                       headers={'Content-Type': 'application/json'},
                                       timeout=5)
            
            print(f"\n{method} {endpoint}:")
            print(f"  Status: {response.status_code}")
            print(f"  Headers: {dict(response.headers)}")
            
            if response.status_code == 404:
                # Check if it's a Trac 404 or server 404
                if 'trac' in response.text.lower():
                    print("  Type: Trac 404 (handler not found)")
                else:
                    print("  Type: Server 404")
            elif response.status_code == 500:
                # Try to extract error message
                if 'traceback' in response.text.lower():
                    print("  Error: Python exception occurred")
                    # Extract error message if possible
                    import re
                    error_match = re.search(r'<pre[^>]*>(.*?)</pre>', response.text, re.DOTALL)
                    if error_match:
                        print(f"  Details: {error_match.group(1)[:200]}...")
            
            # For non-200 responses, show part of the body
            if response.status_code != 200:
                print(f"  Body preview: {response.text[:300]}...")
    
    def test_environment_components(self):
        """Test component loading in a test environment."""
        # Create test environment with AI enabled
        env = EnvironmentStub(enable=['trac.ai.*'])
        env.config.set('ai', 'openai_api_key', 'test-key')
        
        # Check if components are loaded
        from trac.ai.chat_handler import ChatHandler
        from trac.web.api import IRequestHandler
        
        # Check that ChatHandler is enabled
        self.assertTrue(env.is_component_enabled(ChatHandler),
                       "ChatHandler should be enabled")
        
        # Create handler and test it
        handler = ChatHandler(env)
        self.assertIsNotNone(handler, "ChatHandler should be instantiable")
        
        # Test that it can match requests
        class MockRequest:
            def __init__(self, path):
                self.path_info = path
        
        req = MockRequest('/ai')
        self.assertTrue(handler.match_request(req), 
                       "ChatHandler should match /ai requests")
    
    def test_request_matching(self):
        """Test if ChatHandler can match AI requests."""
        env = EnvironmentStub(enable=['trac.ai.*'])
        env.config.set('ai', 'openai_api_key', 'test-key')
        
        from trac.ai.chat_handler import ChatHandler
        handler = ChatHandler(env)
        
        # Test request matching
        class MockRequest:
            def __init__(self, path):
                self.path_info = path
        
        test_paths = ['/ai', '/ai/', '/ai/chat', '/notai']
        
        print("\nRequest matching tests:")
        for path in test_paths:
            req = MockRequest(path)
            matches = handler.match_request(req)
            print(f"  {path}: {'MATCH' if matches else 'NO MATCH'}")
            
            if path.startswith('/ai'):
                self.assertTrue(matches, f"ChatHandler should match {path}")
            else:
                self.assertFalse(matches, f"ChatHandler should not match {path}")
    
    def test_trac_admin_component_list(self):
        """Use trac-admin to list components."""
        cmd = ['trac-admin', self.project_path, 'config', 'get', 'components']
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            print("\nComponents listed by trac-admin:")
            
            # Parse output
            for line in result.stdout.split('\n'):
                if 'ai' in line.lower():
                    print(f"  AI-related: {line}")
            
            if result.stderr:
                print(f"Errors: {result.stderr}")
        except Exception as e:
            print(f"Failed to run trac-admin: {e}")
    
    def test_plugin_egg_info(self):
        """Check if plugin is properly installed as egg-info."""
        import site
        
        print("\nChecking for AI plugin installation:")
        
        # Check site-packages
        for site_dir in site.getsitepackages():
            ai_path = os.path.join(site_dir, 'trac', 'ai')
            if os.path.exists(ai_path):
                print(f"  Found at: {ai_path}")
        
        # Check if it's in development mode
        import trac.ai
        print(f"  trac.ai location: {trac.ai.__file__}")
        
        # Check if ChatHandler is discoverable
        try:
            from pkg_resources import iter_entry_points
            
            print("\nEntry points for trac.plugins:")
            for entry_point in iter_entry_points('trac.plugins'):
                if 'ai' in str(entry_point).lower():
                    print(f"  {entry_point}")
        except ImportError:
            print("  pkg_resources not available")
    
    def test_navigation_items(self):
        """Test if AI appears in navigation."""
        response = requests.get(f"{self.server_url}/wiki")
        
        print("\nChecking navigation items:")
        
        # Look for main navigation
        import re
        nav_match = re.search(r'<div id="mainnav"[^>]*>(.*?)</div>', 
                             response.text, re.DOTALL)
        
        if nav_match:
            nav_html = nav_match.group(1)
            links = re.findall(r'href="([^"]+)"[^>]*>([^<]+)</a>', nav_html)
            
            print("  Main navigation items:")
            for href, text in links:
                print(f"    - {text}: {href}")
                if 'ai' in text.lower():
                    print("      ^ AI FOUND IN NAV!")
        else:
            print("  Could not find navigation HTML")
    
    def test_error_details(self):
        """Try to get detailed error information."""
        # Test with debug mode
        response = requests.get(f"{self.server_url}/ai")
        
        if response.status_code == 404:
            print("\nDetailed 404 analysis:")
            
            # Check if it mentions no handler
            if 'No handler matched request to' in response.text:
                print("  Trac says: No handler matched request")
                print("  This means ChatHandler.match_request() returned False")
                print("  OR ChatHandler is not registered as IRequestHandler")
            
            # Extract the list of tried handlers if available
            tried_match = re.search(r'tried handlers: (.*?)<', response.text)
            if tried_match:
                print(f"  Handlers tried: {tried_match.group(1)}")


def test_suite():
    return makeSuite(LiveServerDiagnosticsTestCase)


if __name__ == '__main__':
    unittest.main()