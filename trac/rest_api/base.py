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

"""Base REST API handler providing common functionality for all REST endpoints."""

import json
from abc import ABCMeta, abstractmethod

from trac.core import TracError
from trac.resource import ResourceNotFound
from trac.util.datefmt import to_utimestamp, from_utimestamp
from trac.web.api import RequestDone


class BaseRESTHandler(object, metaclass=ABCMeta):
    """Base class for REST API handlers providing common CRUD operations."""
    
    def __init__(self, env):
        self.env = env
    
    @property
    @abstractmethod
    def model_class(self):
        """Return the model class this handler manages (e.g., Ticket, Component)."""
        pass
    
    @property
    @abstractmethod
    def resource_name(self):
        """Return the resource name for permissions (e.g., 'TICKET', 'WIKI')."""
        pass
    
    @property
    @abstractmethod
    def collection_name(self):
        """Return the collection name for URLs (e.g., 'tickets', 'wiki')."""
        pass
    
    def handle_request(self, req, resource_id):
        """Route REST requests to appropriate methods."""
        method = req.method
        
        # Handle collection operations
        if not resource_id:
            if method == 'GET':
                return self.list_resources(req)
            elif method == 'POST':
                return self.create_resource(req)
            else:
                self._send_error(req, 405, "Method not allowed")
        
        # Handle single resource operations
        if method == 'GET':
            return self.get_resource(req, resource_id)
        elif method == 'PUT':
            return self.update_resource(req, resource_id)
        elif method == 'DELETE':
            return self.delete_resource(req, resource_id)
        else:
            self._send_error(req, 405, "Method not allowed")
    
    def list_resources(self, req):
        """GET /api/{collection} - List resources with optional filtering."""
        req.perm.require(f'{self.resource_name}_VIEW')
        
        # Get pagination parameters
        limit = int(req.args.get('limit', 100))
        offset = int(req.args.get('offset', 0))
        
        # Get resources
        resources = self._get_resources_list(req, limit, offset)
        total_count = self._get_resources_count(req)
        
        # Serialize resources
        serialized = []
        for resource in resources:
            if self._has_permission(req, resource, 'VIEW'):
                serialized.append(self._serialize_resource(resource))
        
        # Send response
        response_data = {
            self.collection_name: serialized,
            'count': total_count,
            'offset': offset,
            'limit': limit
        }
        
        self._send_json_response(req, 200, response_data)
    
    def get_resource(self, req, resource_id):
        """GET /api/{collection}/{id} - Get a specific resource."""
        try:
            resource = self._load_resource(resource_id)
            self._check_permission(req, resource, 'VIEW')
        except ResourceNotFound:
            self._send_error(req, 404, f"{self.model_class.__name__} not found")
            return
        
        serialized = self._serialize_resource(resource, detailed=True)
        self._send_json_response(req, 200, serialized)
    
    def create_resource(self, req):
        """POST /api/{collection} - Create a new resource."""
        req.perm.require(f'{self.resource_name}_CREATE')
        
        # Parse JSON body
        try:
            data = json.loads(req.read())
        except (ValueError, TypeError):
            self._send_error(req, 400, "Invalid JSON in request body")
            return
        
        # Create resource
        resource = self.model_class(self.env)
        
        # Set fields from data
        self._set_resource_fields(resource, data, req)
        
        # Save resource
        try:
            self._save_new_resource(resource, req)
        except TracError as e:
            self._send_error(req, 400, str(e))
            return
        
        # Return created resource
        serialized = self._serialize_resource(resource, detailed=True)
        self._send_json_response(req, 201, serialized)
    
    def update_resource(self, req, resource_id):
        """PUT /api/{collection}/{id} - Update an existing resource."""
        try:
            resource = self._load_resource(resource_id)
            self._check_permission(req, resource, 'MODIFY')
        except ResourceNotFound:
            self._send_error(req, 404, f"{self.model_class.__name__} not found")
            return
        
        # Parse JSON body
        try:
            data = json.loads(req.read())
        except (ValueError, TypeError):
            self._send_error(req, 400, "Invalid JSON in request body")
            return
        
        # Track changes
        changes = self._update_resource_fields(resource, data, req)
        
        # Save changes
        try:
            self._save_resource_changes(resource, changes, req, data)
        except TracError as e:
            self._send_error(req, 400, str(e))
            return
        
        # Return updated resource
        serialized = self._serialize_resource(resource, detailed=True)
        serialized['changes'] = [{'field': field, 'old': old, 'new': new} 
                                 for field, old, new in changes]
        
        self._send_json_response(req, 200, serialized)
    
    def delete_resource(self, req, resource_id):
        """DELETE /api/{collection}/{id} - Delete a resource."""
        try:
            resource = self._load_resource(resource_id)
            self._check_permission(req, resource, 'ADMIN')
        except ResourceNotFound:
            self._send_error(req, 404, f"{self.model_class.__name__} not found")
            return
        
        try:
            resource.delete()
        except TracError as e:
            self._send_error(req, 400, str(e))
            return
        
        # Return success
        response_data = {'message': f'{self.model_class.__name__} deleted successfully'}
        self._send_json_response(req, 200, response_data)
    
    # Abstract methods that subclasses must implement
    @abstractmethod
    def _get_resources_list(self, req, limit, offset):
        """Get a list of resources for the collection."""
        pass
    
    @abstractmethod
    def _get_resources_count(self, req):
        """Get the total count of resources."""
        pass
    
    @abstractmethod
    def _serialize_resource(self, resource, detailed=False):
        """Serialize a resource to a dictionary."""
        pass
    
    @abstractmethod
    def _set_resource_fields(self, resource, data, req):
        """Set fields on a new resource from request data."""
        pass
    
    @abstractmethod
    def _update_resource_fields(self, resource, data, req):
        """Update fields on an existing resource and return changes."""
        pass
    
    @abstractmethod
    def _save_new_resource(self, resource, req):
        """Save a newly created resource."""
        pass
    
    @abstractmethod
    def _save_resource_changes(self, resource, changes, req, data):
        """Save changes to an existing resource."""
        pass
    
    # Helper methods
    def _load_resource(self, resource_id):
        """Load a resource by ID."""
        return self.model_class(self.env, resource_id)
    
    def _check_permission(self, req, resource, action):
        """Check if user has permission for an action on a resource."""
        perm_name = f'{self.resource_name}_{action}'
        req.perm(resource.resource).require(perm_name)
    
    def _has_permission(self, req, resource, action):
        """Check if user has permission without raising exception."""
        perm_name = f'{self.resource_name}_{action}'
        return perm_name in req.perm(resource.resource)
    
    def _send_json_response(self, req, status, data):
        """Send a JSON response."""
        req.send_response(status)
        req.send_header('Content-Type', 'application/json')
        req.send_header('Cache-Control', 'no-cache')
        req.end_headers()
        req.write(json.dumps(data).encode('utf-8'))
        raise RequestDone
    
    def _send_error(self, req, status, message):
        """Send a JSON error response."""
        error_data = {
            'error': {
                'code': status,
                'message': message
            }
        }
        self._send_json_response(req, status, error_data)
    
    def _serialize_datetime(self, dt):
        """Convert datetime to timestamp for JSON serialization."""
        return to_utimestamp(dt) if dt else None
    
    def _deserialize_datetime(self, timestamp):
        """Convert timestamp to datetime."""
        return from_utimestamp(timestamp) if timestamp else None