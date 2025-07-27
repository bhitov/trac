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

"""REST API for Timeline - provides timeline events via JSON API."""

import json
from datetime import datetime, timedelta

from trac.core import TracError, Component, ExtensionPoint, implements
from trac.web.api import IRequestHandler, RequestDone
from trac.timeline.api import ITimelineEventProvider
from trac.perm import PermissionError
from trac.util.datefmt import to_datetime, to_utimestamp, utc, parse_date, format_datetime


class TimelineAPI(Component):
    """Handles REST API requests for timeline."""
    
    implements(IRequestHandler)
    
    timeline_providers = ExtensionPoint(ITimelineEventProvider)
    
    def match_request(self, req):
        """Never match - we're called directly from handlers."""
        return False
    
    def process_request(self, req):
        """Should not be called."""
        raise NotImplementedError
    
    def handle_request(self, req, resource_id):
        """Handle REST API requests for timeline."""
        if req.method == 'GET':
            return self._handle_get_timeline(req)
        else:
            self._send_error(req, 405, "Method not allowed")
    
    def _handle_get_timeline(self, req):
        """Handle GET /api/timeline - get timeline events."""
        # Check permission
        try:
            req.perm.require('TIMELINE_VIEW')
        except PermissionError:
            self._send_error(req, 403, "TIMELINE_VIEW privileges are required to perform this operation")
            return
        
        # Parse date parameters
        try:
            from_date, to_date = self._parse_date_range(req)
        except TracError as e:
            self._send_error(req, 400, str(e))
            return
        
        # Get pagination
        try:
            limit = int(req.args.get('limit', '100'))
            offset = int(req.args.get('offset', '0'))
        except ValueError:
            self._send_error(req, 400, "Invalid limit or offset")
            return
        
        # Get event filters
        filters = self._get_filters(req)
        
        # Collect events
        events = self._get_timeline_events(req, from_date, to_date, filters)
        
        # Sort by date (newest first)
        events.sort(key=lambda e: e['timestamp'], reverse=True)
        
        # Apply pagination
        total = len(events)
        paginated_events = events[offset:offset + limit]
        
        # Convert datetime objects to ISO format
        for event in paginated_events:
            event['date'] = event['timestamp'].isoformat()
            del event['timestamp']
        
        # Prepare response
        response = {
            'events': paginated_events,
            'total': total,
            'offset': offset,
            'limit': limit
        }
        
        # Send response
        self._send_json_response(req, 200, response)
    
    def _parse_date_range(self, req):
        """Parse date range from request parameters."""
        # Check for daysback parameter
        daysback = req.args.get('daysback')
        if daysback:
            try:
                days = int(daysback)
                to_date = datetime.now(utc)
                from_date = to_date - timedelta(days=days)
                return from_date, to_date
            except ValueError:
                raise TracError("Invalid daysback value")
        
        # Parse from/to dates
        from_str = req.args.get('from')
        to_str = req.args.get('to')
        
        # Default to last 30 days if no dates specified
        if not from_str and not to_str:
            to_date = datetime.now(utc)
            from_date = to_date - timedelta(days=30)
            return from_date, to_date
        
        # Parse dates
        try:
            if from_str:
                from_date = parse_date(from_str, tzinfo=utc)
            else:
                from_date = datetime.now(utc) - timedelta(days=30)
                
            if to_str:
                to_date = parse_date(to_str, tzinfo=utc)
                # Include the entire day
                to_date = to_date.replace(hour=23, minute=59, second=59)
            else:
                to_date = datetime.now(utc)
        except Exception as e:
            raise TracError(f"Invalid date format: {e}")
        
        return from_date, to_date
    
    def _get_filters(self, req):
        """Get event type filters from request."""
        filters = []
        
        # Collect available filters from providers
        available_filters = {}
        for provider in self.timeline_providers:
            for filter_info in provider.get_timeline_filters(req) or []:
                if len(filter_info) >= 2:
                    name, label = filter_info[:2]
                    available_filters[name] = True
        
        # Check which filters are requested
        for name in available_filters:
            if req.args.get(name):
                filters.append(name)
        
        # If no filters specified, use all
        if not filters:
            filters = list(available_filters.keys())
        
        return filters
    
    def _get_timeline_events(self, req, from_date, to_date, filters):
        """Collect timeline events from all providers."""
        events = []
        
        # Timeline providers expect datetime objects, not timestamps
        # from_date and to_date are already datetime objects
        
        # Collect events from each provider
        for provider in self.timeline_providers:
            try:
                # Get events from this provider
                for event in provider.get_timeline_events(req, from_date, to_date, filters) or []:
                    # Event is a tuple: (kind, date, author, data)
                    if len(event) >= 4:
                        kind, date, author, data = event[:4]
                        
                        # Render the event
                        if hasattr(provider, 'render_timeline_event'):
                            from trac.web.chrome import web_context
                            context = web_context(req)
                            
                            try:
                                field, url, title, markup = provider.render_timeline_event(
                                    context, 'url', event)
                            except Exception as e:
                                # Fallback if rendering fails
                                url = ''
                                title = f"{kind} event"
                                markup = ''
                            
                            # Create event dict
                            # date is a datetime object from the event tuple
                            event_dict = {
                                'id': f"{kind}_{to_utimestamp(date)}_{hash(str(data))}",
                                'type': kind,
                                'timestamp': date,  # Keep as datetime for sorting
                                'author': author or 'anonymous',
                                'title': str(title) if title else '',
                                'description': str(markup) if markup else '',
                                'href': req.href(url) if url else ''
                            }
                            
                            # Add extra data if available
                            if isinstance(data, dict):
                                for key, value in data.items():
                                    if key not in event_dict:
                                        event_dict[key] = value
                            
                            events.append(event_dict)
            except Exception as e:
                # Log error but continue with other providers
                self.log.error(f"Error getting timeline events from {provider}: {e}")
        
        return events
    
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
        
        req.send_response(status)
        req.send_header('Content-Type', 'application/json')
        req.send_header('Cache-Control', 'no-cache')
        req.end_headers()
        req.write(json.dumps(error_data).encode('utf-8'))
        raise RequestDone