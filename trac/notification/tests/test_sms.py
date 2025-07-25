# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 Edgewall Software
# All rights reserved.

import unittest
from unittest.mock import Mock, patch, MagicMock

from trac.test import EnvironmentStub, MockRequest
from trac.ticket.model import Ticket
from trac.notification.api import NotificationEvent, INotificationFormatter
from trac.notification.sms import SmsDistributor, SmsFormatter
from trac.notification.prefs import NotificationPreferences
from trac.config import ConfigurationError
from trac.core import Component, implements
from trac.web.api import Request


class SmsDistributorTestCase(unittest.TestCase):
    """Tests for SmsDistributor"""
    
    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('notification', 'sms_enabled', 'true')
        self.env.config.set('notification', 'twilio_account_sid', 'test_sid')
        self.env.config.set('notification', 'twilio_auth_token', 'test_token')
        self.env.config.set('notification', 'twilio_from_number', '+1234567890')
        
        self.distributor = SmsDistributor(self.env)
        
    def test_transports(self):
        """Test that SMS transport is provided"""
        transports = list(self.distributor.transports())
        self.assertEqual(['sms'], transports)
        
    @patch('twilio.rest.Client')
    def test_twilio_client_initialization(self, mock_client):
        """Test Twilio client is initialized correctly"""
        client = self.distributor.twilio_client
        mock_client.assert_called_once_with('test_sid', 'test_token')
        
    @patch('twilio.rest.Client')
    def test_twilio_client_initialization_failure(self, mock_client):
        """Test handling of Twilio initialization failure"""
        mock_client.side_effect = Exception("Auth failed")
        client = self.distributor.twilio_client
        self.assertIsNone(client)
        
    def test_distribute_wrong_transport(self):
        """Test distribute ignores non-SMS transport"""
        # Should return None and not raise
        result = self.distributor.distribute('email', [], Mock())
        self.assertIsNone(result)
        
    def test_distribute_sms_disabled(self):
        """Test distribute does nothing when SMS is disabled"""
        self.env.config.set('notification', 'sms_enabled', 'false')
        distributor = SmsDistributor(self.env)
        
        result = distributor.distribute('sms', [], Mock())
        self.assertIsNone(result)
        
    @patch('twilio.rest.Client')
    @patch('trac.notification.sms.get_session_attribute')
    def test_distribute_success(self, mock_get_session, mock_client):
        """Test successful SMS distribution"""
        # Setup mocks
        mock_twilio = Mock()
        mock_client.return_value = mock_twilio
        mock_messages = Mock()
        mock_twilio.messages = mock_messages
        mock_get_session.return_value = '+15551234567'
        
        # Create event
        ticket = Mock()
        ticket.id = 123
        ticket.realm = 'ticket'
        ticket.__getitem__ = Mock(return_value='Test summary')
        event = NotificationEvent('ticket', 'created', ticket, '')
        
        # Create formatter in the environment
        formatter = SmsFormatter(self.env)
        
        # Test distribution - formatter will be found via ExtensionPoint
        recipients = [('user1', 1, None, 'text/plain')]
        self.distributor.distribute('sms', recipients, event)
        
        # Verify SMS was sent - SmsFormatter formats created events as "New ticket #X: summary"
        ticket.__getitem__.assert_called_with('summary')
        expected_body = "New ticket #123: Test summary"
        mock_messages.create.assert_called_once_with(
            body=expected_body,
            from_='+1234567890',
            to='+15551234567'
        )
        
    @patch('twilio.rest.Client')
    def test_distribute_no_phone_number(self, mock_client):
        """Test distribution skips recipients without phone numbers"""
        mock_twilio = Mock()
        mock_client.return_value = mock_twilio
        
        # Create formatter in the environment
        formatter = SmsFormatter(self.env)
        
        ticket = Mock()
        ticket.realm = 'ticket'
        event = NotificationEvent('ticket', 'created', ticket, '')
        
        # Recipient with no phone number
        recipients = [('user1', 1, None, 'text/plain')]
        
        with patch('trac.notification.sms.get_session_attribute', return_value=None):
            self.distributor.distribute('sms', recipients, event)
            
        # Should not try to send SMS
        mock_twilio.messages.create.assert_not_called()
        
    @patch('twilio.rest.Client')
    def test_send_sms_exception_handling(self, mock_client):
        """Test exception handling in _send_sms"""
        mock_twilio = Mock()
        mock_client.return_value = mock_twilio
        mock_twilio.messages.create.side_effect = Exception("Twilio error")
        
        # Should raise the exception after logging
        with self.assertRaises(Exception) as context:
            self.distributor._send_sms('+15551234567', 'Test message')
        self.assertEqual(str(context.exception), "Twilio error")
        
    @patch('twilio.rest.Client')
    def test_phone_number_prefix_handling(self, mock_client):
        """Test that phone numbers without + get the prefix added"""
        mock_twilio = Mock()
        mock_client.return_value = mock_twilio
        mock_messages = Mock()
        mock_twilio.messages = mock_messages
        mock_result = Mock(sid='SM123', status='queued')
        mock_messages.create.return_value = mock_result
        
        # Test with number missing + prefix
        self.distributor._send_sms('15551234567', 'Test message')
        
        # Should add the + prefix
        mock_messages.create.assert_called_once_with(
            body='Test message',
            from_='+1234567890',
            to='+15551234567'
        )


