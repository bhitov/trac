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

"""Tests to verify all requirements from CHATBOT.md are implemented."""

import unittest
import os

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket


class RequirementsVerificationTestCase(unittest.TestCase):
    """Verify that all requirements are properly implemented."""
    
    def test_no_new_database_tables(self):
        """Verify no new database tables were added."""
        # Check that we didn't add any SQL schema files
        ai_path = os.path.dirname(os.path.dirname(__file__))
        for root, dirs, files in os.walk(ai_path):
            for file in files:
                self.assertFalse(file.endswith('.sql'), 
                    f"Found SQL file {file} - no new tables should be added")
    
    def test_plugin_location(self):
        """Verify plugin is in correct location."""
        import trac.ai
        ai_path = os.path.dirname(trac.ai.__file__)
        self.assertTrue(ai_path.endswith('trac/ai'))
        
        # Check required files exist
        self.assertTrue(os.path.exists(os.path.join(ai_path, '__init__.py')))
        self.assertTrue(os.path.exists(os.path.join(ai_path, 'context_service.py')))
        self.assertTrue(os.path.exists(os.path.join(ai_path, 'search_service.py')))
        self.assertTrue(os.path.exists(os.path.join(ai_path, 'chat_handler.py')))
        self.assertTrue(os.path.exists(os.path.join(ai_path, 'templates', 'ai_chat.html')))
    
    def test_setup_cfg_registration(self):
        """Verify plugin is registered in setup.cfg."""
        setup_cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            'setup.cfg'
        )
        
        with open(setup_cfg_path, 'r') as f:
            content = f.read()
        
        # Check that trac.ai is registered
        self.assertIn('trac.ai = trac.ai', content)
    
    def test_context_service_requirements(self):
        """Verify ContextService meets requirements."""
        env = EnvironmentStub(default_data=True)
        from trac.ai.context_service import ContextService
        service = ContextService(env)
        
        # Check methods exist
        self.assertTrue(hasattr(service, 'get_recent_tickets'))
        self.assertTrue(hasattr(service, 'format_tickets_for_context'))
        
        # Check it queries ticket table
        method_code = service.get_recent_tickets.__code__.co_consts
        sql_found = any('FROM ticket' in str(const) for const in method_code if isinstance(const, str))
        self.assertTrue(sql_found, "ContextService should query ticket table")
    
    def test_search_service_requirements(self):
        """Verify FuzzySearchService meets requirements."""
        env = EnvironmentStub(default_data=True)
        from trac.ai.search_service import FuzzySearchService
        service = FuzzySearchService(env)
        
        # Check required methods
        self.assertTrue(hasattr(service, 'get_total_ticket_count'))
        self.assertTrue(hasattr(service, 'search_tickets'))
        self.assertTrue(hasattr(service, 'search_comments'))
        self.assertTrue(hasattr(service, 'combined_search'))
        
        # Check it can get ticket count
        count = service.get_total_ticket_count()
        self.assertIsInstance(count, int)
    
    def test_chat_handler_requirements(self):
        """Verify ChatHandler meets requirements."""
        env = EnvironmentStub(enable=['trac.ai.*'])
        env.config.set('ai', 'openai_api_key', 'test-key')
        
        from trac.ai.chat_handler import ChatHandler
        handler = ChatHandler(env)
        
        # Check it has IRequestHandler methods
        self.assertTrue(hasattr(handler, 'match_request'))
        self.assertTrue(hasattr(handler, 'process_request'))
        
        # Check match_request for /ai/chat
        class MockReq:
            path_info = '/ai/chat'
        
        self.assertTrue(handler.match_request(MockReq()))
        
        # Check configuration options
        self.assertTrue(hasattr(handler, 'openai_api_key'))
        self.assertTrue(hasattr(handler, 'openai_model'))
        self.assertTrue(hasattr(handler, 'max_context_tickets'))
        self.assertTrue(hasattr(handler, 'search_threshold'))
    
    def test_conditional_search_logic(self):
        """Verify search is conditional based on ticket count."""
        env = EnvironmentStub(
            enable=['trac.ai.*', 'trac.ticket.*'],
            default_data=True
        )
        env.config.set('ai', 'search_threshold', '20')
        
        from trac.ai.search_service import FuzzySearchService
        from trac.ai.chat_handler import ChatHandler
        
        service = FuzzySearchService(env)
        handler = ChatHandler(env)
        
        # Create 10 tickets (less than threshold)
        for i in range(10):
            ticket = Ticket(env)
            ticket['summary'] = f'Test {i}'
            ticket.insert()
        
        count = service.get_total_ticket_count()
        threshold = int(handler.search_threshold)
        
        # Verify count is less than threshold
        self.assertLess(count, threshold)
        
        # The system prompt should reflect this
        prompt = handler._build_system_prompt(count, threshold)
        self.assertIn(str(count) + " tickets", prompt)
        self.assertIn("all tickets are included", prompt)
    
    def test_permissions_respected(self):
        """Verify TICKET_VIEW permission is checked."""
        env = EnvironmentStub(enable=['trac.ai.*'])
        from trac.ai.context_service import ContextService
        
        service = ContextService(env)
        
        # Check that get_recent_tickets checks permissions
        method_code = service.get_recent_tickets.__code__.co_consts
        perm_check_found = any('TICKET_VIEW' in str(const) for const in method_code if isinstance(const, str))
        self.assertTrue(perm_check_found, "Should check TICKET_VIEW permission")
    
    def test_openai_integration_ready(self):
        """Verify OpenAI integration is properly set up."""
        env = EnvironmentStub(enable=['trac.ai.*'])
        env.config.set('ai', 'openai_api_key', 'test-key')
        
        from trac.ai.chat_handler import ChatHandler
        handler = ChatHandler(env)
        
        # Check _generate_ai_response method exists
        self.assertTrue(hasattr(handler, '_generate_ai_response'))
        
        # Check it builds proper prompts
        self.assertTrue(hasattr(handler, '_build_system_prompt'))
        self.assertTrue(hasattr(handler, '_should_search'))
        self.assertTrue(hasattr(handler, '_extract_search_terms'))
    
    def test_ui_endpoint_available(self):
        """Verify UI endpoint is available."""
        env = EnvironmentStub(enable=['trac.ai.*'])
        from trac.ai.chat_handler import ChatHandler
        
        handler = ChatHandler(env)
        
        # Check it has ITemplateProvider methods
        self.assertTrue(hasattr(handler, 'get_templates_dirs'))
        self.assertTrue(hasattr(handler, 'get_htdocs_dirs'))
        
        # Check templates exist
        template_dirs = handler.get_templates_dirs()
        self.assertTrue(len(template_dirs) > 0)
        
        # Check for ai_chat.html
        template_found = False
        for template_dir in template_dirs:
            if os.path.exists(os.path.join(template_dir, 'ai_chat.html')):
                template_found = True
                break
        self.assertTrue(template_found, "ai_chat.html template should exist")


def test_suite():
    return makeSuite(RequirementsVerificationTestCase)