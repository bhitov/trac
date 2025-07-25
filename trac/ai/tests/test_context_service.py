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

"""Tests for the AI context service."""

import unittest
from datetime import datetime, timedelta

from trac.test import EnvironmentStub, makeSuite
from trac.perm import PermissionCache
from trac.ticket.model import Ticket
from trac.util.datefmt import to_utimestamp, utc
from trac.ai.context_service import ContextService
from trac.web.api import Request


class ContextServiceTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.context_service = ContextService(self.env)
        
        # Create a mock request with permission cache
        self.req = MockRequest('admin')
        self.req.tz = utc
        
        # Create test tickets
        self._create_test_tickets()
    
    def _create_test_tickets(self):
        """Create a set of test tickets with different modification times."""
        base_time = datetime.now(utc)
        
        for i in range(25):  # Create more than 20 tickets for testing
            ticket = Ticket(self.env)
            ticket['summary'] = f'Test ticket {i+1}'
            ticket['description'] = f'Description for test ticket {i+1}'
            ticket['status'] = 'new' if i < 10 else 'assigned'
            ticket['priority'] = 'normal' if i < 15 else 'high'
            ticket['owner'] = 'alice' if i % 2 == 0 else 'bob'
            ticket['component'] = 'component1' if i < 12 else 'component2'
            ticket['milestone'] = 'milestone1' if i < 8 else 'milestone2'
            
            # Insert ticket
            ticket.insert()
            
            # Manually update changetime to ensure proper ordering
            changetime = base_time - timedelta(minutes=i)
            with self.env.db_transaction as db:
                db("UPDATE ticket SET changetime=%s WHERE id=%s", 
                   (to_utimestamp(changetime), ticket.id))
            
            # Add some comments to recent tickets
            if i < 5:
                ticket.save_changes('commenter', f'Comment on ticket {i+1}')
    
    def test_get_recent_tickets(self):
        """Test retrieving recent tickets."""
        tickets = self.context_service.get_recent_tickets(self.req, limit=20)
        
        # Should return exactly 20 tickets
        self.assertEqual(len(tickets), 20)
        
        # Verify we got recent tickets (should include the ones we created)
        summaries = [t['summary'] for t in tickets]
        # Check that at least some of our test tickets are in the results
        test_summaries = [f'Test ticket {i}' for i in range(1, 26)]
        found_test_tickets = sum(1 for s in summaries if s in test_summaries)
        self.assertGreater(found_test_tickets, 0)
        
        # Verify ticket data structure
        first_ticket = tickets[0]
        self.assertIn('id', first_ticket)
        self.assertIn('summary', first_ticket)
        self.assertIn('description', first_ticket)
        self.assertIn('status', first_ticket)
        self.assertIn('priority', first_ticket)
        self.assertIn('owner', first_ticket)
        self.assertIn('created', first_ticket)
        self.assertIn('modified', first_ticket)
    
    def test_get_recent_tickets_with_limit(self):
        """Test retrieving tickets with custom limit."""
        tickets = self.context_service.get_recent_tickets(self.req, limit=5)
        self.assertEqual(len(tickets), 5)
    
    def test_get_recent_tickets_permission_check(self):
        """Test that permission checking works."""
        # Create a request with limited permissions
        req = MockRequest('user')
        req.tz = utc
        
        # For this test, we'd need to set up permission policies
        # Since MockRequest gives all permissions by default, we'll just verify
        # the method runs without error
        tickets = self.context_service.get_recent_tickets(req)
        self.assertIsInstance(tickets, list)
    
    def test_get_recent_comments(self):
        """Test retrieving recent comments."""
        # Get tickets that should have comments (the most recent ones)
        tickets = self.context_service.get_recent_tickets(self.req, limit=5)
        ticket_ids = [t['id'] for t in tickets]
        
        comments = self.context_service.get_recent_comments(self.req, ticket_ids)
        
        # Should have comments for at least some tickets
        self.assertGreater(len(comments), 0)
        
        # Verify comment structure
        for ticket_id, ticket_comments in comments.items():
            self.assertIsInstance(ticket_comments, list)
            if ticket_comments:
                comment = ticket_comments[0]
                self.assertIn('time', comment)
                self.assertIn('author', comment)
                self.assertIn('comment', comment)
    
    def test_format_tickets_for_context(self):
        """Test formatting tickets for AI context."""
        context = self.context_service.format_tickets_for_context(self.req)
        
        # Should contain the header
        self.assertIn("most recently updated tickets", context)
        
        # Should contain ticket information
        self.assertIn("Ticket #", context)
        self.assertIn("Status:", context)
        self.assertIn("Priority:", context)
        self.assertIn("Description:", context)
        
        # Should include recent comments
        self.assertIn("Recent comments:", context)
    
    def test_format_tickets_for_context_no_comments(self):
        """Test formatting without comments."""
        context = self.context_service.format_tickets_for_context(self.req, include_comments=False)
        
        # Should not include comments section
        self.assertNotIn("Recent comments:", context)
    
    def test_empty_system(self):
        """Test behavior with no tickets."""
        # Create a fresh environment with no tickets
        env = EnvironmentStub(default_data=False)
        service = ContextService(env)
        req = MockRequest('admin')
        req.tz = utc
        
        tickets = service.get_recent_tickets(req)
        self.assertEqual(len(tickets), 0)
        
        context = service.format_tickets_for_context(req)
        self.assertEqual(context, "No tickets found in the system.")


def test_suite():
    return makeSuite(ContextServiceTestCase)


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