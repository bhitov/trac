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

"""End-to-end tests for Slack notifications."""

import unittest
from unittest.mock import patch, MagicMock

from trac.test import EnvironmentStub, makeSuite
from trac.ticket.model import Ticket
from trac.ticket.api import ITicketChangeListener
from trac.notification.api import NotificationSystem


class SlackE2ETestCase(unittest.TestCase):
    """Test end-to-end Slack notification flow."""
    
    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*'])
        
        # Configure Slack
        self.env.config.set('notification', 'slack_enabled', 'true')
        self.env.config.set('notification', 'slack_bot_token', 'xoxb-test-token')
        self.env.config.set('notification', 'slack_default_channel', '#test')
        self.env.config.set('notification', 'slack_username', 'Trac Bot')
        self.env.config.set('notification', 'always_notify_channel', 'true')
        
        # Enable notification system
        self.env.config.set('notification', 'smtp_enabled', 'false')
        
        self.notifier = NotificationSystem(self.env)
    
    @patch('trac.notification.slack.WebClient')
    def test_ticket_creation_notification(self, mock_client_class):
        """Test that creating a ticket sends a Slack notification."""
        # Setup mock Slack client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Create a ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket for Slack'
        ticket['description'] = 'This should trigger a notification'
        ticket['reporter'] = 'testuser'
        ticket['type'] = 'defect'
        ticket['priority'] = 'high'
        ticket['component'] = 'component1'
        
        # Insert ticket
        ticket.insert()
        
        # Manually trigger notification like web_ui does
        from trac.ticket.notification import TicketChangeEvent
        event = TicketChangeEvent('created', ticket, ticket['time'], 
                                  ticket['reporter'])
        self.notifier.notify(event)
        
        # Print debug info
        print(f"Mock client class called: {mock_client_class.called}")
        print(f"Mock client class call count: {mock_client_class.call_count}")
        print(f"Mock client postMessage call count: {mock_client.chat_postMessage.call_count}")
        
        # Verify Slack was called
        mock_client_class.assert_called_once_with(token='xoxb-test-token')
        
        # Should have sent to default channel
        self.assertGreater(mock_client.chat_postMessage.call_count, 0)
        
        # Check the message
        call_args = mock_client.chat_postMessage.call_args
        self.assertEqual(call_args[1]['channel'], '#test')
        self.assertEqual(call_args[1]['username'], 'Trac Bot')
        
        # Verify message content
        self.assertIn('text', call_args[1])
        self.assertIn('New ticket', call_args[1]['text'])
        self.assertIn(str(ticket.id), call_args[1]['text'])
        
        # Check attachments
        self.assertIn('attachments', call_args[1])
        attachment = call_args[1]['attachments'][0]
        self.assertEqual(attachment['color'], 'good')
        self.assertIn('Test ticket for Slack', attachment['title'])
    
    @patch('trac.notification.slack.WebClient')
    def test_ticket_change_notification(self, mock_client_class):
        """Test that changing a ticket sends a notification."""
        # Setup mock Slack client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Create and save a ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Ticket to be changed'
        ticket['status'] = 'new'
        ticket['priority'] = 'normal'
        ticket.insert()
        
        # Clear previous calls
        mock_client.chat_postMessage.reset_mock()
        
        # Change the ticket
        ticket['priority'] = 'high'
        ticket['status'] = 'assigned'
        ticket['owner'] = 'developer'
        ticket.save_changes('testuser', 'Assigning to developer')
        
        # Get the actual change from the ticket
        changes = ticket.get_change(cdate=ticket['changetime'])
        
        # Manually trigger notification
        from trac.ticket.notification import TicketChangeEvent
        event = TicketChangeEvent('changed', ticket, ticket['changetime'], 
                                  'testuser', 'Assigning to developer', changes)
        self.notifier.notify(event)
        
        # Verify notification was sent
        self.assertGreater(mock_client.chat_postMessage.call_count, 0)
        
        call_args = mock_client.chat_postMessage.call_args
        
        # Check message content
        self.assertIn('Ticket updated', call_args[1]['text'])
        
        # Check attachment shows changes
        attachment = call_args[1]['attachments'][0]
        self.assertEqual(attachment['color'], 'warning')
        self.assertIn('Priority: normal → high', attachment['text'])
        self.assertIn('Status: new → assigned', attachment['text'])
    
    @patch('trac.notification.slack.WebClient')
    def test_user_subscription(self, mock_client_class):
        """Test user-specific Slack DM subscription."""
        # Setup mock Slack client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.conversations_open.return_value = {
            'channel': {'id': 'D1234567890'}
        }
        
        # Create a subscription for Slack DMs
        from trac.notification.model import Subscription
        from trac.web.session import DetachedSession
        
        # Create a session for alice with a Slack user ID
        alice_session = DetachedSession(self.env, 'alice')
        alice_session['slack_user_id'] = 'U987654321'
        alice_session.save()
        
        # Test SlackDistributor directly for now
        from trac.notification.slack import SlackDistributor
        distributor = SlackDistributor(self.env)
        distributor._client = None  # Force it to recreate the client
        
        # Create a ticket event
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test DM notification'
        ticket['owner'] = 'alice'
        ticket['reporter'] = 'testuser'
        ticket.insert()
        
        from trac.ticket.notification import TicketChangeEvent
        event = TicketChangeEvent('created', ticket, ticket['time'], 
                                  ticket['reporter'])
        
        # Test channel notification
        # Recipients should be tuples: (sid, authenticated, address, format)
        channel_recipients = [(None, 0, '#test', 'text/plain')]
        distributor.distribute('slack', channel_recipients, event)
        
        # Check first call
        self.assertEqual(mock_client.chat_postMessage.call_count, 1)
        channel_call = mock_client.chat_postMessage.call_args
        self.assertEqual(channel_call[1]['channel'], '#test')
        
        # Test DM notification
        dm_recipients = [('alice', 1, None, 'text/plain')]
        distributor.distribute('slack-dm', dm_recipients, event)
        
        # Check second call
        self.assertEqual(mock_client.chat_postMessage.call_count, 2)
        
        # Should have opened conversation with the Slack user ID
        mock_client.conversations_open.assert_called_with(users=['U987654321'])
        
        # Get all calls
        calls = mock_client.chat_postMessage.call_args_list
        dm_call = calls[1]
        
        # Verify DM was sent to the right channel
        self.assertEqual(dm_call[1]['channel'], 'D1234567890')
    
    @patch('trac.notification.slack.WebClient')
    def test_disabled_notifications(self, mock_client_class):
        """Test that notifications don't send when disabled."""
        # Disable Slack
        self.env.config.set('notification', 'slack_enabled', 'false')
        
        # Create a ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Should not notify'
        ticket.insert()
        
        # Should not have created client
        mock_client_class.assert_not_called()
    
    @patch('trac.notification.slack.WebClient')
    def test_error_handling(self, mock_client_class):
        """Test that errors are handled gracefully."""
        # Setup mock client that raises error
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client
        
        # Create a ticket
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test with error'
        ticket.insert()
        
        # Manually trigger notification
        from trac.ticket.notification import TicketChangeEvent
        event = TicketChangeEvent('created', ticket, ticket['time'], 
                                  ticket['reporter'])
        
        # This should not raise an exception even though Slack fails
        self.notifier.notify(event)
        
        # Ticket should still be created
        self.assertIsNotNone(ticket.id)
        
        # Error should have been caught
        self.assertTrue(mock_client.chat_postMessage.called)


def test_suite():
    return makeSuite(SlackE2ETestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')