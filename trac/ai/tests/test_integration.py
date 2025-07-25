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

"""Integration tests for the AI chatbot plugin."""

import unittest
import json
from unittest.mock import patch, Mock

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.web.api import Request, RequestDone
from trac.web.href import Href
from trac.perm import PermissionCache
from trac.ai.chat_handler import ChatHandler
from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService


class AIIntegrationTestCase(unittest.TestCase):
    """Integration tests for AI plugin components."""
    
    def setUp(self):
        self.env = EnvironmentStub(
            enable=['trac.ai.*', 'trac.ticket.*'],
            default_data=True
        )
        self.env.config.set('ai', 'openai_api_key', 'test-key')
        self.env.config.set('ai', 'model', 'gpt-3.5-turbo')
        self.env.config.set('ai', 'max_context_tickets', '20')
        self.env.config.set('ai', 'search_threshold', '20')
        
        # Create tickets for testing
        self._create_test_tickets()
        
        # Initialize components
        self.handler = ChatHandler(self.env)
        self.context_service = ContextService(self.env)
        self.search_service = FuzzySearchService(self.env)
    
    def _create_test_tickets(self):
        """Create test tickets with various scenarios."""
        # Scenario 1: Less than 20 tickets (search should not be used)
        self.few_tickets = []
        for i in range(15):
            ticket = Ticket(self.env)
            ticket['summary'] = f'Test ticket {i+1}'
            ticket['description'] = f'Description for ticket {i+1}'
            ticket['status'] = 'new'
            ticket['priority'] = 'normal'
            ticket.insert()
            self.few_tickets.append(ticket)
        
        # Add some with specific keywords for search testing
        special_tickets = [
            ('Login bug in authentication', 'Users cannot login with valid credentials'),
            ('Performance issue with reports', 'Report generation is very slow'),
            ('Documentation update needed', 'API docs are outdated'),
        ]
        
        for summary, description in special_tickets:
            ticket = Ticket(self.env)
            ticket['summary'] = summary
            ticket['description'] = description
            ticket['status'] = 'new'
            ticket['priority'] = 'high'
            ticket.insert()
            self.few_tickets.append(ticket)
    
    def _create_mock_request(self, path='/ai', method='GET', authname='admin', data=None):
        """Create a mock request object that works with Trac components."""
        from trac.util.datefmt import utc
        
        req = Mock()
        req.environ = {'REQUEST_METHOD': method}
        req.path_info = path
        req.method = method
        req.authname = authname
        req.args = {}
        req.chrome = {}
        req.tz = utc
        req.href = Href('/myproject')
        req.abs_href = Href('http://example.com/myproject')
        
        # Create permission cache that works with component checks
        class TestPermissionCache:
            def __init__(self, env, username):
                self.env = env
                self.username = username
                
            def __contains__(self, perm):
                return True
                
            def require(self, perm):
                pass
                
            def __call__(self, resource=None):
                return self
        
        req.perm = TestPermissionCache(self.env, authname)
        
        if data:
            req.read = Mock(return_value=json.dumps(data).encode('utf-8'))
        
        # Mock response methods
        req._response = None
        req._headers = {}
        req._data = []
        
        def send_response(code):
            req._response = code
        
        def send_header(name, value):
            req._headers[name] = value
        
        def end_headers():
            pass
        
        def write(data):
            req._data.append(data)
        
        req.send_response = Mock(side_effect=send_response)
        req.send_header = Mock(side_effect=send_header)
        req.end_headers = Mock(side_effect=end_headers)
        req.write = Mock(side_effect=write)
        
        return req
    
    def test_plugin_registration(self):
        """Test that AI plugin components are properly registered."""
        # Check that components are available
        self.assertIsNotNone(self.handler)
        self.assertIsNotNone(self.context_service)
        self.assertIsNotNone(self.search_service)
        
        # Check that handler is registered as IRequestHandler
        from trac.web.api import IRequestHandler
        
        # For EnvironmentStub, we can check if the handler matches requests
        req = self._create_mock_request(path='/ai')
        self.assertTrue(self.handler.match_request(req),
                       "ChatHandler should match /ai requests")
    
    def test_ai_endpoint_matching(self):
        """Test that AI endpoints are matched correctly."""
        test_cases = [
            ('/ai', True),
            ('/ai/', True),
            ('/ai/chat', True),
            ('/api/ai', False),
            ('/tickets', False),
        ]
        
        for path, should_match in test_cases:
            req = self._create_mock_request(path=path)
            result = self.handler.match_request(req)
            if should_match:
                self.assertTrue(result, f"Path {path} should match")
            else:
                self.assertFalse(result, f"Path {path} should not match")
    
    def test_permission_check(self):
        """Test that TICKET_VIEW permission is required."""
        req = self._create_mock_request(authname='anonymous')
        req.perm = Mock()
        req.perm.require = Mock(side_effect=PermissionError("TICKET_VIEW required"))
        
        with self.assertRaises(PermissionError):
            self.handler.process_request(req)
    
    def test_context_with_few_tickets(self):
        """Test context generation with less than 20 tickets."""
        req = self._create_mock_request()
        
        # Get total count
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 18)  # 15 + 3 special tickets
        
        # Get recent tickets
        tickets = self.context_service.get_recent_tickets(req)
        self.assertEqual(len(tickets), 18)  # Should return all tickets
        
        # Format context
        context = self.context_service.format_tickets_for_context(req)
        self.assertIn("18 most recently updated tickets", context)
        self.assertIn("Test ticket", context)
        self.assertIn("Login bug", context)
    
    def test_search_functionality(self):
        """Test search service functionality."""
        req = self._create_mock_request()
        
        # Test single term search
        results = self.search_service.search_tickets(req, 'login')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['summary'], 'Login bug in authentication')
        
        # Test multiple term search
        results = self.search_service.search_tickets(req, 'performance report')
        self.assertGreater(len(results), 0)
        # Should find the performance issue ticket
        summaries = [r['summary'] for r in results]
        self.assertIn('Performance issue with reports', summaries)
        
        # Test combined search
        combined = self.search_service.combined_search(req, 'bug')
        self.assertIn('tickets', combined)
        self.assertIn('comments', combined)
        self.assertGreater(combined['total_results'], 0)
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_chat_request_success(self, mock_openai):
        """Test successful chat request handling."""
        # Mock OpenAI response
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Here are the recent tickets..."))]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create chat request
        req = self._create_mock_request(
            path='/ai/chat',
            method='POST',
            data={'message': 'Show me recent tickets'}
        )
        
        # Track when RequestDone is raised
        request_done_raised = False
        
        # Process request
        try:
            self.handler.process_request(req)
        except RequestDone:
            request_done_raised = True
        except Exception as e:
            self.fail(f"Unexpected exception: {type(e).__name__}: {e}")
        
        # Debug: print what happened
        if hasattr(req, '_data') and req._data:
            print(f"Response data: {req._data}")
            print(f"RequestDone raised: {request_done_raised}")
            print(f"Number of responses: {len(req._data)}")
        
        # RequestDone should have been raised
        self.assertTrue(request_done_raised, "RequestDone should have been raised")
        
        # Should only have one response
        self.assertEqual(len(req._data), 1, "Should only have one response")
        
        # Verify response
        self.assertEqual(req._response, 200)
        self.assertIn('application/json', req._headers.get('Content-Type', ''))
        
        # Check response data
        response_data = json.loads(req._data[0].decode('utf-8'))
        self.assertIn('response', response_data)
        self.assertIn('timestamp', response_data)
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_search_threshold_behavior(self, mock_openai):
        """Test that search is not triggered when tickets < threshold."""
        # Current tickets (18) < threshold (20)
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Response"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = self._create_mock_request(
            path='/ai/chat',
            method='POST',
            data={'message': 'Find tickets about login'}  # Search-like query
        )
        
        # Process request
        try:
            self.handler.process_request(req)
        except RequestDone:
            pass
        
        # Check OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Verify the system message mentions no search is needed
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        system_message = messages[0]['content']
        self.assertIn("18 tickets", system_message)
        self.assertIn("all tickets are included", system_message)
    
    def test_many_tickets_scenario(self):
        """Test behavior with more than threshold tickets."""
        # Add more tickets to exceed threshold
        for i in range(10):
            ticket = Ticket(self.env)
            ticket['summary'] = f'Additional ticket {i+1}'
            ticket['description'] = 'Extra ticket for testing'
            ticket.insert()
        
        # Now we should have 28 tickets (18 + 10)
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 28)
        
        # Context should only show 20 most recent
        req = self._create_mock_request()
        tickets = self.context_service.get_recent_tickets(req)
        self.assertEqual(len(tickets), 20)
    
    def test_search_term_extraction(self):
        """Test search term extraction from user queries."""
        test_cases = [
            ("Find tickets about login issues", ["login", "issues"]),
            ("Show me all bugs related to performance", ["all", "bugs", "performance"]),
            ("What tickets mention database?", ["what", "tickets", "mention", "database"]),
            ("Search for authentication problems", ["authentication", "problems"]),
            ("Tell me about issues with the API", ["the", "api"]),
        ]
        
        for query, expected_terms in test_cases:
            extracted = self.handler._extract_search_terms(query)
            
            # Should not contain stop phrases
            self.assertNotIn('find', extracted.lower())
            self.assertNotIn('show me', extracted.lower())
            self.assertNotIn('search for', extracted.lower())
            self.assertNotIn('tell me about', extracted.lower())
            self.assertNotIn('issues with', extracted.lower())
            self.assertNotIn('tickets about', extracted.lower())
            
            # Should contain meaningful terms
            for term in expected_terms:
                self.assertIn(term, extracted.lower(), 
                             f"Expected '{term}' in extracted terms '{extracted}'")
    
    def test_error_handling(self):
        """Test various error scenarios."""
        # Test without API key
        self.env.config.set('ai', 'openai_api_key', '')
        handler_no_key = ChatHandler(self.env)
        
        req = self._create_mock_request(
            path='/ai/chat',
            method='POST',
            data={'message': 'test'}
        )
        
        try:
            handler_no_key.process_request(req)
        except RequestDone:
            pass
        
        self.assertEqual(req._response, 500)
        response_data = json.loads(req._data[0].decode('utf-8'))
        self.assertIn('error', response_data)
        self.assertIn('not configured', response_data['error']['message'])
        
        # Test with invalid JSON
        req = self._create_mock_request(path='/ai/chat', method='POST')
        req.read = Mock(return_value=b'invalid json')
        
        # Reset handler with API key
        self.env.config.set('ai', 'openai_api_key', 'test-key')
        handler = ChatHandler(self.env)
        
        req._data = []  # Reset data
        try:
            handler.process_request(req)
        except RequestDone:
            pass
        
        self.assertEqual(req._response, 400)
        response_data = json.loads(req._data[0].decode('utf-8'))
        self.assertIn('error', response_data)
        self.assertIn('Invalid request', response_data['error']['message'])


def test_suite():
    return makeSuite(AIIntegrationTestCase)