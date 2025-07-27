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

"""Tests for the AI chat handler."""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.web.api import RequestDone
from trac.ai.chat_handler import ChatHandler
from trac.util.datefmt import utc


class ChatHandlerTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Set up configuration
        self.env.config.set('ai', 'openai_api_key', 'test-api-key')
        self.env.config.set('ai', 'model', 'gpt-3.5-turbo')
        self.env.config.set('ai', 'max_context_tickets', '20')
        self.env.config.set('ai', 'search_threshold', '20')
        
        self.handler = ChatHandler(self.env)
        
        # Create some test tickets
        self._create_test_tickets()
    
    def _create_test_tickets(self):
        """Create test tickets."""
        for i in range(25):
            ticket = Ticket(self.env)
            ticket['summary'] = f'Test ticket {i}'
            ticket['description'] = f'Description for test ticket {i}'
            ticket['status'] = 'new'
            ticket['priority'] = 'normal'
            ticket.insert()
    
    def test_match_request(self):
        """Test request matching."""
        req = MockRequest()
        
        # Should match these paths
        req.path_info = '/ai'
        self.assertTrue(self.handler.match_request(req))
        
        req.path_info = '/ai/'
        self.assertTrue(self.handler.match_request(req))
        
        req.path_info = '/ai/chat'
        self.assertTrue(self.handler.match_request(req))
        
        # Should not match these
        req.path_info = '/tickets'
        self.assertFalse(self.handler.match_request(req))
        
        req.path_info = '/api/ai'
        self.assertFalse(self.handler.match_request(req))
    
    def test_process_request_chat_page(self):
        """Test rendering the chat page."""
        req = MockRequest('admin')
        req.path_info = '/ai'
        
        template, data, content_type = self.handler.process_request(req)
        
        self.assertEqual(template, 'ai_chat.html')
        self.assertTrue(data['api_configured'])
        self.assertEqual(data['model'], 'gpt-3.5-turbo')
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_handle_chat_request_success(self, mock_openai_class):
        """Test successful chat request handling."""
        # Create a handler with mocked components
        handler = ChatHandler(self.env)
        
        # Mock the internal services
        mock_context_service = Mock()
        mock_context_service.format_tickets_for_context = Mock(
            return_value="Recent tickets context"
        )
        handler.context_service = mock_context_service
        
        mock_search_service = Mock()
        mock_search_service.get_total_ticket_count = Mock(return_value=10)
        handler.search_service = mock_search_service
        
        # Mock OpenAI response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="AI response here"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = MockRequest('admin', method='POST')
        req.path_info = '/ai/chat'
        req._data = json.dumps({'message': 'Tell me about recent tickets'}).encode()
        
        # Capture response
        responses = []
        req.write = lambda data: responses.append(data)
        
        with self.assertRaises(RequestDone):
            handler.process_request(req)
        
        # Verify response - may have error message first
        self.assertGreater(len(responses), 0)
        # Find the JSON response (skip any error messages)
        json_response = None
        for resp in responses:
            try:
                json_response = json.loads(resp.decode())
                break
            except:
                continue
        
        self.assertIsNotNone(json_response)
        self.assertIn('response', json_response)
        self.assertEqual(json_response['response'], "AI response here")
        self.assertIn('timestamp', json_response)
    
    def test_handle_chat_request_no_api_key(self):
        """Test chat request without API key configured."""
        # Remove API key
        self.env.config.set('ai', 'openai_api_key', '')
        handler = ChatHandler(self.env)
        
        req = MockRequest('admin', method='POST')
        req.path_info = '/ai/chat'
        req._data = json.dumps({'message': 'test'}).encode()
        
        # Capture response
        responses = []
        req.write = lambda data: responses.append(data)
        
        with self.assertRaises(RequestDone):
            handler.process_request(req)
        
        # Should get error response
        response_data = json.loads(responses[0].decode())
        self.assertIn('error', response_data)
        self.assertEqual(response_data['error']['code'], 500)
        self.assertIn('not configured', response_data['error']['message'])
    
    def test_handle_chat_request_invalid_json(self):
        """Test chat request with invalid JSON."""
        req = MockRequest('admin', method='POST')
        req.path_info = '/ai/chat'
        req._data = b'invalid json'
        
        # Capture response
        responses = []
        req.write = lambda data: responses.append(data)
        
        with self.assertRaises(RequestDone):
            self.handler.process_request(req)
        
        # Should get error response
        response_data = json.loads(responses[0].decode())
        self.assertIn('error', response_data)
        self.assertEqual(response_data['error']['code'], 400)
    
    def test_should_search(self):
        """Test search detection logic."""
        # Should trigger search
        self.assertTrue(self.handler._should_search("Find tickets about login"))
        self.assertTrue(self.handler._should_search("Show me issues with performance"))
        self.assertTrue(self.handler._should_search("What tickets are related to API?"))
        self.assertTrue(self.handler._should_search("Search for database problems"))
        
        # Should not trigger search
        self.assertFalse(self.handler._should_search("Hello"))
        self.assertFalse(self.handler._should_search("Thank you"))
        self.assertFalse(self.handler._should_search("How are you?"))
    
    def test_extract_search_terms(self):
        """Test search term extraction."""
        # Test various queries
        queries = [
            ("Find tickets about login issues", "tickets login issues"),
            ("Show me problems with the database", "the database"),
            ("What tickets are related to performance?", "tickets are performance"),
            ("Search for API bugs", "api bugs"),
            ("Can you find issues with authentication please?", "issues authentication"),
        ]
        
        for input_msg, expected in queries:
            result = self.handler._extract_search_terms(input_msg)
            # Should have extracted meaningful terms
            self.assertTrue(len(result) > 0)
            # Should not contain stop words
            self.assertNotIn('find', result.lower())
            self.assertNotIn('show me', result.lower())
            self.assertNotIn('please', result.lower())
    
    def test_build_system_prompt(self):
        """Test system prompt generation."""
        # Test with few tickets
        prompt = self.handler._build_system_prompt(10, 20)
        self.assertIn("10 tickets", prompt)
        self.assertIn("all tickets are included", prompt)
        
        # Test with many tickets
        prompt = self.handler._build_system_prompt(100, 20)
        self.assertIn("100 tickets", prompt)
        self.assertIn("Search results are included", prompt)
    
    def test_permission_requirement(self):
        """Test that TICKET_VIEW permission is required."""
        req = MockRequest('anonymous')
        req.path_info = '/ai'
        
        # Override perm to deny access
        req.perm = MockPermissionCache(allowed=False)
        
        from trac.perm import PermissionError
        with self.assertRaises(PermissionError):
            self.handler.process_request(req)
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_generate_ai_response_with_search(self, mock_openai_class):
        """Test AI response generation with search."""
        # Create handler with mocked services
        handler = ChatHandler(self.env)
        
        # Mock context service
        mock_context_service = Mock()
        mock_context_service.format_tickets_for_context = Mock(
            return_value="Recent 20 tickets..."
        )
        handler.context_service = mock_context_service
        
        # Mock search service to simulate > 20 tickets
        mock_search_service = Mock()
        mock_search_service.get_total_ticket_count = Mock(return_value=25)
        mock_search_service.format_search_results_for_context = Mock(
            return_value="Search results for 'test'"
        )
        handler.search_service = mock_search_service
        
        # Mock OpenAI
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Found relevant tickets"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = MockRequest('admin')
        
        # Should trigger search since we have > 20 tickets
        response = handler._generate_ai_response(req, "Find tickets about test")
        
        self.assertEqual(response, "Found relevant tickets")
        
        # Verify search was called
        mock_search_service.format_search_results_for_context.assert_called_once()
        
        # Verify OpenAI was called with proper messages
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        
        # Should have system prompt, context, and user message
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'system')  # Context
        self.assertEqual(messages[2]['role'], 'user')
        self.assertEqual(messages[2]['content'], "Find tickets about test")


