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

"""Unit tests for the base REST API handler."""

import json
import unittest
from datetime import datetime

from trac.core import TracError
from trac.resource import Resource, ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.util.datefmt import to_utimestamp, from_utimestamp, utc
from trac.web.api import RequestDone

from trac.rest_api.base import BaseRESTHandler


class MockModel:
    """Mock model class for testing."""
    
    def __init__(self, env, id=None):
        self.env = env
        if isinstance(id, str):
            id = int(id) if id.isdigit() else None
        self.id = id
        self.fields = {}
        self._exists = id is not None
        
        if id == 999:
            raise ResourceNotFound("Mock not found")
        
        if id:
            self.fields = {
                'name': f'Mock {id}',
                'value': id * 10,
                'created': datetime.now(utc)
            }
    
    @property
    def resource(self):
        return Resource('mock', self.id)
    
    def __getitem__(self, key):
        return self.fields.get(key)
    
    def __setitem__(self, key, value):
        self.fields[key] = value
    
    def insert(self):
        if self._exists:
            raise TracError("Already exists")
        self.id = 42
        self._exists = True
    
    def save_changes(self, author, comment):
        if not self._exists:
            raise TracError("Does not exist")
    
    def delete(self):
        if not self._exists:
            raise TracError("Does not exist")
        self._exists = False


class MockRESTHandler(BaseRESTHandler):
    """Mock REST handler for testing base functionality."""
    
    @property
    def model_class(self):
        return MockModel
    
    @property
    def resource_name(self):
        return 'MOCK'
    
    @property
    def collection_name(self):
        return 'mocks'
    
    def _get_resources_list(self, req, limit, offset):
        # Return mock list
        resources = []
        for i in range(1, 6):  # 5 mock resources
            if i > offset and len(resources) < limit:
                resources.append(MockModel(self.env, i))
        return resources
    
    def _get_resources_count(self, req):
        return 5
    
    def _serialize_resource(self, resource, detailed=False):
        data = {
            'id': resource.id,
            'name': resource['name'],
            'value': resource['value']
        }
        if detailed:
            data['created'] = self._serialize_datetime(resource['created'])
        return data
    
    def _set_resource_fields(self, resource, data, req):
        resource['name'] = data.get('name', 'New Mock')
        resource['value'] = data.get('value', 0)
        resource['created'] = datetime.now(utc)
    
    def _update_resource_fields(self, resource, data, req):
        changes = []
        for field in ['name', 'value']:
            if field in data:
                old_value = resource[field]
                if old_value != data[field]:
                    resource[field] = data[field]
                    changes.append((field, old_value, data[field]))
        return changes
    
    def _save_new_resource(self, resource, req):
        resource.insert()
    
    def _save_resource_changes(self, resource, changes, req, data):
        comment = data.get('comment', '')
        resource.save_changes(req.authname, comment)


