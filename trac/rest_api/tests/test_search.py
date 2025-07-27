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

"""Tests for the Search REST API."""

import json
import unittest

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.wiki.model import WikiPage
from trac.ticket.model import Ticket
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.search.api import ISearchSource
from trac.core import Component, implements


class SearchAPITestCase(unittest.TestCase):
    """Test cases for Search REST API endpoints."""
    
    def setUp(self):
        # Don't disable any components - use default environment
        self.env = EnvironmentStub(default_data=True)
        
        # Manually enable the search sources
        from trac.ticket.web_ui import TicketModule
        from trac.wiki.web_ui import WikiModule
        from trac.ticket.roadmap import MilestoneModule
        self.env.enable_component(TicketModule)
        self.env.enable_component(WikiModule)
        self.env.enable_component(MilestoneModule)
        
        # Grant necessary permissions
        # Search requires SEARCH_VIEW permission
        try:
            PermissionSystem(self.env).grant_permission('anonymous', 'SEARCH_VIEW')
            PermissionSystem(self.env).grant_permission('anonymous', 'WIKI_VIEW')
            PermissionSystem(self.env).grant_permission('anonymous', 'TICKET_VIEW')
        except:
            pass  # Permission might already exist
        
        # Create test wiki pages
        page1 = WikiPage(self.env, 'TestPage1')
        page1.text = 'This is a test page about Python programming and Trac'
        page1.save('author', 'Created test page')
        
        page2 = WikiPage(self.env, 'TestPage2')
        page2.text = 'Another page discussing Python web frameworks'
        page2.save('author', 'Created another test page')
        
        # Create test tickets
        ticket1 = Ticket(self.env)
        ticket1['summary'] = 'Python test ticket'
        ticket1['description'] = 'This ticket is about Python bugs'
        ticket1['reporter'] = 'tester'
        ticket1.insert()
        
        ticket2 = Ticket(self.env)
        ticket2['summary'] = 'Another test issue'
        ticket2['description'] = 'This is a different bug report'
        ticket2['reporter'] = 'tester'
        ticket2.insert()
    
    def test_search_all_resources(self):
        """Test GET /api/search - search all resource types."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': 'Python'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('results', response)
        self.assertIn('total', response)
        
        # Should find results in both wiki and tickets
        self.assertGreater(response['total'], 0)
        
        # Check result structure
        for result in response['results']:
            self.assertIn('href', result)
            self.assertIn('title', result)
            self.assertIn('excerpt', result)
            self.assertIn('author', result)
            self.assertIn('date', result)
            self.assertIn('resource', result)
    
    def test_search_with_filters(self):
        """Test GET /api/search with resource filters."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        # Search only in wiki
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': 'Python', 'wiki': 'on'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        
        # All results should be wiki pages
        for result in response['results']:
            self.assertEqual(result['resource'], 'wiki')
    
    def test_search_with_pagination(self):
        """Test GET /api/search with pagination."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': 'test', 'limit': '1', 'offset': '0'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(len(response['results']), 1)
        self.assertIn('total', response)
    
    def test_search_empty_query(self):
        """Test GET /api/search with empty query."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': ''})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '400 Bad Request')
        self.assertIn('error', response)
    
    def test_search_no_results(self):
        """Test GET /api/search with query that returns no results."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': 'xyzabc123notfound'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['total'], 0)
        self.assertEqual(len(response['results']), 0)
    
    def test_search_permissions(self):
        """Test search API respects permissions."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        # Remove permissions
        PermissionSystem(self.env).revoke_permission('anonymous', 'SEARCH_VIEW')
        
        # Try to search without permission
        req = MockRequest(self.env, method='GET', path_info='/api/search',
                          args={'q': 'test'}, authname='unprivileged')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '403 Forbidden')
        self.assertIn('error', response)
    
    def test_post_search(self):
        """Test POST /api/search - search with JSON body."""
        from trac.rest_api.search import SearchAPI
        handler = SearchAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/search')
        
        search_data = {
            'q': 'Python',
            'filters': ['wiki', 'ticket'],
            'limit': 10,
            'offset': 0
        }
        req._content = json.dumps(search_data).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('results', response)
        self.assertGreater(response['total'], 0)


def test_suite():
    """Return the test suite."""
    return makeSuite(SearchAPITestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')