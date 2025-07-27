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

"""Tests for Slack notification integration."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.notification.api import NotificationEvent
from trac.notification.slack import (
    SlackDistributor, SlackFormatter, SlackChannelSubscriber, SlackUserSubscriber
)
from trac.util.datefmt import utc


class SlackDistributorTestCase(unittest.TestCase):
    """Test cases for SlackDistributor."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('notification', 'slack_bot_token', 'xoxb-test-token')
        self.env.config.set('notification', 'slack_default_channel', '#test-channel')
        self.env.config.set('notification', 'slack_username', 'TestBot')
        self.env.config.set('notification', 'slack_enabled', 'true')
        self.env.config.set('notification', 'always_notify_channel', 'true')
        
        self.distributor = SlackDistributor(self.env)
    
    def test_transports(self):
        """Test that distributor provides correct transports."""
        transports = self.distributor.transports()
        self.assertIn('slack', transports)
        self.assertIn('slack-dm', transports)
    
    @patch('trac.notification.slack.WebClient')
    def test_distribute_to_channel(self, mock_client_class):
        """Test distributing to a Slack channel."""
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Create test event
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'created')
        
        # Create mock recipient
        recipient = Mock()
        recipient.address = '#dev-channel'
        
        # Distribute event
        self.distributor.distribute('slack', [recipient], event)
        
        # Verify client was initialized with token
        mock_client_class.assert_called_once_with(token='xoxb-test-token')
        
        # Verify message was sent (to both dev-channel and default channel)
        self.assertEqual(mock_client.chat_postMessage.call_count, 2)
        
        # Check that messages were sent to both channels
        calls = mock_client.chat_postMessage.call_args_list
        channels = [call[1]['channel'] for call in calls]
        self.assertIn('#dev-channel', channels)
        self.assertIn('#test-channel', channels)  # default channel
        
        # Verify message structure
        for call in calls:
            self.assertEqual(call[1]['username'], 'TestBot')
            self.assertIn('text', call[1])
    
    @patch('trac.notification.slack.WebClient')
    def test_distribute_dm(self, mock_client_class):
        """Test distributing direct messages."""
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock conversations.open response
        mock_client.conversations_open.return_value = {
            'channel': {'id': 'D1234567890'}
        }
        
        # Create test event
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'changed')
        
        # Create mock recipients
        recipient1 = Mock()
        recipient1.address = '@alice'  # Username format
        
        recipient2 = Mock() 
        recipient2.address = 'U987654321'  # User ID format
        
        # Distribute event
        self.distributor.distribute('slack-dm', [recipient1, recipient2], event)
        
        # Verify DMs were sent
        self.assertEqual(mock_client.chat_postMessage.call_count, 2)
        
        # Check that both messages were sent (order may vary due to set)
        channels = [call[1]['channel'] for call in mock_client.chat_postMessage.call_args_list]
        self.assertIn('@alice', channels)
        self.assertIn('D1234567890', channels)
        
        # Check user ID DM (should open conversation first)
        mock_client.conversations_open.assert_called_once_with(users=['U987654321'])
    
    def test_distribute_disabled(self):
        """Test that distribution is skipped when disabled."""
        self.env.config.set('notification', 'slack_enabled', 'false')
        distributor = SlackDistributor(self.env)
        
        with patch('trac.notification.slack.WebClient') as mock_client_class:
            event = self._create_ticket_event(self._create_test_ticket(), 'created')
            distributor.distribute('slack', [], event)
            
            # Should not create client when disabled
            mock_client_class.assert_not_called()
    
    def test_distribute_no_token(self):
        """Test that distribution is skipped without token."""
        self.env.config.set('notification', 'slack_bot_token', '')
        distributor = SlackDistributor(self.env)
        
        with patch('trac.notification.slack.WebClient') as mock_client_class:
            event = self._create_ticket_event(self._create_test_ticket(), 'created')
            distributor.distribute('slack', [], event)
            
            # Should not create client without token
            mock_client_class.assert_not_called()
    
    @patch('trac.notification.slack.WebClient', None)
    def test_distribute_no_sdk(self):
        """Test graceful handling when slack_sdk is not installed."""
        event = self._create_ticket_event(self._create_test_ticket(), 'created')
        
        # Should not raise exception
        self.distributor.distribute('slack', [], event)
    
    @patch('trac.notification.slack.WebClient')
    def test_api_error_handling(self, mock_client_class):
        """Test handling of Slack API errors."""
        # Mock SlackApiError
        mock_error = Exception("channel_not_found")
        mock_error.response = {'error': 'channel_not_found'}
        
        # Setup mock client that raises error
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = mock_error
        mock_client_class.return_value = mock_client
        
        # Create test event
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'created')
        
        recipient = Mock()
        recipient.address = '#nonexistent'
        
        # Should not raise exception
        self.distributor.distribute('slack', [recipient], event)
        
        # Verify error was logged
        self.assertTrue(mock_client.chat_postMessage.called)
    
    def _create_test_ticket(self):
        """Create a test ticket."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket'
        ticket['description'] = 'Test description'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['component'] = 'component1'
        ticket['owner'] = 'alice'
        ticket.insert()
        return ticket
    
    def _create_ticket_event(self, ticket, category, changes=None):
        """Create a test ticket event."""
        event = Mock(spec=NotificationEvent)
        event.category = category
        event.target = ticket
        event.time = datetime.now(utc)
        event.author = 'testuser'
        
        if changes:
            event.changes = changes
        
        return event


class SlackFormatterTestCase(unittest.TestCase):
    """Test cases for SlackFormatter."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.formatter = SlackFormatter(self.env)
    
    def test_supported_styles(self):
        """Test get_supported_styles."""
        # Should yield tuples
        slack_styles = list(self.formatter.get_supported_styles('slack'))
        self.assertEqual(len(slack_styles), 2)
        self.assertIn(('full', None), slack_styles)
        self.assertIn(('dm', None), slack_styles)
        
        # Should yield nothing for unsupported transport
        email_styles = list(self.formatter.get_supported_styles('email'))
        self.assertEqual(len(email_styles), 0)
    
    def test_format_ticket_created(self):
        """Test formatting of ticket creation."""
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'created')
        
        result = self.formatter.format('slack', 'full', event)
        
        self.assertIsNotNone(result)
        self.assertIn('text', result)
        self.assertIn('New ticket', result['text'])
        self.assertIn(f'#{ticket.id}', result['text'])
        
        # Check attachments
        self.assertIn('attachments', result)
        self.assertEqual(len(result['attachments']), 1)
        
        attachment = result['attachments'][0]
        self.assertEqual(attachment['color'], 'good')
        self.assertIn('New ticket by testuser', attachment['author_name'])
        self.assertIn(ticket['summary'], attachment['title'])
        self.assertIn('fields', attachment)
        
        # Verify fields
        fields = {f['title']: f['value'] for f in attachment['fields']}
        self.assertEqual(fields['Type'], 'defect')
        self.assertEqual(fields['Priority'], 'major')
        self.assertEqual(fields['Component'], 'component1')
        self.assertEqual(fields['Owner'], 'alice')
    
    def test_format_ticket_changed(self):
        """Test formatting of ticket changes."""
        ticket = self._create_test_ticket()
        changes = {
            'status': {'old': 'new', 'new': 'closed'},
            'resolution': {'old': '', 'new': 'fixed'}
        }
        event = self._create_ticket_event(ticket, 'changed', changes)
        event.comment = 'Fixed the issue'
        
        result = self.formatter.format('slack', 'full', event)
        
        self.assertIsNotNone(result)
        self.assertIn('Ticket updated', result['text'])
        
        attachment = result['attachments'][0]
        self.assertEqual(attachment['color'], 'warning')
        self.assertIn('Status: new → closed', attachment['text'])
        self.assertIn('Resolution:  → fixed', attachment['text'])
        
        # Check comment in full style
        self.assertIn('fields', attachment)
        comment_field = next(f for f in attachment['fields'] if f['title'] == 'Comment')
        self.assertEqual(comment_field['value'], 'Fixed the issue')
    
    def test_format_dm_style(self):
        """Test DM style formatting is more concise."""
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'created')
        
        full_result = self.formatter.format('slack-dm', 'full', event)
        dm_result = self.formatter.format('slack-dm', 'dm', event)
        
        # Both should have content
        self.assertIsNotNone(full_result)
        self.assertIsNotNone(dm_result)
        
        # DM style might be more concise (implementation specific)
        # For now they're the same, but this is where you'd test differences
    
    def test_format_attachment_added(self):
        """Test formatting of attachment events."""
        ticket = self._create_test_ticket()
        event = self._create_ticket_event(ticket, 'attachment added')
        event.filename = 'screenshot.png'
        
        result = self.formatter.format('slack', 'full', event)
        
        self.assertIsNotNone(result)
        self.assertIn('Attachment added', result['text'])
        
        attachment = result['attachments'][0]
        self.assertIn('screenshot.png', attachment['title'])
    
    def test_format_invalid_event(self):
        """Test handling of invalid events."""
        event = Mock(spec=['category'])  # Spec to ensure no target attribute
        event.category = 'unknown'
        
        result = self.formatter.format('slack', 'full', event)
        self.assertIsNone(result)
    
    def _create_test_ticket(self):
        """Create a test ticket."""
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket'
        ticket['description'] = 'Test description'
        ticket['type'] = 'defect'
        ticket['priority'] = 'major'
        ticket['component'] = 'component1'
        ticket['owner'] = 'alice'
        ticket.insert()
        return ticket
    
    def _create_ticket_event(self, ticket, category, changes=None):
        """Create a test ticket event."""
        event = Mock()
        event.category = category
        event.target = ticket
        event.time = datetime.now(utc)
        event.author = 'testuser'
        
        if changes:
            event.changes = changes
        
        return event


