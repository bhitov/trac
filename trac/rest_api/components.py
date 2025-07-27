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

"""REST API for Components - provides CRUD operations on components via JSON API."""

from trac.core import TracError
from trac.rest_api.base import BaseRESTHandler
from trac.ticket.model import Component
from trac.resource import ResourceExistsError, ResourceNotFound
from trac.web.api import RequestDone
from trac.perm import PermissionError


class ComponentsAPI(BaseRESTHandler):
    """Handles REST API requests for components."""
    
    @property
    def model_class(self):
        return Component
    
    @property
    def resource_name(self):
        return 'TICKET'  # Components use TICKET permissions
    
    @property
    def collection_name(self):
        return 'components'
    
    def _get_resources_list(self, req, limit, offset):
        """Get a list of components based on filters."""
        # Parse query parameters
        owner = req.args.get('owner')
        
        # Get all components
        components = list(Component.select(self.env))
        
        # Filter by owner if requested
        if owner is not None:
            components = [c for c in components if c.owner == owner]
        
        # Sort by name
        components.sort(key=lambda c: c.name)
        
        # Apply offset and limit
        total = len(components)
        components = components[offset:offset + limit]
        
        return components
    
    def _get_resources_count(self, req):
        """Get total count of components."""
        # Parse query parameters
        owner = req.args.get('owner')
        
        # Get all components
        components = list(Component.select(self.env))
        
        # Filter by owner if requested
        if owner is not None:
            components = [c for c in components if c.owner == owner]
        
        return len(components)
    
    def _serialize_resource(self, component, detailed=False):
        """Convert a Component object to a JSON-serializable dict."""
        return {
            'name': component.name,
            'owner': component.owner,
            'description': component.description,
        }
    
    def _set_resource_fields(self, component, data, req):
        """Set fields on a new component from request data."""
        # Set required fields
        if 'name' not in data or not data['name'].strip():
            raise TracError("Name is required")
            
        component.name = data['name']
        
        # Set optional fields
        if 'owner' in data:
            component.owner = data['owner']
        
        if 'description' in data:
            component.description = data['description']
    
    def _update_resource_fields(self, component, data, req):
        """Update fields on an existing component and return changes."""
        changes = []
        
        # Update fields if provided
        if 'owner' in data and component.owner != data['owner']:
            old_value = component.owner
            component.owner = data['owner']
            changes.append(('owner', old_value, component.owner))
        
        if 'description' in data and component.description != data['description']:
            old_value = component.description
            component.description = data['description']
            changes.append(('description', old_value, component.description))
        
        return changes
    
    def _save_new_resource(self, component, req):
        """Save a newly created component."""
        try:
            component.insert()
        except ResourceExistsError:
            raise TracError(f"Component '{component.name}' already exists")
    
    def _save_resource_changes(self, component, changes, req, data):
        """Save changes to an existing component."""
        component.update()
    
    def list_resources(self, req):
        """Override to check permissions before listing components."""
        # Check if user has permission to view tickets
        try:
            req.perm.require('TICKET_VIEW')
            return super().list_resources(req)
        except PermissionError:
            self._send_error(req, 403, "TICKET_VIEW privileges are required to perform this operation")
    
    def handle_request(self, req, resource_id):
        """Handle REST API requests for components."""
        # Override parent to handle special delete case
        if req.method == 'DELETE' and resource_id:
            # Handle delete
            try:
                component = self._load_resource(resource_id)
                self._check_permission(req, component, 'DELETE')
            except ResourceNotFound:
                self._send_error(req, 404, "Component not found")
                return
            
            # Delete the component
            try:
                component.delete()
            except TracError as e:
                self._send_error(req, 400, str(e))
                return
            
            # Return 204 No Content for successful delete
            req.send_response(204)
            req.send_header('Cache-Control', 'no-cache')
            req.end_headers()
            raise RequestDone
        else:
            # Use parent implementation for other methods
            return super().handle_request(req, resource_id)
    
    def _check_permission(self, req, resource, action):
        """Check if user has permission for an action on a component."""
        # For components, we use TICKET permissions
        if action == 'VIEW':
            req.perm.require('TICKET_VIEW')
        elif action in ('CREATE', 'MODIFY', 'DELETE'):
            req.perm.require('TICKET_ADMIN')
    
    def _load_resource(self, resource_id):
        """Load a component by name."""
        component = Component(self.env, resource_id)
        if not component.exists:
            raise ResourceNotFound("Component '%s' does not exist" % resource_id)
        return component