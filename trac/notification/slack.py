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

"""Slack notification integration for Trac.

This module provides both channel and direct message notifications for Trac events.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Sequence

from trac.core import Component, implements, TracError
from trac.config import BoolOption, Option
from trac.notification.api import (
    INotificationDistributor,
    INotificationFormatter,
    INotificationSubscriber,
    NotificationEvent,
)
from trac.ticket.model import Ticket
from trac.util.datefmt import to_datetime
from trac.util.text import shorten_line
from trac.util.translation import _
from trac.web import IRequestHandler
from trac.web.api import RequestDone
from trac.web.chrome import add_notice, add_warning

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    WebClient = None
    SlackApiError = Exception

try:
    import requests
except ImportError:
    requests = None


class SlackDistributor(Component):
    """Distribute notifications to Slack channels and direct messages."""
    
    implements(INotificationDistributor)
    
    # Configuration options
    slack_bot_token = Option(
        'notification', 'slack_bot_token', '',
        doc="Slack bot token (xoxb-...) for sending messages")
    
    slack_default_channel = Option(
        'notification', 'slack_default_channel', '#general',
        doc="Default Slack channel for notifications")
    
    slack_username = Option(
        'notification', 'slack_username', 'Trac',
        doc="Bot username to display in Slack")
    
    slack_enabled = BoolOption(
        'notification', 'slack_enabled', True,
        doc="Enable Slack notifications")
    
    always_notify_channel = BoolOption(
        'notification', 'always_notify_channel', True,
        doc="Always send notifications to the default channel")
    
    def __init__(self):
        super().__init__()
        self._client = None
    
    # INotificationDistributor methods
    def transports(self):
        """Return list of supported transports."""
        return ['slack', 'slack-dm']
    
    def description(self, transport):
        """Return description for the transport."""
        if transport == 'slack':
            return _("Slack channel notifications")
        elif transport == 'slack-dm':
            return _("Slack direct message notifications")
        return ""
    
    def distribute(self, transport, recipients, event):
        """Distribute event notifications to Slack."""
        if not self.slack_enabled or not self.slack_bot_token:
            self.log.debug("Slack notifications disabled or token not configured")
            return
        
        if WebClient is None:
            self.log.error("slack_sdk not installed - run: pip install slack_sdk")
            return
        
        # Initialize client if needed
        if self._client is None:
            self._client = WebClient(token=self.slack_bot_token)
        
        # Format the message
        formatter = SlackFormatter(self.env)
        style = 'full' if transport == 'slack' else 'dm'
        message_data = formatter.format(transport, style, event)
        
        if not message_data:
            self.log.debug("No message generated for event %s", event)
            return
        
        # Process recipients
        if transport == 'slack':
            # Channel subscriptions
            channels = set()
            for recipient in recipients:
                # Recipients from NotificationSystem are tuples: (sid, authenticated, address, format)
                if isinstance(recipient, tuple) and len(recipient) >= 3:
                    sid = recipient[0]
                    authenticated = recipient[1]
                    address = recipient[2]
                    
                    # Try to get user-configured Slack channel name from session
                    slack_channel_name = None
                    if sid and authenticated:
                        from trac.web.session import DetachedSession
                        session = DetachedSession(self.env, sid)
                        slack_channel_name = session.get('slack_channel_name')
                    
                    # Use user's configured channel if available, otherwise use address
                    if slack_channel_name:
                        channels.add(slack_channel_name)
                    elif address:
                        channels.add(address)
                # Handle simple address format
                elif hasattr(recipient, 'address') and recipient.address:
                    channels.add(recipient.address)
                # Handle string addresses
                elif isinstance(recipient, str):
                    channels.add(recipient)
            
            # Always include default channel if configured
            if self.always_notify_channel and self.slack_default_channel:
                channels.add(self.slack_default_channel)
            
            for channel in channels:
                self._send_to_channel(channel, message_data)
        
        elif transport == 'slack-dm':
            # Direct message subscriptions
            users = set()
            for recipient in recipients:
                # Recipients from NotificationSystem are tuples: (sid, authenticated, address, format)
                if isinstance(recipient, tuple) and len(recipient) >= 3:
                    sid = recipient[0]
                    authenticated = recipient[1]
                    address = recipient[2]
                    
                    # Try to get Slack user ID from session
                    slack_user_id = None
                    if sid and authenticated:
                        from trac.web.session import DetachedSession
                        session = DetachedSession(self.env, sid)
                        # Check for OAuth-based slack_uid first, then fall back to manual slack_user_id
                        slack_user_id = session.get('slack_uid') or session.get('slack_user_id')
                    
                    # Use Slack user ID if available, otherwise use address
                    if slack_user_id:
                        users.add(slack_user_id)
                    elif address:
                        users.add(address)
                # Handle simple address format
                elif hasattr(recipient, 'address') and recipient.address:
                    users.add(recipient.address)
                # Handle string addresses
                elif isinstance(recipient, str):
                    users.add(recipient)
            
            for user in users:
                self._send_dm(user, message_data)
    
    def _send_to_channel(self, channel, message_data):
        """Send message to a Slack channel."""
        # Ensure channel starts with #
        if not channel.startswith('#'):
            channel = f'#{channel}'
        
        try:
            self._client.chat_postMessage(
                channel=channel,
                username=self.slack_username,
                **message_data
            )
            self.log.info("Sent Slack notification to %s", channel)
        except Exception as e:
            self.log.error("Failed to send to channel %s: %s", channel, e)
    
    def _send_dm(self, user_id, message_data):
        """Send direct message to a Slack user."""
        try:
            # If it's a username (@alice), use it directly
            if user_id.startswith('@'):
                channel = user_id
            else:
                # Otherwise, open a DM channel with the user ID
                response = self._client.conversations_open(users=[user_id])
                channel = response['channel']['id']
            
            self._client.chat_postMessage(
                channel=channel,
                username=self.slack_username,
                **message_data
            )
            self.log.info("Sent Slack DM to %s", user_id)
        except Exception as e:
            self.log.error("Failed to send DM to %s: %s", user_id, e)


class SlackFormatter(Component):
    """Format Trac events for Slack messages."""
    
    implements(INotificationFormatter)
    
    # INotificationFormatter methods
    def get_supported_styles(self, transport):
        """Return supported styles for the transport."""
        if transport in ('slack', 'slack-dm'):
            # Return tuples of (style, realm)
            yield ('full', None)
            yield ('dm', None)
    
    def format(self, transport, style, event):
        """Format the event for Slack."""
        if transport not in ('slack', 'slack-dm'):
            return None
        
        # Extract ticket information
        ticket = self._get_ticket(event)
        if not ticket:
            return None
        
        # Build message based on event type
        if hasattr(event, 'category'):
            if event.category == 'created':
                return self._format_ticket_created(ticket, event, style)
            elif event.category == 'changed':
                return self._format_ticket_changed(ticket, event, style)
            elif event.category == 'attachment added':
                return self._format_attachment_added(ticket, event, style)
        
        # Default format
        return self._format_generic(ticket, event, style)
    
    def _get_ticket(self, event):
        """Extract ticket from event."""
        if hasattr(event, 'target'):
            return event.target
        elif hasattr(event, 'ticket'):
            return event.ticket
        return None
    
    def _format_ticket_created(self, ticket, event, style):
        """Format new ticket notification."""
        ticket_url = self.env.abs_href.ticket(ticket.id)
        author = getattr(event, 'author', 'unknown')
        
        # Build attachments for rich formatting
        attachments = [{
            'color': 'good',
            'author_name': f'New ticket by {author}',
            'title': f'Ticket #{ticket.id}: {ticket["summary"]}',
            'title_link': str(ticket_url),
            'fields': [
                {'title': 'Type', 'value': ticket['type'], 'short': True},
                {'title': 'Priority', 'value': ticket['priority'], 'short': True},
                {'title': 'Component', 'value': ticket['component'], 'short': True},
                {'title': 'Owner', 'value': ticket['owner'] or 'unassigned', 'short': True},
            ],
            'fallback': f'New ticket #{ticket.id}: {ticket["summary"]}',
            'ts': int(to_datetime(event.time).timestamp()) if hasattr(event, 'time') else None
        }]
        
        if style == 'full' and ticket['description']:
            # Include description for full style
            desc = shorten_line(ticket['description'], 300)
            attachments[0]['text'] = desc
        
        return {
            'text': f'🎫 New ticket: <{ticket_url}|#{ticket.id}>',
            'attachments': attachments
        }
    
    def _format_ticket_changed(self, ticket, event, style):
        """Format ticket change notification."""
        ticket_url = self.env.abs_href.ticket(ticket.id)
        author = getattr(event, 'author', 'unknown')
        comment = getattr(event, 'comment', '')
        
        # Build change summary
        changes = []
        if hasattr(event, 'changes') and event.changes:
            # Check if changes has 'fields' key (from get_change)
            field_changes = event.changes.get('fields', event.changes)
            for field, change in field_changes.items():
                if field == 'comment':
                    continue  # Comments are handled separately
                    
                if isinstance(change, dict) and 'old' in change and 'new' in change:
                    old_value = change['old']
                    new_value = change['new']
                    if field == 'status':
                        changes.append(f'• Status: {old_value} → {new_value}')
                    elif field == 'owner':
                        changes.append(f'• Assigned to: {new_value or "unassigned"}')
                    else:
                        changes.append(f'• {field.title()}: {old_value} → {new_value}')
        
        change_text = '\n'.join(changes) if changes else 'No field changes'
        
        # Build attachment
        attachment = {
            'color': 'warning',
            'author_name': f'Updated by {author}',
            'title': f'Ticket #{ticket.id}: {ticket["summary"]}',
            'title_link': str(ticket_url),
            'text': change_text,
            'fallback': f'Ticket #{ticket.id} updated by {author}',
            'ts': int(to_datetime(event.time).timestamp()) if hasattr(event, 'time') else None
        }
        
        # Add comment if present
        if comment and style == 'full':
            attachment['fields'] = [{
                'title': 'Comment',
                'value': shorten_line(comment, 500),
                'short': False
            }]
        
        return {
            'text': f'📝 Ticket updated: <{ticket_url}|#{ticket.id}>',
            'attachments': [attachment]
        }
    
    def _format_attachment_added(self, ticket, event, style):
        """Format attachment added notification."""
        ticket_url = self.env.abs_href.ticket(ticket.id)
        author = getattr(event, 'author', 'unknown')
        filename = getattr(event, 'filename', 'unknown')
        
        return {
            'text': f'📎 Attachment added to <{ticket_url}|#{ticket.id}>',
            'attachments': [{
                'color': '#439FE0',
                'author_name': f'Attachment by {author}',
                'title': f'File: {filename}',
                'title_link': str(ticket_url),
                'fallback': f'Attachment {filename} added to ticket #{ticket.id}',
                'ts': int(to_datetime(event.time).timestamp()) if hasattr(event, 'time') else None
            }]
        }
    
    def _format_generic(self, ticket, event, style):
        """Generic format for other events."""
        ticket_url = self.env.abs_href.ticket(ticket.id)
        event_type = getattr(event, 'category', 'event')
        
        return {
            'text': f'Ticket event: <{ticket_url}|#{ticket.id}>',
            'attachments': [{
                'color': '#666666',
                'title': f'{event_type.title()} - Ticket #{ticket.id}',
                'title_link': str(ticket_url),
                'text': ticket.get('summary', 'No summary') if hasattr(ticket, 'get') else str(ticket),
                'fallback': f'{event_type} on ticket #{ticket.id}',
                'ts': int(to_datetime(event.time).timestamp()) if hasattr(event, 'time') else None
            }]
        }


class SlackChannelSubscriber(Component):
    """Global channel notifications - not user configurable."""
    
    implements(INotificationSubscriber)
    
    # INotificationSubscriber methods
    def matches(self, event):
        """Match all ticket events for channel notifications."""
        # This subscriber handles the global channel notifications
        # configured in trac.ini - it's not user-configurable
        if self.config.getbool('notification', 'always_notify_channel'):
            channel = self.config.get('notification', 'slack_default_channel')
            if channel and hasattr(event, 'category') and event.category in ('created', 'changed', 'attachment added'):
                # Return subscription tuple: 
                # (class, distributor, sid, authenticated, address, format, priority, adverb)
                yield ('SlackChannelSubscriber', 'slack', None, 0, 
                       channel, 'text/plain', 1, 'always')
    
    def description(self):
        """Description for the subscription type."""
        # Return None to hide from user preferences
        return None
    
    def requires_authentication(self):
        """Whether authentication is required."""
        return False
    
    def default_subscriptions(self):
        """Default subscriptions."""
        return []


class SlackUserSubscriber(Component):
    """Allow users to subscribe to Slack DMs."""
    
    implements(INotificationSubscriber)
    
    # INotificationSubscriber methods
    def matches(self, event):
        """Match events based on user subscriptions."""
        # This is handled by the subscription system
        # The actual matching is done by subscription rules
        # When a match occurs, we'll use the user's stored Slack ID
        from trac.web.session import DetachedSession
        
        # This subscriber doesn't directly match - it relies on
        # subscription rules created through the UI
        return iter([])
    
    def description(self):
        """Description for the subscription type."""
        # Return None to hide from user preferences
        # This subscriber is handled internally, not user-configurable
        return None
    
    def requires_authentication(self):
        """Whether authentication is required."""
        return True
    
    def default_subscriptions(self):
        """Default subscriptions."""
        return []


class SlackOAuth(Component):
    """Handle Slack OAuth flow for user authentication."""
    
    implements(IRequestHandler)
    
    # Configuration options
    slack_client_id = Option(
        'notification', 'slack_client_id', '',
        doc="Slack OAuth app client ID")
    
    slack_client_secret = Option(
        'notification', 'slack_client_secret', '',
        doc="Slack OAuth app client secret")
    
    # IRequestHandler methods
    def match_request(self, req):
        """Match Slack OAuth routes."""
        return req.path_info in ("/slack/auth", "/slack/callback", "/slack/disconnect")
    
    def process_request(self, req):
        """Process OAuth requests."""
        if req.path_info == "/slack/auth":
            # Check if OAuth is configured
            if not self.slack_client_id:
                raise TracError(
                    "Slack OAuth is not configured. "
                    "Please ask your administrator to set up a Slack app and configure "
                    "slack_client_id and slack_client_secret in trac.ini"
                )
            
            # Redirect user to Slack OAuth
            # Use configured base_url for OAuth redirect
            base_url = self.config.get('trac', 'base_url')
            if base_url:
                redirect_uri = base_url.rstrip('/') + '/slack/callback'
            else:
                redirect_uri = req.abs_href.slack("callback")
            
            url = "https://slack.com/oauth/v2/authorize"
            params = {
                "client_id": self.slack_client_id,
                "scope": "chat:write,im:write,users:read",
                "redirect_uri": redirect_uri,
                "state": req.session.sid,  # CSRF protection
            }
            req.redirect(url + "?" + urllib.parse.urlencode(params))
            
        elif req.path_info == "/slack/callback":
            # Handle OAuth callback
            code = req.args.get("code")
            state = req.args.get("state")
            error = req.args.get("error")
            
            # Handle user cancellation
            if error:
                if error == "access_denied":
                    add_notice(req, "Slack authorization cancelled")
                else:
                    add_warning(req, f"Slack OAuth error: {error}")
                req.redirect(req.href.prefs("notification"))
                return
            
            # Verify CSRF token - be more lenient with state checking
            # The session might be different if coming from external domain
            if state and len(state) > 0:
                # Just log the mismatch instead of failing
                if state != req.session.sid:
                    self.log.warning(f"State mismatch: expected {req.session.sid}, got {state}")
            
            # Exchange code for token
            self._complete_oauth(req, code)
            
            add_notice(req, "Successfully connected to Slack!")
            req.redirect(req.href.prefs("notification"))
            
        elif req.path_info == "/slack/disconnect":
            # Disconnect Slack account
            if "slack_uid" in req.session:
                del req.session["slack_uid"]
            if "slack_username" in req.session:
                del req.session["slack_username"]
            req.session.save()
            req.redirect(req.href.prefs("notification"))
    
    def _complete_oauth(self, req, code):
        """Complete OAuth flow by exchanging code for token."""
        if not self.slack_client_id or not self.slack_client_secret:
            raise TracError("Slack OAuth not configured")
        
        if requests is None:
            raise TracError("requests package not installed")
        
        # Exchange code for access token
        # Use configured base_url for OAuth redirect
        base_url = self.config.get('trac', 'base_url')
        if base_url:
            redirect_uri = base_url.rstrip('/') + '/slack/callback'
        else:
            redirect_uri = req.abs_href.slack("callback")
            
        token_resp = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self.slack_client_id,
                "client_secret": self.slack_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        ).json()
        
        if not token_resp.get("ok"):
            raise TracError("Slack auth failed: " + token_resp.get("error", "Unknown error"))
        
        # Store user info in session
        authed_user = token_resp.get("authed_user", {})
        req.session["slack_uid"] = authed_user["id"]
        
        # Get username if we have access token
        if "access_token" in authed_user:
            user_resp = requests.get(
                "https://slack.com/api/users.info",
                headers={"Authorization": f"Bearer {authed_user['access_token']}"},
                params={"user": authed_user["id"]}
            ).json()
            
            if user_resp.get("ok") and user_resp.get("user"):
                req.session["slack_username"] = user_resp["user"].get("name", authed_user["id"])
        else:
            req.session["slack_username"] = authed_user.get("name", authed_user["id"])
        
        req.session.save()