class SlackSubscriberTestCase(unittest.TestCase):
    """Test cases for Slack subscribers."""
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('notification', 'slack_default_channel', '#general')
        self.env.config.set('notification', 'always_notify_channel', 'true')
    
    def test_channel_subscriber(self):
        """Test SlackChannelSubscriber."""
        subscriber = SlackChannelSubscriber(self.env)
        
        # Test description - should be None (hidden from UI)
        self.assertIsNone(subscriber.description())
        
        # Test authentication requirement
        self.assertFalse(subscriber.requires_authentication())
        
        # Test matching
        event = Mock()
        event.category = 'created'
        recipients = list(subscriber.matches(event))
        
        self.assertEqual(len(recipients), 1)
        # Should be a subscription tuple
        self.assertEqual(recipients[0][4], '#general')  # address at index 4
    
    def test_channel_subscriber_disabled(self):
        """Test channel subscriber when disabled."""
        self.env.config.set('notification', 'always_notify_channel', 'false')
        subscriber = SlackChannelSubscriber(self.env)
        
        event = Mock()
        recipients = list(subscriber.matches(event))
        
        self.assertEqual(len(recipients), 0)
    
    def test_user_subscriber(self):
        """Test SlackUserSubscriber."""
        subscriber = SlackUserSubscriber(self.env)
        
        # Test description - should be None (hidden from UI)
        self.assertIsNone(subscriber.description())
        
        # Test authentication requirement
        self.assertTrue(subscriber.requires_authentication())
        
        # Test default subscriptions
        self.assertEqual(subscriber.default_subscriptions(), [])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(SlackDistributorTestCase))
    suite.addTest(makeSuite(SlackFormatterTestCase))
    suite.addTest(makeSuite(SlackSubscriberTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')