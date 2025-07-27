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

"""REST API for Wiki - provides CRUD operations on wiki pages via JSON API."""

import json
from datetime import datetime

from trac.core import TracError
from trac.resource import ResourceNotFound
from trac.rest_api.base import BaseRESTHandler
from trac.util.datefmt import datetime_now, utc
from trac.wiki.model import WikiPage


class WikiAPI(BaseRESTHandler):
    """Handles REST API requests for wiki pages."""
    
    @property
    def model_class(self):
        return WikiPage
    
    @property
    def resource_name(self):
        return 'WIKI'
    
    @property
    def collection_name(self):
        return 'pages'
    
    def _get_resources_list(self, req, limit, offset):
        """Get a list of wiki pages."""
        # Get all wiki page names
        pages = []
        with self.env.db_query as db:
            query = """
                SELECT DISTINCT name FROM wiki 
                ORDER BY name
                LIMIT %s OFFSET %s
            """
            for row in db(query, (limit, offset)):
                page_name = row[0]
                try:
                    page = WikiPage(self.env, page_name)
                    if page.exists:
                        pages.append(page)
                except:
                    pass  # Skip pages that can't be loaded
        
        return pages
    
    def _get_resources_count(self, req):
        """Get total count of wiki pages."""
        with self.env.db_query as db:
            count = db("SELECT COUNT(DISTINCT name) FROM wiki")[0][0]
        return count
    
    def _serialize_resource(self, page, detailed=False):
        """Serialize a wiki page to a dictionary."""
        data = {
            'name': page.name,
            'version': page.version,
            'author': page.author,
            'time': self._serialize_datetime(page.time),
            'readonly': page.readonly
        }
        
        if detailed:
            # Add full content for detailed view
            data['text'] = page.text
            data['comment'] = page.comment
            
            # Add version history count
            history_count = 0
            for version, time, author, comment in page.get_history():
                history_count += 1
            data['history_count'] = history_count
        
        return data
    
    def _set_resource_fields(self, page, data, req):
        """Set fields on a new wiki page from request data."""
        page.text = data.get('text', '')
        page.comment = data.get('comment', 'Page created via REST API')
        page.author = req.authname
        page.time = datetime_now(utc)
    
    def _update_resource_fields(self, page, data, req):
        """Update fields on an existing wiki page and return changes."""
        changes = []
        
        # Track text changes
        if 'text' in data:
            old_text = page.text
            if old_text != data['text']:
                page.text = data['text']
                changes.append(('text', old_text, data['text']))
        
        # Set metadata
        page.comment = data.get('comment', 'Updated via REST API')
        page.author = req.authname
        page.time = datetime_now(utc)
        
        return changes
    
    def _save_new_resource(self, page, req):
        """Save a newly created wiki page."""
        page.save(req.authname, page.comment)
    
    def _save_resource_changes(self, page, changes, req, data):
        """Save changes to an existing wiki page."""
        comment = data.get('comment', 'Updated via REST API')
        page.save(req.authname, comment)
    
    def _load_resource(self, resource_id):
        """Load a wiki page by name."""
        # Wiki page names can contain slashes, so resource_id is the full name
        page = WikiPage(self.env, resource_id)
        return page
    
    def get_resource(self, req, resource_id):
        """Override to handle non-existent pages."""
        from trac.perm import PermissionError
        
        try:
            resource = self._load_resource(resource_id)
        except TracError:
            self._send_error(req, 404, f"{self.resource_name} not found")
            return
        
        # Check if page exists
        if not resource.exists:
            self._send_error(req, 404, "Wiki page not found")
            return
        
        try:
            self._check_permission(req, resource, 'VIEW')
        except PermissionError as e:
            self._send_error(req, 403, str(e))
            return
        
        serialized = self._serialize_resource(resource, detailed=True)
        self._send_json_response(req, 200, serialized)
    
    def create_resource(self, req):
        """For wiki, creation happens through PUT on a new page name."""
        self._send_error(req, 405, "Use PUT /api/wiki/{page_name} to create a new page")
    
    def handle_request(self, req, resource_id):
        """Override to handle special wiki endpoints."""
        # Handle POST to create a specific page
        if req.method == 'POST' and resource_id:
            # Creating a new page with a specific name
            return self._create_page(req, resource_id)
        # Handle version history endpoint
        elif resource_id and resource_id.endswith('/history'):
            page_name = resource_id[:-8]  # Remove '/history'
            return self._get_page_history(req, page_name)
        elif resource_id and '/versions/' in resource_id:
            # Handle specific version endpoint
            parts = resource_id.split('/versions/')
            page_name = parts[0]
            version = parts[1]
            return self._get_page_version(req, page_name, version)
        else:
            # Default handling
            return super(WikiAPI, self).handle_request(req, resource_id)
    
    def _get_page_history(self, req, page_name):
        """GET /api/wiki/{page}/history - Get page history."""
        try:
            page = WikiPage(self.env, page_name)
            req.perm(page.resource).require('WIKI_VIEW')
        except ResourceNotFound:
            self._send_error(req, 404, "Wiki page not found")
            return
        
        history = []
        for version, time, author, comment in page.get_history():
            history.append({
                'version': version,
                'time': self._serialize_datetime(time),
                'author': author,
                'comment': comment
            })
        
        response_data = {
            'page': page_name,
            'history': history
        }
        
        self._send_json_response(req, 200, response_data)
    
    def _create_page(self, req, page_name):
        """Create a new wiki page with POST."""
        req.perm.require('WIKI_CREATE')
        
        # Parse JSON body
        try:
            data = json.loads(req.read().decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_error(req, 400, f"Invalid JSON: {e}")
            return
            
        # Create new page
        page = WikiPage(self.env, page_name)
        if page.exists:
            self._send_error(req, 409, f"Page '{page_name}' already exists")
            return
            
        # Set fields
        self._set_resource_fields(page, data, req)
        
        # Save the page
        try:
            self._save_new_resource(page, req)
        except TracError as e:
            self._send_error(req, 400, str(e))
            return
            
        # Return created page
        self._send_json_response(req, 201, self._serialize_resource(page, detailed=True))
    
    def _get_page_version(self, req, page_name, version):
        """GET /api/wiki/{page}/versions/{version} - Get specific version."""
        try:
            version_num = int(version)
            page = WikiPage(self.env, page_name, version_num)
            req.perm(page.resource).require('WIKI_VIEW')
        except (ValueError, ResourceNotFound):
            self._send_error(req, 404, "Wiki page version not found")
            return
        
        response_data = self._serialize_resource(page, detailed=True)
        self._send_json_response(req, 200, response_data)