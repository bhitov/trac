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

"""Chat handler for AI-powered ticket assistance."""

import json
import re
import traceback
from datetime import datetime

from trac.core import Component, implements
from trac.config import Option
from trac.web.api import IRequestHandler, RequestDone
from trac.web.chrome import ITemplateProvider, INavigationContributor, tag
from trac.perm import IPermissionRequestor
from trac.util.translation import _

from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class ChatHandler(Component):
    """Handles AI chat requests for ticket assistance."""
    
    implements(IRequestHandler, ITemplateProvider, IPermissionRequestor, INavigationContributor)
    
    # Configuration options
    openai_api_key = Option('ai', 'openai_api_key', '',
        doc="OpenAI API key for the chatbot")
    
    openai_model = Option('ai', 'model', 'gpt-3.5-turbo',
        doc="OpenAI model to use (e.g., gpt-3.5-turbo, gpt-4)")
    
    max_context_tickets = Option('ai', 'max_context_tickets', '50',
        doc="Maximum number of recent tickets to include in context")
    
    search_threshold = Option('ai', 'search_threshold', '20',
        doc="Minimum number of tickets before search is allowed")
    
    def __init__(self):
        super().__init__()
        self.context_service = ContextService(self.env)
        self.search_service = FuzzySearchService(self.env)
    
    # IRequestHandler methods
    def match_request(self, req):
        """Match /ai/chat requests."""
        return re.match(r'^/ai(?:/chat)?(?:/(.*))?$', req.path_info)
    
    def process_request(self, req):
        """Process AI chat requests."""
        # Check permissions
        if hasattr(req, 'perm'):
            req.perm.require('TICKET_VIEW')
        
        # Handle different request types
        if req.path_info == '/ai' or req.path_info == '/ai/':
            # Show chat interface
            return self._render_chat_page(req)
        elif req.path_info == '/ai/chat':
            # Handle API requests
            if req.method == 'POST':
                return self._handle_chat_request(req)
            else:
                req.send_error(405, 'Method Not Allowed')
        else:
            req.send_error(404, 'Not Found')
    
    def _render_chat_page(self, req):
        """Render the chat interface page."""
        data = {
            'api_configured': bool(self.openai_api_key),
            'model': self.openai_model,
        }
        
        return 'ai_chat.html', data, {}
    
    def _handle_chat_request(self, req):
        """Handle chat API requests."""
        self.log.info("=== AI Chat Request Started ===")
        
        # Check OpenAI API key
        if not self.openai_api_key:
            self.log.error("OpenAI API key not configured")
            self._send_json_error(req, 500, "OpenAI API key not configured")
            return
        
        self.log.info(f"OpenAI API key configured: {bool(self.openai_api_key)}")
        
        # Check OpenAI library
        if not OpenAI:
            self.log.error("OpenAI library not installed")
            self._send_json_error(req, 500, "OpenAI library not installed. Run: pip install openai")
            return
        
        self.log.info("OpenAI library available")
        
        # Parse request
        try:
            self.log.info("Reading request data...")
            raw_data = req.read()
            self.log.info(f"Raw request data length: {len(raw_data) if raw_data else 0}")
            
            data = json.loads(raw_data)
            self.log.info(f"Parsed JSON data: {data}")
            
            message = data.get('message', '').strip()
            self.log.info(f"Extracted message: '{message}' (length: {len(message)})")
            
        except (json.JSONDecodeError, ValueError) as e:
            self.log.error(f"JSON decode error: {e}")
            self.log.error(f"Raw data was: {raw_data}")
            self._send_json_error(req, 400, "Invalid request format")
            return
        except Exception as e:
            self.log.error(f"Unexpected error parsing request: {e}")
            self.log.error(f"Traceback: {traceback.format_exc()}")
            self._send_json_error(req, 500, f"Error parsing request: {str(e)}")
            return
        
        if not message:
            self.log.error("Empty message received")
            self._send_json_error(req, 400, "Message cannot be empty")
            return
        
        # Generate response
        try:
            self.log.info("Starting AI response generation...")
            response = self._generate_ai_response(req, message)
            self.log.info(f"AI response generated successfully: {len(response)} characters")
            
            self._send_json_response(req, 200, {
                'response': response,
                'timestamp': datetime.now().isoformat()
            })
            self.log.info("Response sent successfully")
            
        except RequestDone:
            # This is expected, re-raise it
            self.log.info("Request completed (RequestDone)")
            raise
        except Exception as e:
            self.log.error(f"Error generating AI response: {e}")
            self.log.error(f"Full traceback: {traceback.format_exc()}")
            self._send_json_error(req, 500, f"Error generating response: {str(e)}")
    
    def _generate_ai_response(self, req, user_message):
        """Generate AI response using OpenAI API.
        
        Args:
            req: Request object
            user_message: User's question
            
        Returns:
            str: AI response
        """
        try:
            self.log.info(f"=== Generating AI Response for: '{user_message}' ===")
            
            # Get recent tickets for context
            context_limit = int(self.max_context_tickets)
            self.log.info(f"Getting context with limit: {context_limit}")
            
            # Check if context service is available
            if not hasattr(self, 'context_service') or self.context_service is None:
                self.log.error("Context service not available")
                raise Exception("Context service not initialized")
            
            self.log.info("Calling context_service.format_tickets_for_context...")
            base_context = self.context_service.format_tickets_for_context(req, include_comments=True, limit=context_limit)
            self.log.info(f"Base context generated: {len(base_context)} characters")
            
            # Check if we should perform a search
            search_context = ""
            
            # Check if search service is available
            if not hasattr(self, 'search_service') or self.search_service is None:
                self.log.error("Search service not available")
                raise Exception("Search service not initialized")
            
            self.log.info("Getting total ticket count...")
            total_tickets = self.search_service.get_total_ticket_count()
            search_threshold = int(self.search_threshold)
            self.log.info(f"Total tickets: {total_tickets}, search threshold: {search_threshold}")
            
            if total_tickets > search_threshold:
                self.log.info("Checking if search is needed...")
                # Analyze if the user's message suggests a search
                if self._should_search(user_message):
                    self.log.info("Search is needed, extracting search terms...")
                    search_query = self._extract_search_terms(user_message)
                    self.log.info(f"Search query: '{search_query}'")
                    if search_query:
                        search_context = self.search_service.format_search_results_for_context(req, search_query)
                        self.log.info(f"Search context generated: {len(search_context)} characters")
                else:
                    self.log.info("No search needed for this message")
            else:
                self.log.info("Total tickets below search threshold, skipping search")
            
            # Build the system prompt
            self.log.info("Building system prompt...")
            system_prompt = self._build_system_prompt(total_tickets, search_threshold)
            self.log.info(f"System prompt built: {len(system_prompt)} characters")
            
            # Build the full context
            full_context = base_context
            if search_context:
                full_context += "\n\n" + search_context
            self.log.info(f"Full context: {len(full_context)} characters")
            
            # Call OpenAI API
            self.log.info("Creating OpenAI client...")
            if not self.openai_api_key:
                raise Exception("OpenAI API key is empty")
            
            try:
                client = OpenAI(api_key=self.openai_api_key)
                self.log.info("OpenAI client created successfully")
            except Exception as e:
                self.log.error(f"Failed to create OpenAI client: {e}")
                raise Exception(f"OpenAI client creation failed: {str(e)}")
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": full_context},
                {"role": "user", "content": user_message}
            ]
            self.log.info(f"Prepared {len(messages)} messages for OpenAI API")
            self.log.info(f"Using model: {self.openai_model}")
            
            self.log.info("Calling OpenAI API...")
            try:
                response = client.chat.completions.create(
                    model=self.openai_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000
                )
                self.log.info("OpenAI API call completed")
            except Exception as e:
                self.log.error(f"OpenAI API call failed: {e}")
                self.log.error(f"API call traceback: {traceback.format_exc()}")
                raise Exception(f"OpenAI API call failed: {str(e)}")
            
            # Validate response structure to prevent NoneType errors
            self.log.info("Validating OpenAI response...")
            if response is None:
                self.log.error("OpenAI response is None")
                raise Exception("Invalid OpenAI API response: response is None")
            
            if not hasattr(response, 'choices'):
                self.log.error(f"OpenAI response missing 'choices' attribute. Response type: {type(response)}")
                self.log.error(f"Response attributes: {dir(response) if response else 'None'}")
                raise Exception("Invalid OpenAI API response: no choices attribute")
            
            if response.choices is None:
                self.log.error("OpenAI response.choices is None")
                raise Exception("Invalid OpenAI API response: choices is None")
            
            if len(response.choices) == 0:
                self.log.error("OpenAI response.choices is empty")
                raise Exception("Invalid OpenAI API response: empty choices list")
            
            self.log.info(f"OpenAI returned {len(response.choices)} choices")
            
            choice = response.choices[0]
            if choice is None:
                self.log.error("First choice is None")
                raise Exception("Invalid OpenAI API response: first choice is None")
            
            if not hasattr(choice, 'message'):
                self.log.error(f"Choice missing 'message' attribute. Choice type: {type(choice)}")
                self.log.error(f"Choice attributes: {dir(choice) if choice else 'None'}")
                raise Exception("Invalid OpenAI API response: choice has no message attribute")
            
            if choice.message is None:
                self.log.error("Choice message is None")
                raise Exception("Invalid OpenAI API response: choice message is None")
            
            content = choice.message.content
            if content is None:
                self.log.warning("Choice message content is None, using fallback")
                content = "No response generated"
            
            self.log.info(f"Successfully extracted response content: {len(content)} characters")
            return content
            
        except Exception as e:
            self.log.error(f"Error in _generate_ai_response: {e}")
            self.log.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def _should_search(self, message):
        """Determine if the message warrants a search.
        
        Args:
            message: User's message
            
        Returns:
            bool: True if search should be performed
        """
        # Keywords that suggest a search is needed
        search_indicators = [
            'find', 'search', 'look for', 'show me', 'list',
            'which', 'what', 'where', 'who', 'about',
            'related to', 'concerning', 'regarding',
            'tickets about', 'issues with', 'problems with'
        ]
        
        message_lower = message.lower()
        return any(indicator in message_lower for indicator in search_indicators)
    
    def _extract_search_terms(self, message):
        """Extract search terms from the user's message.
        
        Args:
            message: User's message
            
        Returns:
            str: Search query
        """
        # Remove common question words and phrases
        stop_phrases = [
            'find', 'search for', 'look for', 'show me', 'list',
            'tell me about', 'what about', 'tickets about',
            'issues with', 'problems with', 'related to',
            'concerning', 'regarding', 'can you', 'could you',
            'please', 'thanks', 'thank you', '?', '.'
        ]
        
        query = message.lower()
        for phrase in stop_phrases:
            query = query.replace(phrase, ' ')
        
        # Clean up and return
        query = ' '.join(query.split())
        return query.strip()
    
    def _build_system_prompt(self, total_tickets, search_threshold):
        """Build the system prompt for the AI.
        
        Args:
            total_tickets: Total number of tickets in the system
            search_threshold: Threshold for allowing search
            
        Returns:
            str: System prompt
        """
        base_prompt = """You are a helpful AI assistant for a Trac issue tracking system. 
Your role is to help users understand and find information about tickets in the system.

You have access to:
1. The most recent tickets in the system (always provided)
2. Search results for specific queries (when applicable)

When answering questions:
- Be concise and accurate
- Reference specific ticket numbers when relevant
- Summarize ticket information clearly
- If you don't have enough information, say so
- Focus on the most relevant tickets for the user's question"""
        
        if total_tickets <= search_threshold:
            base_prompt += f"\n\nNote: The system currently has {total_tickets} tickets, " \
                          f"so all tickets are included in the recent context. No search is needed."
        else:
            base_prompt += f"\n\nNote: The system has {total_tickets} tickets. " \
                          f"Search results are included when your question requires looking beyond " \
                          f"the most recent tickets."
        
        return base_prompt
    
    def _send_json_response(self, req, status, data):
        """Send a JSON response."""
        req.send_response(status)
        req.send_header('Content-Type', 'application/json')
        req.send_header('Cache-Control', 'no-cache')
        req.end_headers()
        req.write(json.dumps(data).encode('utf-8'))
        raise RequestDone
    
    def _send_json_error(self, req, status, message):
        """Send a JSON error response."""
        self._send_json_response(req, status, {
            'error': {
                'code': status,
                'message': message
            }
        })
    
    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        """Return the static resources directory."""
        return []
    
    def get_templates_dirs(self):
        """Return the templates directory."""
        try:
            from importlib.resources import files
            return [str(files('trac.ai') / 'templates')]
        except ImportError:
            # Python < 3.9 fallback
            from pkg_resources import resource_filename
            return [resource_filename('trac.ai', 'templates')]
    
    # IPermissionRequestor methods
    def get_permission_actions(self):
        """Define AI chat permissions."""
        # For now, we just require TICKET_VIEW
        # Could add AI_CHAT permission in the future
        return []
    
    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        """Return the active navigation item."""
        return 'ai' if req.path_info.startswith('/ai') else None
    
    def get_navigation_items(self, req):
        """Add AI Assistant to the main navigation."""
        if 'TICKET_VIEW' in req.perm:
            yield ('mainnav', 'ai',
                   tag.a(_("AI Assistant"), href=req.href.ai()))