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

"""Tests for the AI fuzzy search service."""

import unittest
from datetime import datetime

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.util.datefmt import utc
from trac.ai.search_service import FuzzySearchService


class FuzzySearchServiceTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.search_service = FuzzySearchService(self.env)
        self.req = MockRequest('admin')
        self.req.tz = utc
        
        # Create test tickets with searchable content
        self._create_test_tickets()
    
    def _create_test_tickets(self):
        """Create test tickets with specific content for searching."""
        test_data = [
            ('Fix login bug', 'The login form is broken and shows error', 'bug', 'high'),
            ('Add new feature for reports', 'We need a new reporting feature', 'enhancement', 'normal'),
            ('Database performance issue', 'Queries are running slowly', 'bug', 'critical'),
            ('Update documentation', 'Documentation needs updating for new API', 'task', 'low'),
            ('Login enhancement request', 'Add remember me option to login', 'enhancement', 'normal'),
            ('Report generation fails', 'PDF report crashes with large data', 'bug', 'high'),
            ('Performance optimization needed', 'Overall system performance degraded', 'enhancement', 'high'),
            ('Fix broken links in docs', 'Several documentation links are 404', 'bug', 'low'),
            ('Add user dashboard', 'Users want a personalized dashboard view', 'enhancement', 'normal'),
            ('Critical security patch', 'Security vulnerability in auth system', 'bug', 'critical'),
        ]
        
        self.test_tickets = []
        for i, (summary, description, ticket_type, priority) in enumerate(test_data):
            ticket = Ticket(self.env)
            ticket['summary'] = summary
            ticket['description'] = description
            ticket['type'] = ticket_type
            ticket['priority'] = priority
            ticket['status'] = 'new'
            ticket['owner'] = 'developer'
            ticket['component'] = 'component1'
            ticket['milestone'] = 'milestone1'
            ticket.insert()
            self.test_tickets.append(ticket)
            
            # Add comments to some tickets
            if 'login' in summary.lower():
                ticket.save_changes('alice', 'This login issue is affecting many users')
            if 'performance' in summary.lower():
                ticket.save_changes('bob', 'Performance degradation started after last update')
    
    def test_get_total_ticket_count(self):
        """Test getting total ticket count."""
        count = self.search_service.get_total_ticket_count()
        # Should have at least our test tickets
        self.assertGreaterEqual(count, len(self.test_tickets))
    
    def test_search_tickets_single_term(self):
        """Test searching tickets with a single term."""
        results = self.search_service.search_tickets(self.req, 'login')
        
        # Should find tickets with 'login' in summary or description
        self.assertGreater(len(results), 0)
        
        # Verify all results contain the search term
        for ticket in results:
            text = (ticket['summary'] + ' ' + ticket['description']).lower()
            self.assertIn('login', text)
    
    def test_search_tickets_multiple_terms(self):
        """Test searching with multiple terms."""
        results = self.search_service.search_tickets(self.req, 'performance issue')
        
        # Should find tickets matching both terms
        self.assertGreater(len(results), 0)
        
        # The most relevant should be the one with both terms
        first_result = results[0]
        text = (first_result['summary'] + ' ' + first_result['description']).lower()
        self.assertIn('performance', text)
        self.assertIn('issue', text)
    
    def test_search_comments(self):
        """Test searching in comments."""
        results = self.search_service.search_comments(self.req, 'users')
        
        # Should find comments mentioning 'users'
        self.assertGreater(len(results), 0)
        
        for result in results:
            self.assertIn('users', result['comment_text'].lower())
    
    def test_combined_search(self):
        """Test combined ticket and comment search."""
        results = self.search_service.combined_search(self.req, 'login')
        
        # Should have both tickets and comments sections
        self.assertIn('tickets', results)
        self.assertIn('comments', results)
        self.assertIn('total_results', results)
        
        # Should find some results
        self.assertGreater(results['total_results'], 0)
    
    def test_relevance_scoring(self):
        """Test that relevance scoring works correctly."""
        # Search for a term that appears in multiple tickets
        results = self.search_service.search_tickets(self.req, 'bug')
        
        # Results should find at least one ticket
        self.assertGreaterEqual(len(results), 1)
        
        # If we have multiple results, check that relevance scores are properly assigned
        if len(results) > 1:
            # Check that relevance scores decrease
            for i in range(len(results) - 1):
                self.assertGreaterEqual(results[i]['relevance'], results[i+1]['relevance'])
        
        # Verify all results have a relevance score
        for result in results:
            self.assertIn('relevance', result)
            self.assertIsInstance(result['relevance'], (int, float))
    
    def test_empty_search_query(self):
        """Test behavior with empty search query."""
        results = self.search_service.search_tickets(self.req, '')
        self.assertEqual(len(results), 0)
        
        results = self.search_service.search_comments(self.req, '')
        self.assertEqual(len(results), 0)
    
    def test_format_search_results(self):
        """Test formatting search results for AI context."""
        context = self.search_service.format_search_results_for_context(self.req, 'performance')
        
        # Should contain search results header
        self.assertIn("Search results for 'performance'", context)
        
        # Should have found some tickets
        self.assertIn("Tickets matching", context)
        self.assertIn("Ticket #", context)
    
    def test_format_no_results(self):
        """Test formatting when no results found."""
        context = self.search_service.format_search_results_for_context(self.req, 'nonexistentterm123')
        self.assertIn("No tickets or comments found", context)
    
    def test_permission_filtering(self):
        """Test that results respect permissions."""
        # This would require setting up permission policies
        # For now, just verify the search runs without error
        req = MockRequest('user')
        req.tz = utc
        
        results = self.search_service.search_tickets(req, 'bug')
        # Should return list (even if empty due to permissions)
        self.assertIsInstance(results, list)
    
    def test_search_limit(self):
        """Test that search respects the limit parameter."""
        # Create many tickets with the same term
        for i in range(30):
            ticket = Ticket(self.env)
            ticket['summary'] = f'Test search limit ticket {i}'
            ticket['description'] = 'Testing search limits'
            ticket.insert()
        
        # Search with a small limit
        results = self.search_service.search_tickets(self.req, 'search limit', limit=5)
        self.assertEqual(len(results), 5)


def test_suite():
    return makeSuite(FuzzySearchServiceTestCase)


class MockRequest:
    """Mock request object for testing."""
    
    def __init__(self, authname='anonymous'):
        self.authname = authname
        self.args = {}
        self.tz = utc
        self._perm_cache = {}
    
    def perm(self, resource=None):
        """Return a mock permission cache that allows everything."""
        return MockPermissionCache()


class MockPermissionCache:
    """Mock permission cache that allows all permissions."""
    
    def __contains__(self, perm):
        return True
    
    def require(self, perm):
        pass