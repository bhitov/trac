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

"""REST API for Milestones - provides CRUD operations on milestones via JSON API."""

from datetime import datetime

from trac.core import TracError
from trac.rest_api.base import BaseRESTHandler
from trac.ticket.model import Milestone
from trac.util.datefmt import to_utimestamp, from_utimestamp, parse_date, utc
from trac.resource import ResourceExistsError, ResourceNotFound
from trac.web.api import RequestDone


class MilestonesAPI(BaseRESTHandler):
    """Handles REST API requests for milestones."""
    
    @property
    def model_class(self):
        return Milestone
    
    @property
    def resource_name(self):
        return 'TICKET'  # Milestones use TICKET permissions
    
    @property
    def collection_name(self):
        return 'milestones'
    
    def _get_resources_list(self, req, limit, offset):
        """Get a list of milestones based on filters."""
        # Parse query parameters
        completed = req.args.get('completed')
        
        # Get all milestones
        milestones = list(Milestone.select(self.env))
        
        # Filter by completed status if requested
        if completed is not None:
            is_completed = completed.lower() == 'true'
            milestones = [m for m in milestones if (m.is_completed == is_completed)]
        
        # Sort by due date (None values last)
        milestones.sort(key=lambda m: (m.due is None, m.due))
        
        # Apply offset and limit
        total = len(milestones)
        milestones = milestones[offset:offset + limit]
        
        return milestones
    
    def _get_resources_count(self, req):
        """Get total count of milestones."""
        # Parse query parameters
        completed = req.args.get('completed')
        
        # Get all milestones
        milestones = list(Milestone.select(self.env))
        
        # Filter by completed status if requested
        if completed is not None:
            is_completed = completed.lower() == 'true'
            milestones = [m for m in milestones if (m.is_completed == is_completed)]
        
        return len(milestones)
    
    def _serialize_resource(self, milestone, detailed=False):
        """Convert a Milestone object to a JSON-serializable dict."""
        return {
            'name': milestone.name,
            'description': milestone.description,
            'due': milestone.due.isoformat() if milestone.due else None,
            'completed': milestone.completed.isoformat() if milestone.completed else None,
            'is_completed': milestone.is_completed,
            'is_late': milestone.is_late,
        }
    
    def _set_resource_fields(self, milestone, data, req):
        """Set fields on a new milestone from request data."""
        # Set required fields
        if 'name' not in data or not data['name'].strip():
            raise TracError("Name is required")
            
        milestone.name = data['name']
        
        # Set optional fields
        if 'description' in data:
            milestone.description = data['description']
        
        if 'due' in data and data['due']:
            try:
                milestone.due = parse_date(data['due'], tzinfo=utc)
            except Exception as e:
                raise TracError(f"Invalid due date format: {e}")
        
        if 'completed' in data and data['completed']:
            try:
                milestone.completed = parse_date(data['completed'], tzinfo=utc)
            except Exception as e:
                raise TracError(f"Invalid completed date format: {e}")
    
    def _update_resource_fields(self, milestone, data, req):
        """Update fields on an existing milestone and return changes."""
        changes = []
        
        # Update fields if provided
        if 'description' in data and milestone.description != data['description']:
            old_value = milestone.description
            milestone.description = data['description']
            changes.append(('description', old_value, milestone.description))
        
        if 'due' in data:
            old_value = milestone.due
            if data['due']:
                try:
                    milestone.due = parse_date(data['due'], tzinfo=utc)
                except Exception as e:
                    raise TracError(f"Invalid due date format: {e}")
            else:
                milestone.due = None
            if old_value != milestone.due:
                # Serialize dates to ISO format for JSON response
                old_serialized = old_value.isoformat() if old_value else None
                new_serialized = milestone.due.isoformat() if milestone.due else None
                changes.append(('due', old_serialized, new_serialized))
        
        if 'completed' in data:
            old_value = milestone.completed
            if data['completed']:
                try:
                    milestone.completed = parse_date(data['completed'], tzinfo=utc)
                except Exception as e:
                    raise TracError(f"Invalid completed date format: {e}")
            else:
                milestone.completed = None
            if old_value != milestone.completed:
                # Serialize dates to ISO format for JSON response
                old_serialized = old_value.isoformat() if old_value else None
                new_serialized = milestone.completed.isoformat() if milestone.completed else None
                changes.append(('completed', old_serialized, new_serialized))
        
        return changes
    
    def _save_new_resource(self, milestone, req):
        """Save a newly created milestone."""
        try:
            milestone.insert()
        except ResourceExistsError:
            raise TracError(f"Milestone '{milestone.name}' already exists")
    
    def _save_resource_changes(self, milestone, changes, req, data):
        """Save changes to an existing milestone."""
        milestone.update()
    
    def list_resources(self, req):
        """Override to check permissions before listing milestones."""
        # Check if user has permission to view tickets
        from trac.perm import PermissionError
        try:
            req.perm.require('TICKET_VIEW')
            return super().list_resources(req)
        except PermissionError:
            self._send_error(req, 403, "TICKET_VIEW privileges are required to perform this operation")
    
    def handle_request(self, req, resource_id):
        """Handle REST API requests for milestones."""
        # Override parent to handle special delete case with retarget
        if req.method == 'DELETE' and resource_id:
            # Handle delete with optional retarget
            try:
                milestone = self._load_resource(resource_id)
                self._check_permission(req, milestone, 'DELETE')
            except ResourceNotFound:
                self._send_error(req, 404, "Milestone not found")
                return
            
            retarget_to = req.args.get('retarget')
            if retarget_to:
                # Verify target milestone exists
                try:
                    target = Milestone(self.env, retarget_to)
                    if not target.exists:
                        self._send_error(req, 400, f"Target milestone '{retarget_to}' does not exist")
                        return
                except:
                    self._send_error(req, 400, f"Target milestone '{retarget_to}' does not exist")
                    return
                
                # Move tickets to target milestone
                milestone.move_tickets(retarget_to, req.authname, "Milestone deleted")
            
            # Delete the milestone
            try:
                milestone.delete()
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
        """Check if user has permission for an action on a milestone."""
        # For milestones, we use TICKET permissions
        if action == 'VIEW':
            req.perm.require('TICKET_VIEW')
        elif action == 'CREATE':
            req.perm.require('TICKET_ADMIN')
        elif action in ('MODIFY', 'DELETE'):
            req.perm.require('TICKET_ADMIN')
    
    def _load_resource(self, resource_id):
        """Load a milestone by name."""
        milestone = Milestone(self.env, resource_id)
        if not milestone.exists:
            raise ResourceNotFound("Milestone '%s' does not exist" % resource_id)
        return milestone