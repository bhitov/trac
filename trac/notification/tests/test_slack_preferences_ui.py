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

"""Tests for Slack notification preferences UI integration."""

import unittest
from unittest.mock import Mock, patch

from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.notification.prefs import NotificationPreferences
from trac.notification.slack import SlackUserSubscriber, SlackChannelSubscriber
from trac.web.session import DetachedSession


class SlackPreferencesUITestCase(unittest.TestCase):
    """Test Slack UI integration with notification preferences."""
    
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
        self.req = MockRequest(self.env, authname='testuser')
        self.req.session = self.session
    
    def tearDown(self):
        self.env.reset_db()
    
    def test_notification_preferences_page_with_slack(self):
        """Test that Slack options appear in notification preferences page."""
        # Get preferences module
        prefs = NotificationPreferences(self.env)
        
        # Render panel data
        template, data_dict = prefs.render_preference_panel(self.req, 'notification')
        data = data_dict['data']
        
        # Check that Slack distributors are included
        self.assertIn('distributors', data)
        distributors = data['distributors']
        
        # Should have slack and slack-dm
        self.assertIn('slack', distributors)
        self.assertIn('slack-dm', distributors)
        
        # Check descriptions
        self.assertIn('description', distributors['slack'])
        self.assertIn('description', distributors['slack-dm'])
        self.assertIn('channel', distributors['slack']['description'].lower())
        self.assertIn('direct', distributors['slack-dm']['description'].lower())
    
    def test_save_slack_dm_subscription(self):
        """Test saving a Slack DM subscription through preferences."""
        from trac.notification.model import Subscription
        
        # Create a proper POST request
        self.req = MockRequest(self.env, method='POST', authname='testuser', args={
            'action': 'add-rule_slack-dm',
            'new-adverb-slack-dm': 'always',
            'new-rule-slack-dm': 'TicketOwnerSubscriber',
            'format-slack-dm': 'text/plain',
            'slack_user_id': 'U01234567',  # Slack user ID
        })
        self.req.session = self.session
        
        prefs = NotificationPreferences(self.env)
        
        # RequestDone will be raised after successful POST handling
        from trac.web.api import RequestDone
        with self.assertRaises(RequestDone):
            prefs.render_preference_panel(self.req, 'notification')
        
        # Check that subscription was created
        subscriptions = list(Subscription.find_by_sid_and_distributor(
            self.env, 'testuser', 1, 'slack-dm'))
        
        self.assertEqual(len(subscriptions), 1)
        sub = subscriptions[0]
        self.assertEqual(sub['distributor'], 'slack-dm')
        self.assertEqual(sub['format'], 'text/plain')
        self.assertEqual(sub['class'], 'TicketOwnerSubscriber')
        self.assertEqual(sub['adverb'], 'always')
        
        # Check that Slack user ID was saved to session
        # Use the same session object that was used in the request
        self.assertEqual(self.req.session.get('slack_user_id'), 'U01234567')
    


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(SlackPreferencesUITestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')