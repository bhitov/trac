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

"""REST API for Versions - provides CRUD operations on versions via JSON API."""

from datetime import datetime

from trac.core import TracError
from trac.rest_api.base import BaseRESTHandler
from trac.ticket.model import Version
from trac.util.datefmt import to_utimestamp, from_utimestamp, parse_date, utc
from trac.resource import ResourceExistsError, ResourceNotFound
from trac.web.api import RequestDone
from trac.perm import PermissionError


class VersionsAPI(BaseRESTHandler):
    """Handles REST API requests for versions."""
    
    @property
    def model_class(self):
        return Version
    
    @property
    def resource_name(self):
        return 'TICKET'  # Versions use TICKET permissions
    
    @property
    def collection_name(self):
        return 'versions'
    
    def _get_resources_list(self, req, limit, offset):
        """Get a list of versions based on filters."""
        # Parse query parameters
        released = req.args.get('released')
        
        # Get all versions
        versions = list(Version.select(self.env))
        
        # Filter by released status if requested
        if released is not None:
            is_released = released.lower() == 'true'
            versions = [v for v in versions if (v.time is not None) == is_released]
        
        # Sort by time (None values last), then by name
        versions.sort(key=lambda v: (v.time is None, v.time, v.name))
        
        # Apply offset and limit
        total = len(versions)
        versions = versions[offset:offset + limit]
        
        return versions
    
    def _get_resources_count(self, req):
        """Get total count of versions."""
        # Parse query parameters
        released = req.args.get('released')
        
        # Get all versions
        versions = list(Version.select(self.env))
        
        # Filter by released status if requested
        if released is not None:
            is_released = released.lower() == 'true'
            versions = [v for v in versions if (v.time is not None) == is_released]
        
        return len(versions)
    
    def _serialize_resource(self, version, detailed=False):
        """Convert a Version object to a JSON-serializable dict."""
        return {
            'name': version.name,
            'time': version.time.isoformat() if version.time else None,
            'description': version.description,
        }
    
    def _set_resource_fields(self, version, data, req):
        """Set fields on a new version from request data."""
        # Set required fields
        if 'name' not in data or not data['name'].strip():
            raise TracError("Name is required")
            
        version.name = data['name']
        
        # Set optional fields
        if 'description' in data:
            version.description = data['description']
        
        if 'time' in data and data['time']:
            try:
                version.time = parse_date(data['time'], tzinfo=utc)
            except Exception as e:
                raise TracError(f"Invalid time format: {e}")
    
    def _update_resource_fields(self, version, data, req):
        """Update fields on an existing version and return changes."""
        changes = []
        
        # Update fields if provided
        if 'description' in data and version.description != data['description']:
            old_value = version.description
            version.description = data['description']
            changes.append(('description', old_value, version.description))
        
        if 'time' in data:
            old_value = version.time
            if data['time']:
                try:
                    version.time = parse_date(data['time'], tzinfo=utc)
                except Exception as e:
                    raise TracError(f"Invalid time format: {e}")
            else:
                version.time = None
            if old_value != version.time:
                # Serialize dates to ISO format for JSON response
                old_serialized = old_value.isoformat() if old_value else None
                new_serialized = version.time.isoformat() if version.time else None
                changes.append(('time', old_serialized, new_serialized))
        
        return changes
    
    def _save_new_resource(self, version, req):
        """Save a newly created version."""
        try:
            version.insert()
        except ResourceExistsError:
            raise TracError(f"Version '{version.name}' already exists")
    
    def _save_resource_changes(self, version, changes, req, data):
        """Save changes to an existing version."""
        version.update()
    
    def list_resources(self, req):
        """Override to check permissions before listing versions."""
        # Check if user has permission to view tickets
        try:
            req.perm.require('TICKET_VIEW')
            return super().list_resources(req)
        except PermissionError:
            self._send_error(req, 403, "TICKET_VIEW privileges are required to perform this operation")
    
    def handle_request(self, req, resource_id):
        """Handle REST API requests for versions."""
        # Override parent to handle special delete case
        if req.method == 'DELETE' and resource_id:
            # Handle delete
            try:
                version = self._load_resource(resource_id)
                self._check_permission(req, version, 'DELETE')
            except ResourceNotFound:
                self._send_error(req, 404, "Version not found")
                return
            
            # Delete the version
            try:
                version.delete()
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
        """Check if user has permission for an action on a version."""
        # For versions, we use TICKET permissions
        if action == 'VIEW':
            req.perm.require('TICKET_VIEW')
        elif action in ('CREATE', 'MODIFY', 'DELETE'):
            req.perm.require('TICKET_ADMIN')
    
    def _load_resource(self, resource_id):
        """Load a version by name."""
        version = Version(self.env, resource_id)
        if not version.exists:
            raise ResourceNotFound("Version '%s' does not exist" % resource_id)
        return version