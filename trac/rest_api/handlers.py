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

"""Base REST API request handler for Trac."""

import json
import re
from trac.core import Component, implements
from trac.web.api import IRequestHandler, RequestDone
from trac.web.chrome import INavigationContributor


class RestApiHandler(Component):
    """Main REST API request handler that routes to specific API modules."""
    
    implements(IRequestHandler, INavigationContributor)
    
    # Match paths like /api/tickets, /api/tickets/123, /api/wiki/PageName
    api_path_re = re.compile(r'^/api/([^/]+)(?:/(.*))?$')
    
    # IRequestHandler methods
    def match_request(self, req):
        """Check if this is a REST API request."""
        match = self.api_path_re.match(req.path_info)
        if match:
            req.args['api_resource'] = match.group(1)
            req.args['api_path'] = match.group(2) or ''
            return True
        return False
    
    def process_request(self, req):
        """Process REST API requests and route to appropriate handlers."""
        resource_type = req.args.get('api_resource')
        resource_id = req.args.get('api_path')
        
        # Route to appropriate API handler based on resource type
        if resource_type == 'ticket':
            from trac.rest_api.tickets import TicketsAPI
            handler = TicketsAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'wiki':
            from trac.rest_api.wiki import WikiAPI
            handler = WikiAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'milestone':
            from trac.rest_api.milestones import MilestonesAPI
            handler = MilestonesAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'component':
            from trac.rest_api.components import ComponentsAPI
            handler = ComponentsAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'version':
            from trac.rest_api.versions import VersionsAPI
            handler = VersionsAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'search':
            from trac.rest_api.search import SearchAPI
            handler = SearchAPI(self.env)
            return handler.handle_request(req, resource_id)
        elif resource_type == 'timeline':
            from trac.rest_api.timeline import TimelineAPI
            handler = TimelineAPI(self.env)
            return handler.handle_request(req, resource_id)
        
        # All planned API handlers have been implemented
        
        # If no handler found, return 404
        self._send_json_error(req, 404, "API endpoint not found")
        raise RequestDone
    
    def _send_json_error(self, req, status, message):
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
    
    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return None
    
    def get_navigation_items(self, req):
        # Don't add any navigation items for the API
        return []