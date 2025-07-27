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

"""Unit tests for the Wiki REST API."""

import json
import unittest
from datetime import datetime

from trac.core import TracError
from trac.perm import PermissionCache, PermissionSystem
from trac.test import EnvironmentStub, MockPerm, MockRequest
from trac.util.datefmt import to_utimestamp, utc
from trac.web.api import RequestDone
from trac.wiki.model import WikiPage

from trac.rest_api.handlers import RestApiHandler
from trac.rest_api.wiki import WikiAPI


class WikiAPITestCase(unittest.TestCase):
    """Test cases for the Wiki REST API."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.api = WikiAPI(self.env)
        self.handler = RestApiHandler(self.env)
        
        # Create some test wiki pages
        self._create_test_pages()
        
    def tearDown(self):
        self.env.reset_db()
        
    def _create_test_pages(self):
        """Create test wiki pages in the database."""
        pages_data = [
            {'name': 'TestPage1', 'text': 'This is test page 1'},
            {'name': 'TestPage2', 'text': 'This is test page 2'},
            {'name': 'TestPage3', 'text': 'This is test page 3'},
        ]
        
        for data in pages_data:
            page = WikiPage(self.env, data['name'])
            page.text = data['text']
            page.save('testuser', 'Initial version')
    
    def _make_request(self, method='GET', path='', data=None, authname='admin'):
        """Create a mock request for testing."""
        # Create request with None authname to get MockPerm
        req = MockRequest(self.env, method=method, path_info=path,
                          authname=None)
        
        # Override with authname and create a MockPerm that allows everything
        req.authname = authname
        req.perm = MockPerm()
        
        # Add REST API args
        if path.startswith('/api/'):
            parts = path[5:].split('/', 1)
            req.args['api_resource'] = parts[0]
            req.args['api_path'] = parts[1] if len(parts) > 1 else ''
        
        # Add request body data
        if data:
            req.data = json.dumps(data).encode('utf-8')
            
            # Mock read method
            def mock_read():
                return req.data
            req.read = mock_read
        
        return req
    
    def test_list_pages(self):
        """Test GET /api/wiki - List all wiki pages."""
        req = self._make_request('GET', '/api/wiki')
        
        response_data = None
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.write = mock_write
        
        try:
            self.api.handle_request(req, '')
        except RequestDone:
            pass
        
        self.assertIsNotNone(response_data)
        self.assertIn('pages', response_data)
        self.assertEqual(len(response_data['pages']), 3)
        self.assertEqual(response_data['pages'][0]['name'], 'TestPage1')
    
    def test_get_single_page(self):
        """Test GET /api/wiki/TestPage1 - Get specific page."""
        req = self._make_request('GET', '/api/wiki/TestPage1')
        
        response_data = None
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'TestPage1')
        except RequestDone:
            pass
        
        self.assertIsNotNone(response_data)
        self.assertEqual(response_data['name'], 'TestPage1')
        self.assertEqual(response_data['text'], 'This is test page 1')
        self.assertIn('version', response_data)
        self.assertIn('author', response_data)
    
    def test_get_nonexistent_page(self):
        """Test GET /api/wiki/NonExistent - Get nonexistent page."""
        req = self._make_request('GET', '/api/wiki/NonExistent')
        
        response_data = None
        status_code = None
        
        def mock_send_response(code):
            nonlocal status_code
            status_code = code
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.send_response = mock_send_response
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'NonExistent')
        except RequestDone:
            pass
        
        self.assertEqual(status_code, 404)
        self.assertIn('error', response_data)
    
    def test_create_page(self):
        """Test PUT /api/wiki/NewPage - Create new wiki page."""
        new_page_data = {
            'text': '= New Page =\n\nThis is a new wiki page created via API.',
            'comment': 'Created via REST API test'
        }
        
        # For wiki, we use PUT to create a new page
        req = self._make_request('PUT', '/api/wiki/NewPage', data=new_page_data)
        req.args['api_path'] = 'NewPage'
        
        response_data = None
        status_code = None
        
        def mock_send_response(code):
            nonlocal status_code
            status_code = code
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.send_response = mock_send_response
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'NewPage')
        except RequestDone:
            pass
        
        self.assertEqual(status_code, 200)  # PUT returns 200
        self.assertIsNotNone(response_data)
        self.assertEqual(response_data['name'], 'NewPage')
        
        # Verify page was actually created
        page = WikiPage(self.env, 'NewPage')
        self.assertTrue(page.exists)
        self.assertEqual(page.text, new_page_data['text'])
    
    def test_update_page(self):
        """Test PUT /api/wiki/TestPage1 - Update existing page."""
        update_data = {
            'text': 'Updated content for test page 1',
            'comment': 'Updated via REST API'
        }
        
        req = self._make_request('PUT', '/api/wiki/TestPage1', data=update_data)
        
        response_data = None
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'TestPage1')
        except RequestDone:
            pass
        
        self.assertIsNotNone(response_data)
        self.assertEqual(response_data['name'], 'TestPage1')
        
        # Verify page was updated
        page = WikiPage(self.env, 'TestPage1')
        self.assertEqual(page.text, update_data['text'])
    
    def test_delete_page(self):
        """Test DELETE /api/wiki/TestPage3 - Delete wiki page."""
        req = self._make_request('DELETE', '/api/wiki/TestPage3')
        
        response_data = None
        status_code = None
        
        def mock_send_response(code):
            nonlocal status_code
            status_code = code
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.send_response = mock_send_response
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'TestPage3')
        except RequestDone:
            pass
        
        self.assertEqual(status_code, 200)
        self.assertIn('message', response_data)
        
        # Verify page was deleted
        page = WikiPage(self.env, 'TestPage3')
        self.assertFalse(page.exists)
    
    def test_get_page_history(self):
        """Test GET /api/wiki/TestPage1/history - Get page history."""
        # Create multiple versions
        page = WikiPage(self.env, 'TestPage1')
        page.text = 'Version 2 content'
        page.save('testuser', 'Second version')
        page.text = 'Version 3 content'
        page.save('testuser', 'Third version')
        
        req = self._make_request('GET', '/api/wiki/TestPage1/history')
        
        response_data = None
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'TestPage1/history')
        except RequestDone:
            pass
        
        self.assertIsNotNone(response_data)
        self.assertEqual(response_data['page'], 'TestPage1')
        self.assertIn('history', response_data)
        self.assertGreaterEqual(len(response_data['history']), 3)
        
        # Check history is in descending order (newest first)
        self.assertEqual(response_data['history'][0]['version'], 3)
        self.assertEqual(response_data['history'][0]['comment'], 'Third version')
    
    def test_get_specific_version(self):
        """Test GET /api/wiki/TestPage1/versions/1 - Get specific version."""
        # Create multiple versions
        page = WikiPage(self.env, 'TestPage1')
        original_text = page.text
        page.text = 'Version 2 content'
        page.save('testuser', 'Second version')
        
        req = self._make_request('GET', '/api/wiki/TestPage1/versions/1')
        
        response_data = None
        
        def mock_write(data):
            nonlocal response_data
            response_data = json.loads(data.decode('utf-8'))
        
        req.write = mock_write
        
        try:
            self.api.handle_request(req, 'TestPage1/versions/1')
        except RequestDone:
            pass
        
        self.assertIsNotNone(response_data)
        self.assertEqual(response_data['name'], 'TestPage1')
        self.assertEqual(response_data['version'], 1)
        self.assertEqual(response_data['text'], original_text)


def test_suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(WikiAPITestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')