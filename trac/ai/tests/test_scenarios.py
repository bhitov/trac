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

"""Scenario tests for AI chatbot with different ticket counts."""

import unittest
import json
from unittest.mock import patch, Mock, MagicMock

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.ai.chat_handler import ChatHandler
from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService


class AIScenarioTestCase(unittest.TestCase):
    """Test AI behavior in different scenarios."""
    
    def setUp(self):
        self.env = EnvironmentStub(
            enable=['trac.ai.*', 'trac.ticket.*'],
            default_data=True
        )
        self.env.config.set('ai', 'openai_api_key', 'test-key')
        self.env.config.set('ai', 'model', 'gpt-3.5-turbo')
        self.env.config.set('ai', 'search_threshold', '20')
        
        # Initialize components
        self.handler = ChatHandler(self.env)
        self.context_service = ContextService(self.env)
        self.search_service = FuzzySearchService(self.env)
    
    def _create_tickets(self, count, prefix="Ticket"):
        """Helper to create a specific number of tickets."""
        tickets = []
        for i in range(count):
            ticket = Ticket(self.env)
            ticket['summary'] = f'{prefix} {i+1}'
            ticket['description'] = f'Description for {prefix.lower()} {i+1}'
            ticket['status'] = 'new'
            ticket['priority'] = 'normal'
            ticket.insert()
            tickets.append(ticket)
        return tickets
    
    def _create_mock_request(self):
        """Create a mock request for testing."""
        from trac.util.datefmt import utc
        req = Mock()
        req.authname = 'admin'
        req.tz = utc
        req.perm = Mock()
        req.perm.require = Mock()
        req.perm.__contains__ = Mock(return_value=True)
        
        # Mock the perm() method to return a permission cache
        def mock_perm(resource=None):
            perm_cache = Mock()
            perm_cache.__contains__ = Mock(return_value=True)
            return perm_cache
        req.perm = mock_perm
        
        return req
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_scenario_less_than_20_tickets(self, mock_openai):
        """Test with less than 20 tickets - search should not be used."""
        # Create exactly 15 tickets
        self._create_tickets(15)
        
        # Verify ticket count
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 15)
        
        # Mock OpenAI
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Response without search"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = self._create_mock_request()
        
        # Make a request that would normally trigger search
        response = self.handler._generate_ai_response(req, "Find tickets about Ticket 5")
        
        # Verify OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Check the system prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        
        # System message should indicate all tickets are included
        system_msg = messages[0]['content']
        self.assertIn("15 tickets", system_msg)
        self.assertIn("all tickets are included", system_msg)
        self.assertIn("No search is needed", system_msg)
        
        # Context should include all tickets
        context_msg = messages[1]['content']
        self.assertIn("15 most recently updated tickets", context_msg)
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_scenario_exactly_20_tickets(self, mock_openai):
        """Test with exactly 20 tickets - at threshold."""
        # Create exactly 20 tickets
        self._create_tickets(20)
        
        # Verify ticket count
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 20)
        
        # Mock OpenAI
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Response at threshold"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = self._create_mock_request()
        
        # Make a search-like request
        response = self.handler._generate_ai_response(req, "Show me tickets about Ticket 10")
        
        # Check system prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        
        system_msg = messages[0]['content']
        self.assertIn("20 tickets", system_msg)
        self.assertIn("all tickets are included", system_msg)
    
    @patch('trac.ai.chat_handler.OpenAI')
    def test_scenario_more_than_20_tickets_with_search(self, mock_openai):
        """Test with more than 20 tickets - search should be available."""
        # Create 30 tickets with some specific ones for search
        self._create_tickets(25, "Regular Ticket")
        
        # Add specific tickets for search testing
        special_tickets = [
            ("Login Authentication Bug", "Users cannot login with SSO"),
            ("Performance Issue Dashboard", "Dashboard loads very slowly"),
            ("API Documentation Update", "REST API docs need updating"),
            ("Database Connection Error", "Connection pool exhausted"),
            ("Search Feature Enhancement", "Add fuzzy search capability"),
        ]
        
        for summary, desc in special_tickets:
            ticket = Ticket(self.env)
            ticket['summary'] = summary
            ticket['description'] = desc
            ticket['status'] = 'new'
            ticket['priority'] = 'high'
            ticket.insert()
        
        # Verify ticket count
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 30)  # 25 + 5
        
        # Mock OpenAI
        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Found login tickets"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        req = self._create_mock_request()
        
        # Make a search request
        response = self.handler._generate_ai_response(req, "Find tickets about login authentication")
        
        # Verify OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        
        # Check messages
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        
        # System message should indicate search is available
        system_msg = messages[0]['content']
        self.assertIn("30 tickets", system_msg)
        self.assertIn("Search results are included", system_msg)
        
        # Context should include both recent tickets and search results
        context_msg = messages[1]['content']
        # Should have recent tickets
        self.assertIn("most recently updated tickets", context_msg)
        # Should have search results
        self.assertIn("Search results for", context_msg)
        self.assertIn("login", context_msg.lower())
    
    def test_search_behavior_based_on_count(self):
        """Test that search behavior changes based on ticket count."""
        # Start with few tickets
        self._create_tickets(10)
        
        req = self._create_mock_request()
        
        # Test that search would not be performed
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 10)
        self.assertLess(total, int(self.handler.search_threshold))
        
        # Add more tickets to exceed threshold
        self._create_tickets(15, "Additional Ticket")
        
        # Now we should have 25 tickets
        total = self.search_service.get_total_ticket_count()
        self.assertEqual(total, 25)
        self.assertGreater(total, int(self.handler.search_threshold))
        
        # Verify search would be performed for appropriate queries
        should_search = self.handler._should_search("Find tickets about Additional")
        self.assertTrue(should_search)
    
    def test_context_limit_with_many_tickets(self):
        """Test that context respects the limit even with many tickets."""
        # Create 50 tickets
        self._create_tickets(50)
        
        req = self._create_mock_request()
        
        # Get recent tickets with default limit
        recent = self.context_service.get_recent_tickets(req)
        self.assertEqual(len(recent), 20)  # Should respect default limit
        
        # Test with custom limit
        recent_5 = self.context_service.get_recent_tickets(req, limit=5)
        self.assertEqual(len(recent_5), 5)
        
        # Verify they are recent tickets
        # Just check we got the expected number
        self.assertEqual(len(recent), 20)
        self.assertEqual(len(recent_5), 5)
    
    def test_search_with_no_results(self):
        """Test behavior when search returns no results."""
        # Create some tickets
        self._create_tickets(25)
        
        req = self._create_mock_request()
        
        # Search for something that doesn't exist
        results = self.search_service.search_tickets(req, "nonexistentterm12345")
        self.assertEqual(len(results), 0)
        
        # Format should handle no results gracefully
        formatted = self.search_service.format_search_results_for_context(req, "nonexistentterm12345")
        self.assertIn("No tickets or comments found", formatted)
    
    def test_mixed_permission_scenario(self):
        """Test with tickets having different permissions."""
        # Create tickets
        tickets = self._create_tickets(25)
        
        # Create a request with limited permissions
        req = self._create_mock_request()
        req.authname = 'user'
        
        # Mock permission to deny access to some tickets
        def mock_perm(resource=None):
            perm_cache = Mock()
            # Deny access to tickets with even IDs
            if resource and hasattr(resource, 'id'):
                try:
                    ticket_id = int(resource.id)
                    perm_cache.__contains__ = Mock(return_value=(ticket_id % 2 == 1))
                except:
                    perm_cache.__contains__ = Mock(return_value=True)
            else:
                perm_cache.__contains__ = Mock(return_value=True)
            return perm_cache
        
        req.perm = mock_perm
        
        # Get recent tickets - should only return odd-numbered ones
        recent = self.context_service.get_recent_tickets(req)
        
        # All returned tickets should have odd IDs
        for ticket in recent:
            self.assertEqual(ticket['id'] % 2, 1)


def test_suite():
    return makeSuite(AIScenarioTestCase)