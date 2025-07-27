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

"""Tests for the Timeline REST API."""

import json
import unittest
from datetime import datetime, timedelta

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.wiki.model import WikiPage
from trac.ticket.model import Ticket, Milestone
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.util.datefmt import utc, to_utimestamp


class TimelineAPITestCase(unittest.TestCase):
    """Test cases for Timeline REST API endpoints."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Enable timeline event providers
        from trac.ticket.web_ui import TicketModule
        from trac.wiki.web_ui import WikiModule
        from trac.ticket.roadmap import MilestoneModule
        self.env.enable_component(TicketModule)
        self.env.enable_component(WikiModule)
        self.env.enable_component(MilestoneModule)
        
        # Grant necessary permissions
        try:
            PermissionSystem(self.env).grant_permission('anonymous', 'TIMELINE_VIEW')
            PermissionSystem(self.env).grant_permission('anonymous', 'WIKI_VIEW')
            PermissionSystem(self.env).grant_permission('anonymous', 'TICKET_VIEW')
            PermissionSystem(self.env).grant_permission('anonymous', 'MILESTONE_VIEW')
        except:
            pass  # Permission might already exist
        
        # Create test data with specific timestamps
        now = datetime.now(utc)
        
        # Create wiki pages
        page1 = WikiPage(self.env, 'TimelinePage1')
        page1.text = 'Timeline test page 1'
        page1.save('wiki_author', 'Created timeline test page', now - timedelta(hours=2))
        
        page2 = WikiPage(self.env, 'TimelinePage2')
        page2.text = 'Timeline test page 2'
        page2.save('wiki_author', 'Created another timeline test page', now - timedelta(hours=1))
        
        # Create tickets
        ticket1 = Ticket(self.env)
        ticket1['summary'] = 'Timeline test ticket'
        ticket1['description'] = 'Testing timeline API'
        ticket1['reporter'] = 'ticket_reporter'
        ticket1.insert(when=now - timedelta(hours=3))
        
        # Create milestone
        milestone = Milestone(self.env)
        milestone.name = 'Timeline Test Milestone'
        milestone.due = now + timedelta(days=7)
        milestone.description = 'Test milestone for timeline'
        milestone.insert()
    
    def test_get_timeline_events(self):
        """Test GET /api/timeline - get timeline events."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/timeline')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('events', response)
        self.assertIn('total', response)
        self.assertGreater(response['total'], 0)
        
        # Check event structure
        for event in response['events']:
            self.assertIn('id', event)
            self.assertIn('type', event)
            self.assertIn('date', event)
            self.assertIn('author', event)
            self.assertIn('title', event)
            self.assertIn('description', event)
            self.assertIn('href', event)
    
    def test_timeline_with_filters(self):
        """Test GET /api/timeline with event type filters."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        # Filter for wiki events only
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          args={'wiki': 'on'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        
        # All events should be wiki type
        for event in response['events']:
            # The actual event type is just 'wiki'
            self.assertEqual(event['type'], 'wiki')
    
    def test_timeline_with_date_range(self):
        """Test GET /api/timeline with date range filters."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        now = datetime.now(utc)
        from_date = (now - timedelta(hours=2)).strftime('%Y-%m-%d')
        to_date = now.strftime('%Y-%m-%d')
        
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          args={'from': from_date, 'to': to_date})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        # Should have events from last 2 hours (wiki pages)
        self.assertGreaterEqual(len(response['events']), 2)
    
    def test_timeline_with_pagination(self):
        """Test GET /api/timeline with pagination."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          args={'limit': '2', 'offset': '0'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(len(response['events']), 2)
        self.assertIn('total', response)
        self.assertIn('limit', response)
        self.assertIn('offset', response)
    
    def test_timeline_permissions(self):
        """Test timeline API respects permissions."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        # Remove permissions
        PermissionSystem(self.env).revoke_permission('anonymous', 'TIMELINE_VIEW')
        
        # Try to get timeline without permission
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          authname='unprivileged')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '403 Forbidden')
        self.assertIn('error', response)
    
    def test_timeline_invalid_date_format(self):
        """Test GET /api/timeline with invalid date format."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          args={'from': 'invalid-date'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '400 Bad Request')
        self.assertIn('error', response)
    
    def test_timeline_daysback_parameter(self):
        """Test GET /api/timeline with daysback parameter."""
        from trac.rest_api.timeline import TimelineAPI
        handler = TimelineAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/timeline',
                          args={'daysback': '7'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('events', response)
        # Should have all test events from last 7 days
        self.assertGreater(len(response['events']), 0)


def test_suite():
    """Return the test suite."""
    return makeSuite(TimelineAPITestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')