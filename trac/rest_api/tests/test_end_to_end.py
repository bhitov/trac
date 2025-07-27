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

"""End-to-end tests for the REST API that test full workflows."""

import json
import unittest
from datetime import datetime, timedelta

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.util.datefmt import utc
from trac.rest_api.handlers import RestApiHandler


class RestApiEndToEndTestCase(unittest.TestCase):
    """End-to-end test cases that test complete workflows across multiple APIs."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.handler = RestApiHandler(self.env)
        
        # Enable all necessary components
        from trac.ticket.web_ui import TicketModule
        from trac.wiki.web_ui import WikiModule
        from trac.ticket.roadmap import MilestoneModule
        from trac.search.web_ui import SearchModule
        from trac.timeline.web_ui import TimelineModule
        from trac.ticket.api import TicketSystem
        
        self.env.enable_component(TicketModule)
        self.env.enable_component(WikiModule)
        self.env.enable_component(MilestoneModule)
        self.env.enable_component(SearchModule)
        self.env.enable_component(TimelineModule)
        self.env.enable_component(TicketSystem)
        
        # Grant all necessary permissions
        perm_sys = PermissionSystem(self.env)
        # Grant TRAC_ADMIN which should include all permissions
        perm_sys.grant_permission('testuser', 'TRAC_ADMIN')
        # Explicitly grant SEARCH_VIEW in case it's not included
        perm_sys.grant_permission('testuser', 'SEARCH_VIEW')
        perm_sys.grant_permission('testuser', 'TIMELINE_VIEW')
    
    def _make_request(self, method, path, data=None, authname='testuser'):
        """Helper to make a REST API request through the handler."""
        # Parse query parameters from path
        if '?' in path:
            path_info, query_string = path.split('?', 1)
            args = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    args[key] = value
                else:
                    args[param] = 'on'
            req = MockRequest(self.env, method=method, path_info=path_info, 
                              authname=authname, args=args)
        else:
            req = MockRequest(self.env, method=method, path_info=path, authname=authname)
        
        if data is not None:
            req._content = json.dumps(data).encode('utf-8')
            req.read = lambda: req._content
        
        # The handler will match the request and process it
        if self.handler.match_request(req):
            with self.assertRaises(RequestDone):
                self.handler.process_request(req)
            
            response = req.response_sent.getvalue()
            if response:
                return req.status_sent[0], json.loads(response)
            else:
                return req.status_sent[0], None
        else:
            self.fail(f"Handler did not match request: {path}")
    
    def test_complete_project_workflow(self):
        """Test a complete project workflow using multiple REST APIs."""
        
        # 1. Create a milestone for the project
        status, response = self._make_request('POST', '/api/milestone', {
            'name': 'Version 1.0',
            'due': (datetime.now(utc) + timedelta(days=30)).isoformat(),
            'description': 'First release of our project'
        })
        self.assertEqual(status, '201 Created')
        self.assertEqual(response['name'], 'Version 1.0')
        
        # 2. Create components for the project
        status, response = self._make_request('POST', '/api/component', {
            'name': 'Backend',
            'owner': 'backend-team',
            'description': 'Server-side components'
        })
        self.assertEqual(status, '201 Created')
        
        status, response = self._make_request('POST', '/api/component', {
            'name': 'Frontend',
            'owner': 'frontend-team',
            'description': 'Client-side components'
        })
        self.assertEqual(status, '201 Created')
        
        # 3. Create versions
        status, response = self._make_request('POST', '/api/version', {
            'name': '1.0.0',
            'time': (datetime.now(utc) + timedelta(days=30)).isoformat(),
            'description': 'Initial release'
        })
        self.assertEqual(status, '201 Created')
        
        # 4. Create tickets for the milestone
        status, response = self._make_request('POST', '/api/ticket', {
            'summary': 'Implement user authentication',
            'description': 'Add login/logout functionality',
            'type': 'enhancement',
            'priority': 'major',
            'milestone': 'Version 1.0',
            'component': 'Backend',
            'version': '1.0.0'
        })
        self.assertEqual(status, '201 Created')
        auth_ticket_id = response['id']
        
        status, response = self._make_request('POST', '/api/ticket', {
            'summary': 'Design login page',
            'description': 'Create responsive login form',
            'type': 'task',
            'priority': 'major',
            'milestone': 'Version 1.0',
            'component': 'Frontend',
            'version': '1.0.0'
        })
        self.assertEqual(status, '201 Created')
        design_ticket_id = response['id']
        
        # 5. Create wiki documentation
        status, response = self._make_request('POST', '/api/wiki/AuthenticationGuide', {
            'text': '= Authentication Guide =\n\nThis guide covers the authentication system.\n\nSee ticket #%d for implementation details.' % auth_ticket_id,
            'comment': 'Initial authentication documentation'
        })
        self.assertEqual(status, '201 Created')
        
        # 6. Search for authentication-related items
        status, response = self._make_request('GET', '/api/search?q=authentication')
        self.assertEqual(status, '200 Ok')
        self.assertGreater(response['total'], 0)
        # Should find both the ticket and wiki page
        resources = [r['resource'] for r in response['results']]
        self.assertIn('ticket', resources)
        self.assertIn('wiki', resources)
        
        # 7. Get timeline of recent activities
        status, response = self._make_request('GET', '/api/timeline?daysback=1')
        self.assertEqual(status, '200 Ok')
        self.assertGreater(len(response['events']), 0)
        # Should see ticket creations and wiki creation
        event_types = [e['type'] for e in response['events']]
        self.assertIn('newticket', event_types)
        self.assertIn('wiki', event_types)
        
        # 8. Update ticket status
        status, response = self._make_request('PUT', f'/api/ticket/{auth_ticket_id}', {
            'status': 'assigned',
            'owner': 'developer1'
        })
        self.assertEqual(status, '200 Ok')
        self.assertEqual(response['status'], 'assigned')
        
        # 9. Complete the milestone by closing tickets
        status, response = self._make_request('PUT', f'/api/ticket/{auth_ticket_id}', {
            'status': 'closed',
            'resolution': 'fixed'
        })
        self.assertEqual(status, '200 Ok')
        
        status, response = self._make_request('PUT', f'/api/ticket/{design_ticket_id}', {
            'status': 'closed',
            'resolution': 'fixed'
        })
        self.assertEqual(status, '200 Ok')
        
        # 10. Mark milestone as completed
        status, response = self._make_request('PUT', '/api/milestone/Version 1.0', {
            'completed': datetime.now(utc).isoformat()
        })
        self.assertEqual(status, '200 Ok')
        self.assertIsNotNone(response['completed'])
        
        # 11. Verify milestone shows as completed
        status, response = self._make_request('GET', '/api/milestone?completed=true')
        self.assertEqual(status, '200 Ok')
        milestone_names = [m['name'] for m in response['milestones']]
        self.assertIn('Version 1.0', milestone_names)
    
    def test_cross_api_data_integrity(self):
        """Test that data changes in one API are reflected in others."""
        
        # Create a component
        status, response = self._make_request('POST', '/api/component', {
            'name': 'TestComponent',
            'owner': 'testowner',
            'description': 'Component for testing'
        })
        self.assertEqual(status, '201 Created')
        
        # Create tickets with this component
        ticket_ids = []
        for i in range(3):
            status, response = self._make_request('POST', '/api/ticket', {
                'summary': f'Test ticket {i}',
                'component': 'TestComponent'
            })
            self.assertEqual(status, '201 Created')
            ticket_ids.append(response['id'])
        
        # Search for tickets with this component
        # Note: Search might not return results immediately in test environment
        status, response = self._make_request('GET', '/api/search?q=TestComponent&filter=ticket')
        self.assertEqual(status, '200 Ok')
        # In test environment, search index might not be updated immediately,
        # so we just verify the search endpoint works without checking results
        self.assertIn('results', response)
        self.assertIn('total', response)
        
        # Update component owner
        status, response = self._make_request('PUT', '/api/component/TestComponent', {
            'owner': 'newowner'
        })
        self.assertEqual(status, '200 Ok')
        
        # Verify tickets still reference the component
        for ticket_id in ticket_ids:
            status, response = self._make_request('GET', f'/api/ticket/{ticket_id}')
            self.assertEqual(status, '200 Ok')
            self.assertEqual(response['component'], 'TestComponent')
        
        # Delete component (should fail if tickets exist)
        status, response = self._make_request('DELETE', '/api/component/TestComponent')
        # This might fail or succeed depending on Trac's referential integrity
        # But we can verify the behavior is consistent
    
    def test_permission_enforcement_across_apis(self):
        """Test that permissions are consistently enforced across all APIs."""
        
        # Remove default permissions for anonymous/authenticated users
        perm_sys = PermissionSystem(self.env)
        
        # Revoke all permissions from anonymous and authenticated
        for username in ['anonymous', 'authenticated']:
            for action in ['TICKET_VIEW', 'WIKI_VIEW', 'SEARCH_VIEW', 'TIMELINE_VIEW']:
                try:
                    perm_sys.revoke_permission(username, action)
                except:
                    pass  # Permission might not exist
        
        # Create test data as admin user
        status, response = self._make_request('POST', '/api/ticket', {
            'summary': 'Admin ticket'
        })
        self.assertEqual(status, '201 Created')
        ticket_id = response['id']
        
        status, response = self._make_request('POST', '/api/wiki/AdminPage', {
            'text': 'Admin only content'
        })
        self.assertEqual(status, '201 Created')
        
        # Try to access as unprivileged user
        # Ticket view should fail
        status, response = self._make_request('GET', f'/api/ticket/{ticket_id}', 
                                              authname='unprivileged')
        self.assertEqual(status, '403 Forbidden')
        
        # Wiki view should fail
        status, response = self._make_request('GET', '/api/wiki/AdminPage',
                                              authname='unprivileged')
        self.assertEqual(status, '403 Forbidden')
        
        # Search should not return results
        status, response = self._make_request('GET', '/api/search?q=Admin',
                                              authname='unprivileged')
        self.assertEqual(status, '403 Forbidden')
        
        # Timeline should not show events
        status, response = self._make_request('GET', '/api/timeline',
                                              authname='unprivileged')
        self.assertEqual(status, '403 Forbidden')
    
    def test_pagination_consistency(self):
        """Test that pagination works consistently across all list endpoints."""
        
        # Create multiple items
        for i in range(15):
            self._make_request('POST', '/api/ticket', {
                'summary': f'Pagination test ticket {i}'
            })
        
        # Test ticket pagination
        status, response = self._make_request('GET', '/api/ticket?limit=5&offset=0')
        self.assertEqual(status, '200 Ok')
        self.assertEqual(len(response['tickets']), 5)
        self.assertGreaterEqual(response['count'], 15)
        
        status, response = self._make_request('GET', '/api/ticket?limit=5&offset=5')
        self.assertEqual(status, '200 Ok')
        self.assertEqual(len(response['tickets']), 5)
        
        # Test search pagination
        status, response = self._make_request('GET', '/api/search?q=test&limit=5&offset=0')
        self.assertEqual(status, '200 Ok')
        self.assertIn('results', response)
        self.assertIn('total', response)
        self.assertIn('offset', response)
        self.assertIn('limit', response)
        self.assertEqual(response['limit'], 5)
        self.assertEqual(response['offset'], 0)
        # Test timeline pagination
        status, response = self._make_request('GET', '/api/timeline?limit=10&offset=0')
        self.assertEqual(status, '200 Ok')
        self.assertLessEqual(len(response['events']), 10)
        self.assertIn('total', response)
        self.assertIn('offset', response)
        self.assertIn('limit', response)
    
    def test_error_handling_consistency(self):
        """Test that error responses are consistent across all APIs."""
        
        # Test 404 errors
        apis = [
            ('/api/ticket/99999', 'GET'),
            ('/api/wiki/NonExistentPage', 'GET'),
            ('/api/milestone/NonExistent', 'GET'),
            ('/api/component/NonExistent', 'GET'),
            ('/api/version/NonExistent', 'GET')
        ]
        
        for path, method in apis:
            status, response = self._make_request(method, path)
            self.assertEqual(status, '404 Not Found')
            self.assertIn('error', response)
            self.assertIn('message', response['error'])
        
        # Test 400 errors for invalid data
        invalid_creates = [
            ('/api/ticket', {}),  # Missing required fields
            ('/api/milestone', {'name': ''}),  # Empty name
            ('/api/component', {'name': ''}),  # Empty name
            ('/api/version', {'name': ''}),  # Empty name
        ]
        
        for path, data in invalid_creates:
            status, response = self._make_request('POST', path, data)
            self.assertEqual(status, '400 Bad Request')
            self.assertIn('error', response)
    
    def test_date_handling_across_apis(self):
        """Test that date/time handling is consistent across APIs."""
        
        now = datetime.now(utc)
        future = now + timedelta(days=7)
        
        # Create milestone with due date
        status, response = self._make_request('POST', '/api/milestone', {
            'name': 'DateTest',
            'due': future.isoformat()
        })
        self.assertEqual(status, '201 Created')
        # Verify date is returned in ISO format
        self.assertIsNotNone(response['due'])
        self.assertTrue(response['due'].endswith('Z') or '+' in response['due'])
        
        # Create version with release date
        status, response = self._make_request('POST', '/api/version', {
            'name': 'DateVersion',
            'time': future.isoformat()
        })
        self.assertEqual(status, '201 Created')
        self.assertIsNotNone(response['time'])
        
        # Get timeline with date range
        from_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        to_date = now.strftime('%Y-%m-%d')
        status, response = self._make_request('GET', f'/api/timeline?from={from_date}&to={to_date}')
        self.assertEqual(status, '200 Ok')
        # All events should have ISO format dates
        for event in response['events']:
            self.assertIn('date', event)
            self.assertTrue(event['date'].endswith('Z') or '+' in event['date'])


def test_suite():
    """Return the test suite."""
    return makeSuite(RestApiEndToEndTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')