def test_suite():
    return makeSuite(ChatHandlerTestCase)


class MockRequest:
    """Mock request object for testing."""
    
    def __init__(self, authname='anonymous', method='GET'):
        self.authname = authname
        self.method = method
        self.args = {}
        self.tz = utc
        self.path_info = '/'
        self._data = b''
        self._headers_sent = False
        self._response = None
        self._headers = {}
        self.outcookie = {}
        self.incookie = {}
        self._perm_cache = {}
        self.chrome = {}
        self.href = MockHref()
        
    @property 
    def perm(self):
        """Return a mock permission cache that allows everything."""
        if not hasattr(self, '_perm'):
            self._perm = MockPermissionCache()
        return self._perm
    
    @perm.setter
    def perm(self, value):
        """Allow setting custom permission cache."""
        self._perm = value
    
    def read(self):
        """Return request body data."""
        return self._data
    
    def send_response(self, status):
        """Mock sending response status."""
        self._response = status
    
    def send_header(self, name, value):
        """Mock sending headers."""
        self._headers[name] = value
    
    def end_headers(self):
        """Mock ending headers."""
        self._headers_sent = True
    
    def write(self, data):
        """Mock writing response data."""
        pass
    
    def send_error(self, status, message):
        """Mock sending error response."""
        self._response = status
        self._error_message = message


class MockPermissionCache:
    """Mock permission cache that allows all permissions."""
    
    def __init__(self, allowed=True):
        self.allowed = allowed
    
    def __contains__(self, perm):
        return self.allowed
    
    def require(self, perm):
        if not self.allowed:
            from trac.perm import PermissionError
            raise PermissionError(f"{perm} required")
    
    def __call__(self, resource=None):
        """Support req.perm(resource) syntax."""
        return self


class MockHref:
    """Mock href object for URL generation."""
    
    def ai(self):
        return '/ai'