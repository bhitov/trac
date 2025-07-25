# -*- coding: utf-8 -*-
"""
Test cases for handling None values in AI services.

These tests ensure that the AI components gracefully handle None values
from the database without throwing 'NoneType' object is not subscriptable errors.
"""

import unittest
from datetime import datetime

from trac.test import EnvironmentStub, MockRequest
from trac.ticket.model import Ticket
from trac.util.datefmt import utc

from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService


class NoneHandlingTestCase(unittest.TestCase):
    """Test handling of None values in AI services."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.context_service = ContextService(self.env)
        self.search_service = FuzzySearchService(self.env)
        self.req = MockRequest(self.env)
        
    def test_context_service_handles_none_description(self):
        """Test that context service handles tickets with None description."""
        # Create a ticket with None description
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket with null description'
        ticket['description'] = None  # This is the problematic case
        ticket['status'] = 'new'
        ticket['priority'] = 'normal'
        ticket['owner'] = 'testuser'
        ticket['component'] = 'test'
        ticket['milestone'] = ''
        ticket.insert()
        
        # This should not raise an exception
        try:
            context = self.context_service.format_tickets_for_context(self.req, include_comments=False, limit=1)
            self.assertIsInstance(context, str)
            self.assertIn('Test ticket with null description', context)
            # Should show empty description, not crash
            self.assertIn('Description: ', context)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Context service failed to handle None description")
            else:
                raise
    
    def test_context_service_handles_none_summary(self):
        """Test that context service handles tickets with None summary."""
        ticket = Ticket(self.env)
        ticket['summary'] = None  # This could also be problematic
        ticket['description'] = 'Test description'
        ticket['status'] = 'new'
        ticket['priority'] = 'normal'
        ticket['owner'] = 'testuser'
        ticket['component'] = 'test'
        ticket['milestone'] = ''
        ticket.insert()
        
        try:
            context = self.context_service.format_tickets_for_context(self.req, include_comments=False, limit=1)
            self.assertIsInstance(context, str)
            # Should show ticket ID when summary is None
            self.assertIn(f'Ticket #{ticket.id}', context)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Context service failed to handle None summary")
            else:
                raise
    
    def test_context_service_handles_multiple_none_fields(self):
        """Test handling of multiple None fields in a ticket."""
        ticket = Ticket(self.env)
        ticket['summary'] = None
        ticket['description'] = None
        ticket['status'] = None
        ticket['priority'] = None
        ticket['owner'] = None
        ticket['component'] = None
        ticket['milestone'] = None
        ticket.insert()
        
        try:
            context = self.context_service.format_tickets_for_context(self.req, include_comments=False, limit=1)
            self.assertIsInstance(context, str)
            # Should handle all None values gracefully
            self.assertIn('unknown', context)  # Should use fallback values
            self.assertIn('unassigned', context)
            self.assertIn('none', context)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Context service failed to handle multiple None fields")
            else:
                raise
    
    def test_context_service_handles_none_comments(self):
        """Test that context service handles comments with None content."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket'
        ticket['description'] = 'Test description'
        ticket.insert()
        
        # Manually insert a comment with None content
        with self.env.db_transaction as db:
            db("INSERT INTO ticket_change (ticket, time, author, field, newvalue) VALUES (%s, %s, %s, %s, %s)",
               (ticket.id, datetime.now(utc).microsecond, 'testuser', 'comment', None))
        
        try:
            context = self.context_service.format_tickets_for_context(self.req, include_comments=True, limit=1)
            self.assertIsInstance(context, str)
            # Should not crash even with None comment content
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Context service failed to handle None comment content")
            else:
                raise
    
    def test_search_service_handles_none_description(self):
        """Test that search service handles tickets with None description."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Searchable ticket'
        ticket['description'] = None
        ticket['status'] = 'new'
        ticket['priority'] = 'normal'
        ticket['owner'] = 'testuser'
        ticket.insert()
        
        try:
            results = self.search_service.search_tickets(self.req, 'searchable', limit=1)
            self.assertIsInstance(results, list)
            if results:  # If ticket was found
                # Should not crash when formatting for context
                context = self.search_service.format_search_results_for_context(self.req, 'searchable')
                self.assertIsInstance(context, str)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Search service failed to handle None description")
            else:
                raise
    
    def test_search_service_handles_none_comment_text(self):
        """Test that search service handles comments with None text."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket for comment search'
        ticket['description'] = 'Test description'
        ticket.insert()
        
        # Insert a comment with None content
        with self.env.db_transaction as db:
            db("INSERT INTO ticket_change (ticket, time, author, field, newvalue) VALUES (%s, %s, %s, %s, %s)",
               (ticket.id, datetime.now(utc).microsecond, 'testuser', 'comment', None))
        
        try:
            results = self.search_service.search_comments(self.req, 'test', limit=1)
            self.assertIsInstance(results, list)
            # Should not crash when processing comments with None text
            context = self.search_service.format_search_results_for_context(self.req, 'test')
            self.assertIsInstance(context, str)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Search service failed to handle None comment text")
            else:
                raise
    
    def test_relevance_calculation_with_none_values(self):
        """Test relevance calculation handles None title and content."""
        search_terms = ['test', 'null']
        
        # Test with None title
        try:
            score1 = self.search_service._calculate_relevance(None, 'test content', search_terms)
            self.assertIsInstance(score1, float)
            self.assertGreaterEqual(score1, 0.0)
        except TypeError:
            self.fail("Relevance calculation failed with None title")
        
        # Test with None content
        try:
            score2 = self.search_service._calculate_relevance('test title', None, search_terms)
            self.assertIsInstance(score2, float)
            self.assertGreaterEqual(score2, 0.0)
        except TypeError:
            self.fail("Relevance calculation failed with None content")
        
        # Test with both None
        try:
            score3 = self.search_service._calculate_relevance(None, None, search_terms)
            self.assertIsInstance(score3, float)
            self.assertEqual(score3, 0.0)
        except TypeError:
            self.fail("Relevance calculation failed with both None values")
    
    def test_edge_case_empty_vs_none(self):
        """Test the difference between empty strings and None values."""
        # Create tickets with empty strings vs None
        ticket1 = Ticket(self.env)
        ticket1['summary'] = ''  # Empty string
        ticket1['description'] = ''
        ticket1.insert()
        
        ticket2 = Ticket(self.env)
        ticket2['summary'] = None  # None value
        ticket2['description'] = None
        ticket2.insert()
        
        try:
            # Both should be handled gracefully
            context = self.context_service.format_tickets_for_context(self.req, include_comments=False, limit=2)
            self.assertIsInstance(context, str)
            # Should contain information about both tickets
            self.assertIn(f'Ticket #{ticket1.id}', context)
            self.assertIn(f'Ticket #{ticket2.id}', context)
        except TypeError as e:
            if "'NoneType' object is not subscriptable" in str(e):
                self.fail("Failed to handle mix of empty strings and None values")
            else:
                raise


def test_suite():
    """Return test suite for None handling tests."""
    return unittest.TestLoader().loadTestsFromTestCase(NoneHandlingTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')