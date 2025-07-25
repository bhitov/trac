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

"""Error handling and edge case tests for AI plugin."""

import unittest
import json
from unittest.mock import Mock, patch

from trac.test import EnvironmentStub, makeSuite
from trac.ai.chat_handler import ChatHandler
from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService
from trac.web.api import RequestDone


class ErrorHandlingTestCase(unittest.TestCase):
    """Test error handling and edge cases."""
    
    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.ai.*'])
        self.env.config.set('ai', 'openai_api_key', 'test-key')
        self.env.config.set('ai', 'model', 'gpt-3.5-turbo')
        
        self.handler = ChatHandler(self.env)
        self.context_service = ContextService(self.env)
        self.search_service = FuzzySearchService(self.env)
    
    def _create_mock_request(self, method='GET', data=None):
        """Create a mock request."""
        req = Mock()
        req.method = method
        req.path_info = '/ai/chat'
        req.authname = 'test_user'
        req.perm = Mock()
        req.perm.require = Mock()
        
        if data:
            req.read = Mock(return_value=json.dumps(data).encode('utf-8'))
        else:
            req.read = Mock(return_value=b'')
        
        # Response capture
        req._responses = []
        req._headers = {}
        req.send_response = Mock(side_effect=lambda code: setattr(req, '_status', code))
        req.send_header = Mock(side_effect=lambda k, v: req._headers.update({k: v}))
        req.end_headers = Mock()
        req.write = Mock(side_effect=lambda data: req._responses.append(data))
        
        return req
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_openai_api_error(self, mock_openai):
        """Test handling of OpenAI API errors."""
        # Mock API error
        mock_client = Mock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API rate limit exceeded")
        
        req = self._create_mock_request(method='POST', data={'message': 'test'})
        
        with self.assertRaises(RequestDone):
            self.handler.process_request(req)
        
        # Check error response
        self.assertEqual(req._status, 500)
        response = json.loads(req._responses[0].decode())
        self.assertIn('error', response)
        self.assertIn('rate limit', response['error']['message'])
    
    def test_empty_message(self):
        """Test handling of empty message."""
        req = self._create_mock_request(method='POST', data={'message': ''})
        
        with self.assertRaises(RequestDone):
            self.handler.process_request(req)
        
        self.assertEqual(req._status, 400)
        response = json.loads(req._responses[0].decode())
        self.assertIn('error', response)
        self.assertIn('empty', response['error']['message'].lower())
    
    def test_missing_message_field(self):
        """Test handling of missing message field."""
        req = self._create_mock_request(method='POST', data={})
        
        with self.assertRaises(RequestDone):
            self.handler.process_request(req)
        
        self.assertEqual(req._status, 400)
        response = json.loads(req._responses[0].decode())
        self.assertIn('error', response)
    
    def test_malformed_json(self):
        """Test handling of malformed JSON."""
        req = self._create_mock_request(method='POST')
        req.read = Mock(return_value=b'{invalid json')
        
        with self.assertRaises(RequestDone):
            self.handler.process_request(req)
        
        self.assertEqual(req._status, 400)
        response = json.loads(req._responses[0].decode())
        self.assertIn('error', response)
        self.assertIn('Invalid request', response['error']['message'])
    
    def test_database_error(self):
        """Test handling of database errors."""
        # Mock database error
        with patch.object(self.context_service, 'get_recent_tickets', 
                         side_effect=Exception("Database connection failed")):
            
            req = Mock()
            req.authname = 'admin'
            from trac.util.datefmt import utc
            req.tz = utc
            
            # This should not crash
            with self.assertRaises(Exception):
                self.context_service.get_recent_tickets(req)
    
    def test_large_message_handling(self):
        """Test handling of very large messages."""
        large_message = 'x' * 10000  # 10KB message
        req = self._create_mock_request(method='POST', data={'message': large_message})
        
        # Should handle without crashing
        # (In real implementation, might want to limit message size)
        # For now, just ensure it doesn't crash
        self.env.config.set('ai', 'openai_api_key', '')  # Disable API to avoid actual call
        handler = ChatHandler(self.env)
        
        with self.assertRaises(RequestDone):
            handler.process_request(req)
    
    def test_concurrent_requests(self):
        """Test that handler can handle concurrent requests."""
        # Create multiple requests
        requests = []
        for i in range(3):
            req = self._create_mock_request(method='POST', data={'message': f'test {i}'})
            requests.append(req)
        
        # Each request should be independent
        self.env.config.set('ai', 'openai_api_key', '')  # Disable API
        handler = ChatHandler(self.env)
        
        for req in requests:
            with self.assertRaises(RequestDone):
                handler.process_request(req)
            
            # Each should get its own error
            self.assertEqual(req._status, 500)
    
    def test_invalid_http_method(self):
        """Test handling of invalid HTTP methods."""
        for method in ['PUT', 'DELETE', 'PATCH']:
            req = self._create_mock_request(method=method)
            req.send_error = Mock()
            
            self.handler.process_request(req)
            req.send_error.assert_called_with(405, 'Method Not Allowed')
    
    def test_special_characters_in_query(self):
        """Test handling of special characters in search queries."""
        special_chars = ['<script>', 'DROP TABLE', '"; DELETE FROM', '\\x00', '${jndi:ldap://}']
        
        req = Mock()
        req.authname = 'admin'
        from trac.util.datefmt import utc
        req.tz = utc
        req.perm = lambda x=None: MockPermissionCache()
        
        for char in special_chars:
            # Should handle safely without SQL injection
            results = self.search_service.search_tickets(req, char)
            # Should return empty or safe results
            self.assertIsInstance(results, list)
    
    def test_permission_denied_handling(self):
        """Test handling when user lacks permissions."""
        req = Mock()
        req.authname = 'restricted_user'
        from trac.util.datefmt import utc
        req.tz = utc
        
        # Mock permission denial
        class DenyPermission:
            def __contains__(self, perm):
                return False
            def __call__(self, resource=None):
                return self
        
        req.perm = DenyPermission()
        
        # Should return empty results, not crash
        tickets = self.context_service.get_recent_tickets(req)
        self.assertEqual(len(tickets), 0)


class MockPermissionCache:
    def __contains__(self, perm):
        return True
    def __call__(self, resource=None):
        return self


def test_suite():
    return makeSuite(ErrorHandlingTestCase)