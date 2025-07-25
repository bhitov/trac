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

"""Tests for Slack notification preferences integration."""

import unittest
from unittest.mock import Mock

from trac.test import EnvironmentStub, makeSuite
from trac.notification.slack import SlackUserSubscriber, SlackChannelSubscriber
from trac.web.session import DetachedSession


class SlackPreferencesTestCase(unittest.TestCase):
    """Test Slack integration with notification system."""
    
    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*'])
        self.env.config.set('notification', 'slack_enabled', 'true')
        self.env.config.set('notification', 'slack_bot_token', 'xoxb-test-token')
        self.env.config.set('notification', 'slack_default_channel', '#general')
        self.env.config.set('notification', 'always_notify_channel', 'true')
        
        # Create test session
        self.session = DetachedSession(self.env, 'testuser')
        self.session['name'] = 'Test User'
        self.session['email'] = 'testuser@example.com'
        self.session.save()
        
        # Create mock request
        self.req = Mock()
        self.req.session = self.session
        self.req.authname = 'testuser'
        self.req.perm = Mock()
    
    def tearDown(self):
        self.env.reset_db()
    
    def test_slack_subscriber_registration(self):
        """Test that Slack subscriber components are registered."""
        from trac.notification.api import NotificationSystem
        
        ns = NotificationSystem(self.env)
        
        # Get all subscriber class names
        subscriber_classes = [s.__class__.__name__ for s in ns.subscribers]
        
        self.assertIn('SlackChannelSubscriber', subscriber_classes)
        self.assertIn('SlackUserSubscriber', subscriber_classes)
        
        # Get the actual components
        slack_user_sub = None
        slack_channel_sub = None
        
        for sub in ns.subscribers:
            if isinstance(sub, SlackUserSubscriber):
                slack_user_sub = sub
            elif isinstance(sub, SlackChannelSubscriber):
                slack_channel_sub = sub
        
        self.assertIsNotNone(slack_user_sub)
        self.assertIsNotNone(slack_channel_sub)
        
        # Check descriptions
        self.assertIn('direct', slack_user_sub.description().lower())
        self.assertIn('channel', slack_channel_sub.description().lower())
    
    def test_slack_in_distributor_list(self):
        """Test that Slack appears in available distributors."""
        from trac.notification.api import NotificationSystem
        
        ns = NotificationSystem(self.env)
        
        # Get all distributors
        distributors = {}
        for distributor in ns.distributors:
            for transport in distributor.transports():
                distributors[transport] = distributor
        
        self.assertIn('slack', distributors, "slack transport should be available")
        self.assertIn('slack-dm', distributors, "slack-dm transport should be available")
    
    def test_notification_preferences_page(self):
        """Test that Slack distributors are available in the system."""
        from trac.notification.api import NotificationSystem
        
        ns = NotificationSystem(self.env)
        
        # Get all distributors
        distributors = {}
        for distributor in ns.distributors:
            for transport in distributor.transports():
                distributors[transport] = distributor
        
        # Verify Slack distributors exist
        self.assertIn('slack', distributors)
        self.assertIn('slack-dm', distributors)
    
    def test_save_slack_subscription(self):
        """Test creating a Slack notification subscription."""
        from trac.notification.model import Subscription
        
        # Create subscription data
        sub_data = {
            'sid': 'testuser',
            'authenticated': 1,
            'distributor': 'slack-dm',
            'format': 'text/plain',
            'priority': 1,
            'adverb': 'always',
            'class': 'TicketOwnerSubscriber'
        }
        
        # Add subscription
        sub_id = Subscription.add(self.env, sub_data)
        self.assertIsNotNone(sub_id)
        
        # Query to verify it was saved
        with self.env.db_query as db:
            rows = db("""
                SELECT distributor, format, class
                FROM notify_subscription
                WHERE id = %s
            """, (sub_id,))
            
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[0], 'slack-dm')
        self.assertEqual(row[1], 'text/plain')
        self.assertEqual(row[2], 'TicketOwnerSubscriber')
    
    def test_slack_subscription_matching(self):
        """Test that Slack channel subscriptions work."""
        from trac.notification.api import NotificationSystem
        from trac.ticket.model import Ticket
        from trac.ticket.notification import TicketChangeEvent
        
        # Enable channel notifications
        self.env.config.set('notification', 'always_notify_channel', 'true')
        self.env.config.set('notification', 'slack_default_channel', '#test')
        
        # Create a ticket event
        ticket = Ticket(self.env)
        ticket['summary'] = 'Test ticket'
        ticket['reporter'] = 'testuser'
        ticket.insert()
        
        # Create event
        event = TicketChangeEvent('created', ticket, ticket['time'], 'testuser')
        
        # Get notification system
        ns = NotificationSystem(self.env)
        
        # Get subscriptions for this event
        subscriptions = list(ns.subscriptions(event))
        
        # Should include Slack channel subscription
        slack_subs = [s for s in subscriptions if s[3] == 'slack']
        self.assertGreater(len(slack_subs), 0, "Should have Slack channel subscription")
        
        # Verify the subscription has the channel address
        channel_sub = slack_subs[0]
        self.assertEqual(channel_sub[2], '#test')  # address


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(SlackPreferencesTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')