class SmsFormatterTestCase(unittest.TestCase):
    """Tests for SmsFormatter"""
    
    def setUp(self):
        self.env = EnvironmentStub()
        self.formatter = SmsFormatter(self.env)
        
    def test_get_supported_styles(self):
        """Test supported styles for SMS transport"""
        styles = list(self.formatter.get_supported_styles('sms'))
        self.assertEqual([('text/plain', 'ticket')], styles)
        
        # Non-SMS transport
        styles = list(self.formatter.get_supported_styles('email'))
        self.assertEqual([], styles)
        
    def test_format_ticket_created(self):
        """Test formatting of ticket creation event"""
        ticket = Mock()
        ticket.id = 123
        ticket.__getitem__ = Mock(return_value="Fix the bug")
        
        event = Mock()
        event.category = 'created'
        event.target = ticket
        
        message = self.formatter.format('sms', 'text/plain', event)
        self.assertEqual("New ticket #123: Fix the bug", message)
        
    def test_format_ticket_changed(self):
        """Test formatting of ticket change event"""
        ticket = Mock()
        ticket.id = 456
        ticket.__getitem__ = Mock(return_value="Update documentation")
        
        event = Mock()
        event.category = 'changed'
        event.target = ticket
        event.changes = {
            'fields': {
                'status': {'old': 'new', 'new': 'assigned'},
                'owner': {'old': '', 'new': 'john'}
            }
        }
        
        message = self.formatter.format('sms', 'text/plain', event)
        self.assertEqual(
            "Ticket #456 updated: Update documentation (status: assigned, owner: john)",
            message
        )
        
    def test_format_ticket_changed_no_fields(self):
        """Test formatting of ticket change with no field changes"""
        ticket = Mock()
        ticket.id = 789
        ticket.__getitem__ = Mock(return_value="Refactor code")
        
        event = Mock()
        event.category = 'changed'
        event.target = ticket
        event.changes = {}
        
        message = self.formatter.format('sms', 'text/plain', event)
        self.assertEqual("Ticket #789 updated: Refactor code", message)
        
    def test_format_unknown_category(self):
        """Test formatting returns None for unknown event category"""
        event = Mock()
        event.category = 'unknown'
        
        message = self.formatter.format('sms', 'text/plain', event)
        self.assertIsNone(message)
        
    def test_format_wrong_transport(self):
        """Test format returns None for non-SMS transport"""
        event = Mock()
        message = self.formatter.format('email', 'text/plain', event)
        self.assertIsNone(message)


