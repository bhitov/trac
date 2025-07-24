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

"""REST API for Tickets - provides CRUD operations on tickets via JSON API."""

from datetime import datetime

from trac.core import TracError
from trac.rest_api.base import BaseRESTHandler
from trac.ticket.model import Ticket
from trac.ticket.api import TicketSystem
from trac.util.datefmt import to_utimestamp, datetime_now, utc


class TicketsAPI(BaseRESTHandler):
    """Handles REST API requests for tickets."""
    
    @property
    def model_class(self):
        return Ticket
    
    @property
    def resource_name(self):
        return 'TICKET'
    
    @property
    def collection_name(self):
        return 'tickets'
    
    def _get_resources_list(self, req, limit, offset):
        """Get a list of tickets based on filters."""
        # Parse query parameters
        status = req.args.get('status')
        owner = req.args.get('owner')
        milestone = req.args.get('milestone')
        component = req.args.get('component')
        
        # Build SQL query
        query_parts = []
        params = []
        
        if status:
            query_parts.append("status = %s")
            params.append(status)
        if owner:
            query_parts.append("owner = %s")
            params.append(owner)
        if milestone:
            query_parts.append("milestone = %s")
            params.append(milestone)
        if component:
            query_parts.append("component = %s")
            params.append(component)
        
        where_clause = " WHERE " + " AND ".join(query_parts) if query_parts else ""
        
        # Get tickets
        query = """
            SELECT id FROM ticket
            {}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """.format(where_clause)
        
        params.extend([limit, offset])
        
        tickets = []
        with self.env.db_query as db:
            for row in db(query, params):
                try:
                    ticket = Ticket(self.env, row[0])
                    tickets.append(ticket)
                except ResourceNotFound:
                    pass  # Skip tickets that can't be loaded
        
        return tickets
    
    def _get_resources_count(self, req):
        """Get total count of tickets matching filters."""
        # Parse query parameters (same as list)
        status = req.args.get('status')
        owner = req.args.get('owner')
        milestone = req.args.get('milestone')
        component = req.args.get('component')
        
        # Build SQL query
        query_parts = []
        params = []
        
        if status:
            query_parts.append("status = %s")
            params.append(status)
        if owner:
            query_parts.append("owner = %s")
            params.append(owner)
        if milestone:
            query_parts.append("milestone = %s")
            params.append(milestone)
        if component:
            query_parts.append("component = %s")
            params.append(component)
        
        where_clause = " WHERE " + " AND ".join(query_parts) if query_parts else ""
        
        # Get count
        count_query = "SELECT COUNT(*) FROM ticket" + where_clause
        with self.env.db_query as db:
            return db(count_query, params)[0][0]
    
    def _serialize_resource(self, ticket, detailed=False):
        """Serialize a ticket to a dictionary."""
        data = {
            'id': ticket.id,
            'summary': ticket['summary'],
            'status': ticket['status'],
            'priority': ticket['priority'],
            'reporter': ticket['reporter'],
            'owner': ticket['owner'],
            'type': ticket['type'],
            'time_created': self._serialize_datetime(ticket['time']),
            'time_changed': self._serialize_datetime(ticket['changetime'])
        }
        
        if detailed:
            # Add all fields for detailed view
            data['description'] = ticket['description']
            data['component'] = ticket['component']
            data['milestone'] = ticket['milestone']
            data['version'] = ticket['version']
            data['severity'] = ticket['severity']
            data['resolution'] = ticket['resolution']
            data['cc'] = ticket['cc']
            data['keywords'] = ticket['keywords']
            
            # Add custom fields
            custom_fields = {}
            for field in ticket.fields:
                if field.get('custom'):
                    field_name = field['name']
                    value = ticket[field_name]
                    if value is not None:  # Only include non-null custom fields
                        custom_fields[field_name] = value
            
            if custom_fields:
                data['custom_fields'] = custom_fields
        
        return data
    
    def _set_resource_fields(self, ticket, data, req):
        """Set fields on a new ticket from request data."""
        # Set required fields
        ticket['summary'] = data.get('summary', '')
        ticket['description'] = data.get('description', '')
        ticket['reporter'] = req.authname
        ticket['time'] = ticket['changetime'] = datetime_now(utc)
        
        # Set optional fields
        for field in ['type', 'component', 'milestone', 'priority', 
                      'severity', 'version', 'keywords', 'cc', 'owner']:
            if field in data:
                ticket[field] = data[field]
        
        # Set default status
        ticket['status'] = 'new'
        
        # Handle custom fields
        if 'custom_fields' in data:
            for field_name, value in data['custom_fields'].items():
                ticket[field_name] = value
    
    def _update_resource_fields(self, ticket, data, req):
        """Update fields on an existing ticket and return changes."""
        changes = []
        
        # Update standard fields
        for field, value in data.items():
            if field in ['id', 'time', 'changetime', 'custom_fields', 'comment']:
                continue  # Skip read-only and special fields
            
            old_value = ticket[field]
            if old_value != value:
                ticket[field] = value
                changes.append((field, old_value, value))
        
        # Handle custom fields
        if 'custom_fields' in data:
            for field_name, value in data['custom_fields'].items():
                old_value = ticket[field_name]
                if old_value != value:
                    ticket[field_name] = value
                    changes.append((field_name, old_value, value))
        
        return changes
    
    def _save_new_resource(self, ticket, req):
        """Save a newly created ticket."""
        ticket.insert()
    
    def _save_resource_changes(self, ticket, changes, req, data):
        """Save changes to an existing ticket."""
        comment = data.get('comment', '')
        ticket.save_changes(req.authname, comment)
    
    def _load_resource(self, resource_id):
        """Load a ticket by ID, handling integer conversion."""
        try:
            ticket_id = int(resource_id)
        except ValueError:
            raise ResourceNotFound("Invalid ticket ID")
        return Ticket(self.env, ticket_id)