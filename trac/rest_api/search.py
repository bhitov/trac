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

"""REST API for Search - provides search functionality via JSON API."""

import json
from datetime import datetime

from trac.core import TracError, Component, ExtensionPoint, implements
from trac.web.api import IRequestHandler, RequestDone
from trac.search.api import ISearchSource
from trac.perm import PermissionError
from trac.util.datefmt import to_utimestamp, from_utimestamp, utc


class SearchAPI(Component):
    """Handles REST API requests for search."""
    
    implements(IRequestHandler)
    
    search_sources = ExtensionPoint(ISearchSource)
    
    def match_request(self, req):
        """Never match - we're called directly from handlers."""
        return False
    
    def process_request(self, req):
        """Should not be called."""
        raise NotImplementedError
    
    def handle_request(self, req, resource_id):
        """Handle REST API requests for search."""
        if req.method == 'GET':
            return self._handle_get_search(req)
        elif req.method == 'POST':
            return self._handle_post_search(req)
        else:
            self._send_error(req, 405, "Method not allowed")
    
    def _handle_get_search(self, req):
        """Handle GET /api/search - search with query parameters."""
        # Check permission
        try:
            req.perm.require('SEARCH_VIEW')
        except PermissionError:
            self._send_error(req, 403, "SEARCH_VIEW privileges are required to perform this operation")
            return
        
        # Get query parameters
        query = req.args.get('q', '').strip()
        if not query:
            self._send_error(req, 400, "Query parameter 'q' is required")
            return
        
        # Get filters - which resources to search
        filters = []
        for source in self.search_sources:
            source_filters = list(source.get_search_filters(req) or [])
            if source_filters:
                name = source_filters[0][0]
                if req.args.get(name):
                    filters.append(name)
        
        # If no filters specified, search all
        if not filters:
            filters = []
            for source in self.search_sources:
                source_filters = list(source.get_search_filters(req) or [])
                if source_filters:
                    filters.append(source_filters[0][0])
        
        # Get pagination
        try:
            limit = int(req.args.get('limit', '100'))
            offset = int(req.args.get('offset', '0'))
        except ValueError:
            self._send_error(req, 400, "Invalid limit or offset")
            return
        
        # Perform search
        results = self._perform_search(req, query, filters, limit, offset)
        
        # Send response
        self._send_json_response(req, 200, results)
    
    def _handle_post_search(self, req):
        """Handle POST /api/search - search with JSON body."""
        # Check permission
        try:
            req.perm.require('SEARCH_VIEW')
        except PermissionError:
            self._send_error(req, 403, "SEARCH_VIEW privileges are required to perform this operation")
            return
        
        # Parse JSON body
        try:
            data = json.loads(req.read().decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_error(req, 400, f"Invalid JSON: {e}")
            return
        
        # Get search parameters
        query = data.get('q', '').strip()
        if not query:
            self._send_error(req, 400, "Query parameter 'q' is required")
            return
        
        filters = data.get('filters', [])
        if not filters:
            # If no filters specified, search all
            filters = []
            for source in self.search_sources:
                source_filters = list(source.get_search_filters(req) or [])
                if source_filters:
                    filters.append(source_filters[0][0])
        
        # Get pagination
        try:
            limit = int(data.get('limit', 100))
            offset = int(data.get('offset', 0))
        except ValueError:
            self._send_error(req, 400, "Invalid limit or offset")
            return
        
        # Perform search
        results = self._perform_search(req, query, filters, limit, offset)
        
        # Send response
        self._send_json_response(req, 200, results)
    
    def _perform_search(self, req, query, filters, limit, offset):
        """Perform the actual search."""
        # Collect all results
        all_results = []
        for source in self.search_sources:
            source_filters = list(source.get_search_filters(req) or [])
            if not source_filters:
                continue
            source_name = source_filters[0][0]
            if source_name not in filters:
                continue
            
            # Get results from this source
            for result in source.get_search_results(req, query, filters):
                # result is a tuple: (href, title, date, author, excerpt)
                href, title, date, author, excerpt = result
                
                # Convert to dict
                result_dict = {
                    'href': req.href(href) if href else '',
                    'title': str(title) if title else '',
                    'date': date.isoformat() if date else None,
                    'author': author or '',
                    'excerpt': str(excerpt) if excerpt else '',
                    'resource': source_name
                }
                all_results.append(result_dict)
        
        # Sort by date (newest first)
        all_results.sort(key=lambda r: r['date'] or '', reverse=True)
        
        # Apply pagination
        total = len(all_results)
        paginated_results = all_results[offset:offset + limit]
        
        return {
            'results': paginated_results,
            'total': total,
            'offset': offset,
            'limit': limit
        }
    
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
        
        status_messages = {
            400: 'Bad Request',
            403: 'Forbidden',
            404: 'Not Found',
            405: 'Method Not Allowed',
            500: 'Internal Server Error'
        }
        
        req.send_response(status)
        req.send_header('Content-Type', 'application/json')
        req.send_header('Cache-Control', 'no-cache')
        req.end_headers()
        req.write(json.dumps(error_data).encode('utf-8'))
        raise RequestDone