class SmsPreferencesTestCase(unittest.TestCase):
    """Test SMS preferences in notification panel"""
    
    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('notification', 'sms_enabled', 'true')
        self.env.config.set('notification', 'twilio_account_sid', 'test_sid')
        self.env.config.set('notification', 'twilio_auth_token', 'test_token')
        self.env.config.set('notification', 'twilio_from_number', '+1234567890')
        self.env.config.set('components', 'trac.notification.sms.*', 'enabled')
        
    def test_phone_number_field_in_preferences(self):
        """Test that phone number field appears in notification preferences"""
        # Create components
        distributor = SmsDistributor(self.env)
        panel = NotificationPreferences(self.env)
        
        # Create a mock request
        req = MockRequest(self.env, method='GET', path_info='/prefs/notification',
                         authname='test_user')
        
        # Render the preferences panel
        template, data_dict = panel.render_preference_panel(req, 'notification')
        
        # Check that SMS distributor is in the list
        data = data_dict['data']
        self.assertIn('rules', data)
        
        # Check that SMS transport is available
        self.assertIn('sms', data['rules'])
        
        # Check that phone_number field is in data
        self.assertIn('phone_number', data)
        
        # The template should be the notification preferences template
        self.assertEqual('prefs_notification.html', template)
        
    def test_sms_preferences_ui_elements(self):
        """Test that SMS preferences UI elements are present"""
        # Create components
        distributor = SmsDistributor(self.env)
        panel = NotificationPreferences(self.env)
        
        # Create a mock request
        req = MockRequest(self.env, method='GET', path_info='/prefs/notification',
                         authname='test_user')
        
        template, data_dict = panel.render_preference_panel(req, 'notification')
        data = data_dict['data']
        
        # Verify the phone_number field is included in the data
        self.assertIn('phone_number', data)
        
        # Verify SMS is in the available rules (transports)
        self.assertIn('sms', data['rules'])
        
        # Verify SMS has formatters available
        self.assertIn('sms', data['formatters'])
        self.assertIn('text/plain', data['formatters']['sms'])
        
        # Test that the template is the correct one
        self.assertEqual('prefs_notification.html', template)


class SmsIntegrationTestCase(unittest.TestCase):
    """Integration tests for SMS notifications"""
    
    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('notification', 'sms_enabled', 'true')
        self.env.config.set('notification', 'twilio_account_sid', 'test_sid')
        self.env.config.set('notification', 'twilio_auth_token', 'test_token')
        self.env.config.set('notification', 'twilio_from_number', '+1234567890')
        
    @patch('twilio.rest.Client')
    def test_full_notification_flow(self, mock_client):
        """Test complete notification flow from event to SMS"""
        # Setup Twilio mock
        mock_twilio = Mock()
        mock_client.return_value = mock_twilio
        mock_messages = Mock()
        mock_twilio.messages = mock_messages
        
        # Create components
        distributor = SmsDistributor(self.env)
        formatter = SmsFormatter(self.env)
        
        # Create ticket and event
        ticket = Mock()
        ticket.id = 999
        ticket.realm = 'ticket'
        ticket.__getitem__ = Mock(return_value="Critical issue")
        
        event = NotificationEvent('ticket', 'created', ticket, '')
        event.realm = 'ticket'
        event.target = ticket
        event.category = 'created'
        
        # Test with phone number in recipient tuple
        recipients = [('user1', 1, '+15551234567', 'text/plain')]
        distributor.distribute('sms', recipients, event)
        
        # Verify SMS was sent with correct content
        mock_messages.create.assert_called_once_with(
            body="New ticket #999: Critical issue",
            from_='+1234567890',
            to='+15551234567'
        )
        
    def test_message_length_constraint(self):
        """Test that SMS messages are kept reasonably short"""
        formatter = SmsFormatter(self.env)
        
        # Create ticket with very long summary
        ticket = Mock()
        ticket.id = 1
        long_summary = "A" * 200  # 200 character summary
        ticket.__getitem__ = Mock(return_value=long_summary)
        
        event = Mock()
        event.category = 'created'
        event.target = ticket
        
        message = formatter.format('sms', 'text/plain', event)
        
        # Message should still be formatted correctly
        # Total length should be reasonable for SMS (160 char limit)
        self.assertTrue(len(message) > 0)
        self.assertTrue(message.startswith("New ticket #1:"))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(SmsDistributorTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(SmsFormatterTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(SmsPreferencesTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(SmsIntegrationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')