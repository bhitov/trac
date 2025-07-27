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

"""Tests for the Version REST API."""

import json
import unittest
from datetime import datetime

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.ticket.model import Version
from trac.util.datefmt import to_utimestamp, utc
from trac.perm import PermissionSystem
from trac.web.api import RequestDone
from trac.resource import ResourceNotFound


class VersionAPITestCase(unittest.TestCase):
    """Test cases for Version REST API endpoints."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Grant necessary permissions
        # Versions are managed under TICKET_ADMIN permissions
        try:
            PermissionSystem(self.env).grant_permission('anonymous', 'TICKET_ADMIN')
        except:
            pass  # Permission might already exist
        
        # Create test versions
        version1 = Version(self.env)
        version1.name = 'test-version-1.0'
        version1.time = datetime(2025, 1, 1, tzinfo=utc)
        version1.description = 'First test version'
        version1.insert()
        
        version2 = Version(self.env)
        version2.name = 'test-version-2.0'
        version2.time = datetime(2025, 6, 1, tzinfo=utc)
        version2.description = 'Second test version'
        version2.insert()
        
        version3 = Version(self.env)
        version3.name = 'test-version-3.0'
        version3.time = None  # Version without release date
        version3.description = 'Unreleased version'
        version3.insert()
    
    def test_list_versions(self):
        """Test GET /api/version - list all versions."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/version')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertIn('versions', response)
        # Should have at least our 3 test versions
        self.assertGreaterEqual(len(response['versions']), 3)
        
        # Check version data
        version_names = [v['name'] for v in response['versions']]
        self.assertIn('test-version-1.0', version_names)
        self.assertIn('test-version-2.0', version_names)
        self.assertIn('test-version-3.0', version_names)
        
        # Check structure
        v1 = next(v for v in response['versions'] if v['name'] == 'test-version-1.0')
        self.assertEqual(v1['description'], 'First test version')
        self.assertIn('time', v1)
        self.assertIsNotNone(v1['time'])
    
    def test_get_single_version(self):
        """Test GET /api/version/{name} - get single version."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/version/test-version-1.0')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-version-1.0')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['name'], 'test-version-1.0')
        self.assertEqual(response['description'], 'First test version')
        self.assertIn('time', response)
        self.assertIsNotNone(response['time'])
    
    def test_get_nonexistent_version(self):
        """Test GET /api/version/{name} - version not found."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='GET', path_info='/api/version/nonexistent')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'nonexistent')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '404 Not Found')
        self.assertIn('error', response)
    
    def test_create_version(self):
        """Test POST /api/version - create new version."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/version')
        
        new_version = {
            'name': 'new-version-4.0',
            'time': '2025-12-31T00:00:00Z',
            'description': 'A new version'
        }
        req._content = json.dumps(new_version).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '201 Created')
        self.assertEqual(response['name'], 'new-version-4.0')
        self.assertEqual(response['description'], 'A new version')
        
        # Verify it was actually created
        version = Version(self.env, 'new-version-4.0')
        self.assertTrue(version.exists)
        self.assertEqual(version.description, 'A new version')
    
    def test_create_version_duplicate(self):
        """Test POST /api/version - duplicate name error."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='POST', path_info='/api/version')
        
        duplicate = {
            'name': 'test-version-1.0',  # Already exists
            'description': 'Duplicate version'
        }
        req._content = json.dumps(duplicate).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '400 Bad Request')
        self.assertIn('error', response)
    
    def test_update_version(self):
        """Test PUT /api/version/{name} - update version."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        req = MockRequest(self.env, method='PUT', path_info='/api/version/test-version-1.0')
        
        updates = {
            'description': 'Updated description',
            'time': '2025-02-01T00:00:00Z'
        }
        req._content = json.dumps(updates).encode('utf-8')
        req.read = lambda: req._content
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'test-version-1.0')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        self.assertEqual(response['description'], 'Updated description')
        
        # Verify it was actually updated
        version = Version(self.env, 'test-version-1.0')
        self.assertEqual(version.description, 'Updated description')
    
    def test_delete_version(self):
        """Test DELETE /api/version/{name} - delete version."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        # Create a version with no tickets
        temp = Version(self.env)
        temp.name = 'temp-version'
        temp.insert()
        
        req = MockRequest(self.env, method='DELETE', path_info='/api/version/temp-version')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, 'temp-version')
        
        self.assertEqual(req.status_sent[0], '204 No Content')
        
        # Verify it was deleted
        with self.assertRaises(ResourceNotFound):
            version = Version(self.env, 'temp-version')
    
    def test_list_versions_with_released_filter(self):
        """Test GET /api/version with released filter."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        # Test released=true (versions with time set)
        req = MockRequest(self.env, method='GET', path_info='/api/version',
                          args={'released': 'true'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '200 Ok')
        # Should have versions with release time
        for version in response['versions']:
            if version['name'].startswith('test-version-'):
                self.assertIsNotNone(version.get('time'))
        
        # Test released=false (versions without time)
        req2 = MockRequest(self.env, method='GET', path_info='/api/version',
                           args={'released': 'false'})
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req2, '')
        
        response2 = json.loads(req2.response_sent.getvalue())
        self.assertEqual(req2.status_sent[0], '200 Ok')
        # Should include our unreleased test version
        version_names = [v['name'] for v in response2['versions']]
        self.assertIn('test-version-3.0', version_names)
    
    def test_version_permissions(self):
        """Test version API respects permissions."""
        from trac.rest_api.versions import VersionsAPI
        handler = VersionsAPI(self.env)
        
        # Remove permissions
        PermissionSystem(self.env).grant_permission('testuser', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_VIEW')
        PermissionSystem(self.env).revoke_permission('anonymous', 'TICKET_ADMIN')
        
        # Try to list versions without permission
        req = MockRequest(self.env, method='GET', path_info='/api/version', authname='unprivileged')
        
        with self.assertRaises(RequestDone):
            handler.handle_request(req, '')
        
        response = json.loads(req.response_sent.getvalue())
        self.assertEqual(req.status_sent[0], '403 Forbidden')
        self.assertIn('error', response)


def test_suite():
    """Return the test suite."""
    return makeSuite(VersionAPITestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')