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

"""Tests for the Milestone REST API."""

import json
import unittest
from datetime import datetime

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.ticket.model import Milestone, Ticket
from trac.util.datefmt import to_utimestamp, utc
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.resource import ResourceNotFound


class MilestoneAPITestCase(unittest.TestCase):
    """Test cases for Milestone REST API endpoints."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Grant necessary permissions
        # Milestones are managed under TICKET_ADMIN and TICKET_VIEW permissions
        # Default data already includes TICKET_VIEW for anonymous
        try:
            PermissionSystem(self.env).grant_permission('anonymous', 'TICKET_ADMIN')
        except:
            pass  # Permission might already exist
        
        # Create test milestones with unique names
        milestone1 = Milestone(self.env)
        milestone1.name = 'test-milestone-1'
        milestone1.description = 'First test milestone'
        milestone1.due = datetime(2025, 3, 1, tzinfo=utc)
        milestone1.insert()
        
        milestone2 = Milestone(self.env)
        milestone2.name = 'test-milestone-2'
        milestone2.description = 'Second test milestone'
        milestone2.due = datetime(2025, 6, 1, tzinfo=utc)
        milestone2.insert()
        
        # Create completed milestone
        milestone3 = Milestone(self.env)
        milestone3.name = 'test-milestone-3'
        milestone3.description = 'Completed milestone'
        milestone3.completed = datetime(2025, 1, 15, tzinfo=utc)
        milestone3.insert()
    
    def test_list_milestones(self):
        """Test GET /api/milestone - list all milestones."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/milestone')
        
        # This should list all milestones
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('milestones', response)
        # Should have at least our 3 test milestones
        self.assertGreaterEqual(len(response['milestones']), 3)
        
        # Check milestone data
        milestone_names = [m['name'] for m in response['milestones']]
        self.assertIn('test-milestone-1', milestone_names)
        self.assertIn('test-milestone-2', milestone_names)
        self.assertIn('test-milestone-3', milestone_names)
        
        # Check structure
        m1 = next(m for m in response['milestones'] if m['name'] == 'test-milestone-1')
        self.assertEqual(m1['description'], 'First test milestone')
        self.assertIn('due', m1)
        self.assertIsNone(m1.get('completed'))
    
    def test_get_single_milestone(self):
        """Test GET /api/milestone/{name} - get single milestone."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/milestone/test-milestone-1')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-milestone-1')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['name'], 'test-milestone-1')
        self.assertEqual(response['description'], 'First test milestone')
        self.assertIn('due', response)
        self.assertIsNotNone(response['due'])
    
    def test_get_nonexistent_milestone(self):
        """Test GET /api/milestone/{name} - milestone not found."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/milestone/nonexistent')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'nonexistent')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '404 Not Found')
        self.assertIn('error', response)
    
    def test_create_milestone(self):
        """Test POST /api/milestone - create new milestone."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/milestone')
        
        new_milestone = {
            'name': 'new-milestone',
            'description': 'A new milestone',
            'due': '2025-12-31T00:00:00Z'
        }
        req._content = json.dumps(new_milestone).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '201 Created')
        self.assertEqual(response['name'], 'new-milestone')
        self.assertEqual(response['description'], 'A new milestone')
        
        # Verify it was actually created
        milestone = Milestone(self.env, 'new-milestone')
        self.assertTrue(milestone.exists)
        self.assertEqual(milestone.description, 'A new milestone')
    
    def test_create_milestone_duplicate(self):
        """Test POST /api/milestone - duplicate name error."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/milestone')
        
        duplicate = {
            'name': 'test-milestone-1',  # Already exists
            'description': 'Duplicate milestone'
        }
        req._content = json.dumps(duplicate).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '400 Bad Request')
        self.assertIn('error', response)
    
    def test_update_milestone(self):
        """Test PUT /api/milestone/{name} - update milestone."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='PUT', path_info='/api/milestone/test-milestone-1')
        
        updates = {
            'description': 'Updated description',
            'due': '2025-04-01T00:00:00Z'
        }
        req._content = json.dumps(updates).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-milestone-1')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['description'], 'Updated description')
        
        # Verify it was actually updated
        milestone = Milestone(self.env, 'test-milestone-1')
        self.assertEqual(milestone.description, 'Updated description')
    
    def test_complete_milestone(self):
        """Test PUT /api/milestone/{name} - mark as completed."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='PUT', path_info='/api/milestone/test-milestone-1')
        
        updates = {
            'completed': '2025-02-01T00:00:00Z'
        }
        req._content = json.dumps(updates).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-milestone-1')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIsNotNone(response.get('completed'))
        
        # Verify it was marked completed
        milestone = Milestone(self.env, 'test-milestone-1')
        self.assertTrue(milestone.is_completed)
    
    def test_delete_milestone(self):
        """Test DELETE /api/milestone/{name} - delete milestone."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        # Create a milestone with no tickets
        temp = Milestone(self.env)
        temp.name = 'temp-milestone'
        temp.insert()
        
        req = MockRequest(self.env, method='DELETE', path_info='/api/milestone/temp-milestone')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'temp-milestone')
        
        self.assertEqual(req.status_sent[0], '204 No Content')
        
        # Verify it was deleted
        with self.assertRaises(ResourceNotFound):
            milestone = Milestone(self.env, 'temp-milestone')
    
    def test_delete_milestone_with_retarget(self):
        """Test DELETE /api/milestone/{name} with retarget parameter."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        # Create a ticket in test-milestone-1
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket'
        ticket['milestone'] = 'test-milestone-1'
        ticket.insert()
        
        req = MockRequest(self.env, method='DELETE', path_info='/api/milestone/test-milestone-1',
                          args={'retarget': 'test-milestone-2'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-milestone-1')
        
        self.assertEqual(req.status_sent[0], '204 No Content')
        
        # Verify ticket was retargeted
        ticket = Ticket(self.env, ticket.id)
        self.assertEqual(ticket['milestone'], 'test-milestone-2')
        
        # Verify milestone was deleted
        with self.assertRaises(ResourceNotFound):
            milestone = Milestone(self.env, 'test-milestone-1')
    
    def test_list_milestones_with_filters(self):
        """Test GET /api/milestone with completed filter."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/milestone',
                          args={'completed': 'false'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        # Should have at least our 2 incomplete test milestones
        self.assertGreaterEqual(len(response['milestones']), 2)
        
        # Now test completed=true
        req2 = MockRequest(self.env, method='GET', path_info='/api/milestone',
                           args={'completed': 'true'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req2, '')
        
        response2 = json.loads(req2.response_sent.getvalue())
        self.assertEqual(req2.status_sent[0], '200 Ok')
        # Should have at least our 1 completed test milestone
        self.assertGreaterEqual(len(response2['milestones']), 1)
        # Check that our test milestone is in the results
        milestone_names = [m['name'] for m in response2['milestones']]
        self.assertIn('test-milestone-3', milestone_names)
    
    def test_milestone_permissions(self):
        """Test milestone API respects permissions."""
        from trac.rest_api.milestones import MilestonesAPI
        handler = MilestonesAPI(self.env)
        
        # Remove all permissions - first grant TICKET_VIEW to a specific user, then revoke from anonymous
        PermissionSystem(self.env).grant_permission('testuser', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_ADMIN')
        
        # Create request with a real authname to get PermissionCache instead of MockPerm
        req = MockRequest(self.env, method='GET', path_info='/api/milestone', authname='unprivileged')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '403 Forbidden')
        self.assertIn('error', response)


def test_suite():
    """Return the test suite."""
    return makeSuite(MilestoneAPITestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')