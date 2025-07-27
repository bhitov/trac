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

"""Tests for the Component REST API."""

import json
import unittest

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.ticket.model import Component
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.resource import ResourceNotFound


class ComponentAPITestCase(unittest.TestCase):
    """Test cases for Component REST API endpoints."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Grant necessary permissions
        # Components are managed under TICKET_ADMIN permissions
        try:
            PermissionSystem(self.env).grant_permission('anonymous', 'TICKET_ADMIN')
        except:
            pass  # Permission might already exist
        
        # Create test components
        component1 = Component(self.env)
        component1.name = 'test-component-1'
        component1.owner = 'user1'
        component1.description = 'First test component'
        component1.insert()
        
        component2 = Component(self.env)
        component2.name = 'test-component-2'
        component2.owner = 'user2'
        component2.description = 'Second test component'
        component2.insert()
        
        component3 = Component(self.env)
        component3.name = 'test-component-3'
        component3.owner = ''
        component3.description = 'Component without owner'
        component3.insert()
    
    def test_list_components(self):
        """Test GET /api/component - list all components."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/component')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('components', response)
        # Should have at least our 3 test components
        self.assertGreaterEqual(len(response['components']), 3)
        
        # Check component data
        component_names = [c['name'] for c in response['components']]
        self.assertIn('test-component-1', component_names)
        self.assertIn('test-component-2', component_names)
        self.assertIn('test-component-3', component_names)
        
        # Check structure
        c1 = next(c for c in response['components'] if c['name'] == 'test-component-1')
        self.assertEqual(c1['owner'], 'user1')
        self.assertEqual(c1['description'], 'First test component')
    
    def test_get_single_component(self):
        """Test GET /api/component/{name} - get single component."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/component/test-component-1')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-component-1')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['name'], 'test-component-1')
        self.assertEqual(response['owner'], 'user1')
        self.assertEqual(response['description'], 'First test component')
    
    def test_get_nonexistent_component(self):
        """Test GET /api/component/{name} - component not found."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/component/nonexistent')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'nonexistent')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '404 Not Found')
        self.assertIn('error', response)
    
    def test_create_component(self):
        """Test POST /api/component - create new component."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/component')
        
        new_component = {
            'name': 'new-component',
            'owner': 'newowner',
            'description': 'A new component'
        }
        req._content = json.dumps(new_component).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '201 Created')
        self.assertEqual(response['name'], 'new-component')
        self.assertEqual(response['owner'], 'newowner')
        self.assertEqual(response['description'], 'A new component')
        
        # Verify it was actually created
        component = Component(self.env, 'new-component')
        self.assertTrue(component.exists)
        self.assertEqual(component.owner, 'newowner')
    
    def test_create_component_duplicate(self):
        """Test POST /api/component - duplicate name error."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/component')
        
        duplicate = {
            'name': 'test-component-1',  # Already exists
            'description': 'Duplicate component'
        }
        req._content = json.dumps(duplicate).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '400 Bad Request')
        self.assertIn('error', response)
    
    def test_update_component(self):
        """Test PUT /api/component/{name} - update component."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='PUT', path_info='/api/component/test-component-1')
        
        updates = {
            'owner': 'newowner',
            'description': 'Updated description'
        }
        req._content = json.dumps(updates).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-component-1')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['owner'], 'newowner')
        self.assertEqual(response['description'], 'Updated description')
        
        # Verify it was actually updated
        component = Component(self.env, 'test-component-1')
        self.assertEqual(component.owner, 'newowner')
        self.assertEqual(component.description, 'Updated description')
    
    def test_delete_component(self):
        """Test DELETE /api/component/{name} - delete component."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        # Create a component with no tickets
        temp = Component(self.env)
        temp.name = 'temp-component'
        temp.insert()
        
        req = MockRequest(self.env, method='DELETE', path_info='/api/component/temp-component')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'temp-component')
        
        self.assertEqual(req.status_sent[0], '204 No Content')
        
        # Verify it was deleted
        with self.assertRaises(ResourceNotFound):
            component = Component(self.env, 'temp-component')
    
    def test_list_components_with_owner_filter(self):
        """Test GET /api/component with owner filter."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/component',
                          args={'owner': 'user1'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        # Should have only components owned by user1
        for component in response['components']:
            if component['name'].startswith('test-component-'):
                self.assertEqual(component['owner'], 'user1')
    
    def test_component_permissions(self):
        """Test component API respects permissions."""
        from trac.rest_api.components import ComponentsAPI
        handler = ComponentsAPI(self.env)
        
        # Remove permissions
        PermissionSystem(self.env).grant_permission('testuser', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_ADMIN')
        
        # Try to list components without permission
        req = MockRequest(self.env, method='GET', path_info='/api/component', authname='unprivileged')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '403 Forbidden')
        self.assertIn('error', response)


def test_suite():
    """Return the test suite."""
    return makeSuite(ComponentAPITestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')