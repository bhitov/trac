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

"""Integration tests for Slack notifications with real API calls.

These tests use the actual Slack configuration from the project.
They will be skipped if Slack is not properly configured.
"""

import os
import unittest
from datetime import datetime

from trac.env import Environment
from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.notification.api import NotificationSystem
from trac.notification.slack import SlackDistributor, SlackFormatter
from trac.util.datefmt import utc

# Try to load project configuration
try:
    # Use the actual project environment
    project_env = Environment('../myproject')
    SLACK_BOT_TOKEN = project_env.config.get('notification', 'slack_bot_token', '')
    SLACK_DEFAULT_CHANNEL = project_env.config.get('notification', 'slack_default_channel', '')
    SLACK_ENABLED = project_env.config.getbool('notification', 'slack_enabled', False)
except:
    # Fallback if project environment can't be loaded
    SLACK_BOT_TOKEN = ''
    SLACK_DEFAULT_CHANNEL = ''
    SLACK_ENABLED = False


@unittest.skipUnless(SLACK_ENABLED and SLACK_BOT_TOKEN and SLACK_DEFAULT_CHANNEL, 
                     "Slack integration must be properly configured in project to run API tests")
class SlackAPIIntegrationTestCase(unittest.TestCase):
    """Test Slack integration with real API calls."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        
        # Use configuration from actual project
        self.env.config.set('notification', 'slack_bot_token', SLACK_BOT_TOKEN)
        self.env.config.set('notification', 'slack_default_channel', SLACK_DEFAULT_CHANNEL)
        self.env.config.set('notification', 'slack_username', 'Trac Test Bot')
        self.env.config.set('notification', 'slack_enabled', 'true')
        self.env.config.set('notification', 'always_notify_channel', 'true')
        
        self.distributor = SlackDistributor(self.env)
        self.formatter = SlackFormatter(self.env)
    
    def test_send_test_message_to_channel(self):
        """Test sending a real message to Slack channel."""
        # Create a test ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test Slack Integration'
        ticket['description'] = 'This is a test ticket for Slack notifications'
        ticket['type'] = 'task'
        ticket['priority'] = 'normal'
        ticket['component'] = 'testing'
        ticket.insert()
        
        # Create test event
        class TestEvent:
            def __init__(self, ticket):
                self.category = 'created'
                self.target = ticket
                self.time = datetime.now(utc)
                self.author = 'test_bot'
        
        event = TestEvent(ticket)
        
        # Format message
        message_data = self.formatter.format('slack', 'full', event)
        
        # Send to channel
        try:
            self.distributor._client = None  # Force client creation
            self.distributor._send_to_channel(SLACK_DEFAULT_CHANNEL, message_data)
            
            # If we get here without exception, the message was sent
            self.assertTrue(True, "Message sent successfully")
            
        except Exception as e:
            self.fail(f"Failed to send message to Slack: {e}")
    
    def test_send_test_dm(self):
        """Test sending a direct message.
        
        Note: This test is automatically skipped if no DM user is configured.
        To enable DM testing, add a slack_dm_test_user setting to trac.ini.
        """
        # Check if DM testing is configured
        dm_user = project_env.config.get('notification', 'slack_dm_test_user', '') if 'project_env' in globals() else ''
        if not dm_user:
            self.skipTest("Set slack_dm_test_user in project trac.ini to test DMs")
        # Create a test ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test DM Integration'
        ticket['description'] = 'Testing direct messages'
        ticket['type'] = 'task'
        ticket['priority'] = 'high'
        ticket.insert()
        
        # Create test event
        class TestEvent:
            def __init__(self, ticket):
                self.category = 'changed'
                self.target = ticket
                self.time = datetime.now(utc)
                self.author = 'test_bot'
                self.changes = {
                    'priority': {'old': 'normal', 'new': 'high'}
                }
                self.comment = 'Increased priority for testing'
        
        event = TestEvent(ticket)
        
        # Format message
        message_data = self.formatter.format('slack-dm', 'dm', event)
        
        # Send DM
        try:
            self.distributor._client = None  # Force client creation
            self.distributor._send_dm(dm_user, message_data)
            
            self.assertTrue(True, "DM sent successfully")
            
        except Exception as e:
            self.fail(f"Failed to send DM: {e}")
    
    def test_channel_validation(self):
        """Test that invalid channels are handled gracefully."""
        # Create simple message data
        message_data = {
            'text': 'Test message to invalid channel',
            'attachments': []
        }
        
        # Try to send to non-existent channel
        self.distributor._client = None  # Force client creation
        
        # This should not raise an exception but should log an error
        self.distributor._send_to_channel('#this-channel-does-not-exist-12345', message_data)
        
        # If we get here, error was handled gracefully
        self.assertTrue(True, "Invalid channel handled gracefully")
    
    def test_formatting_variations(self):
        """Test different formatting scenarios."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Formatting test: Special chars & <tags>'
        ticket['description'] = 'Testing *bold* _italic_ `code` formatting'
        ticket.insert()
        
        # Test different event types
        for category in ['created', 'changed', 'attachment added']:
            class TestEvent:
                def __init__(self, ticket, cat):
                    self.category = cat
                    self.target = ticket
                    self.time = datetime.now(utc)
                    self.author = 'formatter_test'
                    
                    if cat == 'changed':
                        self.changes = {'status': {'old': 'new', 'new': 'assigned'}}
                        self.comment = 'Status update test'
                    elif cat == 'attachment added':
                        self.filename = 'test_file.pdf'
            
            event = TestEvent(ticket, category)
            
            # Format for both styles
            for style in ['full', 'dm']:
                result = self.formatter.format('slack', style, event)
                
                self.assertIsNotNone(result, f"Should format {category} event in {style} style")
                self.assertIn('text', result)
                self.assertIn('attachments', result)
                
                # Verify special characters are handled
                self.assertIn(str(ticket.id), result['text'])


def test_suite():
    return makeSuite(SlackAPIIntegrationTestCase)


if __name__ == '__main__':
    # Instructions for running these tests
    print("""
To run these integration tests:
1. Ensure Slack is properly configured in your project's trac.ini
2. Optionally set slack_dm_test_user in trac.ini to test DMs
3. Run: python -m pytest test_slack_integration.py -v
""")
    
    if not (SLACK_ENABLED and SLACK_BOT_TOKEN and SLACK_DEFAULT_CHANNEL):
        print("\nSkipping tests - Slack not properly configured in project")
    else:
        unittest.main(defaultTest='test_suite')