class BaseRESTHandlerTestCase(unittest.TestCase):
    """Test cases for the base REST handler."""
    
    def setUp(self):
        self.env = EnvironmentStub()
        self.handler = MockRESTHandler(self.env)
    
    def _make_request(self, method='GET', data=None):
        """Create a mock request."""
        req = MockRequest(self.env, method=method, authname='testuser')
        
        # Mock permission system - grant all permissions
        req.perm = MockPermissions()
        
        # Add request body data
        if data:
            req.data = json.dumps(data).encode('utf-8')
            
            # Mock read method
            def mock_read():
                return req.data
            req.read = mock_read
        
        # Mock response methods
        req._status = None
        req._headers = {}
        req._data = None
        
        def mock_send_response(status):
            req._status = status
        
        def mock_send_header(name, value):
            req._headers[name] = value
        
        def mock_end_headers():
            pass
        
        def mock_write(data):
            req._data = data
        
        req.send_response = mock_send_response
        req.send_header = mock_send_header
        req.end_headers = mock_end_headers
        req.write = mock_write
        
        return req
    
    def test_list_resources(self):
        """Test listing resources."""
        req = self._make_request('GET')
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '')
        
        self.assertEqual(req._status, 200)
        data = json.loads(req._data.decode('utf-8'))
        
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['mocks']), 5)
        self.assertEqual(data['mocks'][0]['name'], 'Mock 1')
    
    def test_list_with_pagination(self):
        """Test listing with pagination."""
        req = self._make_request('GET')
        req.args['limit'] = '2'
        req.args['offset'] = '2'
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '')
        
        data = json.loads(req._data.decode('utf-8'))
        
        self.assertEqual(len(data['mocks']), 2)
        self.assertEqual(data['limit'], 2)
        self.assertEqual(data['offset'], 2)
        self.assertEqual(data['mocks'][0]['name'], 'Mock 3')
    
    def test_get_single_resource(self):
        """Test getting a single resource."""
        req = self._make_request('GET')
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '2')
        
        data = json.loads(req._data.decode('utf-8'))
        
        self.assertEqual(data['id'], 2)
        self.assertEqual(data['name'], 'Mock 2')
        self.assertIn('created', data)  # Detailed view
    
    def test_get_nonexistent_resource(self):
        """Test getting a nonexistent resource."""
        req = self._make_request('GET')
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '999')
        
        self.assertEqual(req._status, 404)
        data = json.loads(req._data.decode('utf-8'))
        self.assertIn('error', data)
    
    def test_create_resource(self):
        """Test creating a resource."""
        req = self._make_request('POST', data={
            'name': 'New Resource',
            'value': 123
        })
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '')
        
        self.assertEqual(req._status, 201)
        data = json.loads(req._data.decode('utf-8'))
        
        self.assertEqual(data['id'], 42)
        self.assertEqual(data['name'], 'New Resource')
        self.assertEqual(data['value'], 123)
    
    def test_update_resource(self):
        """Test updating a resource."""
        req = self._make_request('PUT', data={
            'name': 'Updated Name',
            'value': 999
        })
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '1')
        
        self.assertEqual(req._status, 200)
        data = json.loads(req._data.decode('utf-8'))
        
        self.assertEqual(data['id'], 1)
        self.assertIn('changes', data)
        self.assertEqual(len(data['changes']), 2)
    
    def test_delete_resource(self):
        """Test deleting a resource."""
        req = self._make_request('DELETE')
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '1')
        
        self.assertEqual(req._status, 200)
        data = json.loads(req._data.decode('utf-8'))
        self.assertIn('message', data)
    
    def test_invalid_method(self):
        """Test invalid HTTP method."""
        req = self._make_request('PATCH')
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '1')
        
        self.assertEqual(req._status, 405)
    
    def test_invalid_json(self):
        """Test invalid JSON in request body."""
        req = self._make_request('POST')
        req.data = b'invalid json{'
        
        # Mock read method with invalid JSON
        def mock_read():
            return req.data
        req.read = mock_read
        
        with self.assertRaises(RequestDone):
            self.handler.handle_request(req, '')
        
        self.assertEqual(req._status, 400)
        data = json.loads(req._data.decode('utf-8'))
        self.assertIn('Invalid JSON', data['error']['message'])
    
    def test_datetime_serialization(self):
        """Test datetime serialization."""
        dt = datetime(2025, 1, 23, 12, 30, 45, tzinfo=utc)
        timestamp = self.handler._serialize_datetime(dt)
        self.assertIsInstance(timestamp, int)
        
        # Test deserialization
        dt2 = self.handler._deserialize_datetime(timestamp)
        self.assertEqual(dt.replace(microsecond=0), dt2.replace(microsecond=0))
        
        # Test None handling
        self.assertIsNone(self.handler._serialize_datetime(None))
        self.assertIsNone(self.handler._deserialize_datetime(None))


class MockPermissions:
    """Mock permission system that grants all permissions."""
    
    def __init__(self):
        self.resource = None
    
    def __call__(self, resource):
        self.resource = resource
        return self
    
    def require(self, perm):
        pass  # Grant all permissions
    
    def __contains__(self, perm):
        return True  # Has all permissions


def test_suite():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTest(loader.loadTestsFromTestCase(BaseRESTHandlerTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')