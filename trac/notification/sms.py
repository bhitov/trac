# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 Edgewall Software
# All rights reserved.

from trac.core import Component, ExtensionPoint, implements
from trac.config import BoolOption, Option
from trac.notification.api import (INotificationDistributor,
                                   INotificationFormatter)
from trac.util.translation import _
from trac.web.session import get_session_attribute


class SmsDistributor(Component):
    """Send SMS notifications via Twilio."""

    implements(INotificationDistributor)

    formatters = ExtensionPoint(INotificationFormatter)

    sms_enabled = BoolOption('notification', 'sms_enabled', 'false',
        """Enable SMS notifications.""")

    twilio_account_sid = Option('notification', 'twilio_account_sid', '',
        """Twilio Account SID.""")

    twilio_auth_token = Option('notification', 'twilio_auth_token', '',
        """Twilio Auth Token.""")

    twilio_from_number = Option('notification', 'twilio_from_number', '',
        """Twilio phone number to send SMS from.""")

    def __init__(self):
        self._twilio_client = None

    @property
    def twilio_client(self):
        """Lazy initialization of Twilio client."""
        if self._twilio_client is None:
            try:
                from twilio.rest import Client
                self._twilio_client = Client(self.twilio_account_sid,
                                           self.twilio_auth_token)
            except ImportError:
                self.log.error("Twilio library not installed. Run: pip install twilio")
                return None
            except Exception as e:
                self.log.error("Failed to initialize Twilio: %s", e)
                return None
        return self._twilio_client

    def transports(self):
        yield 'sms'

    def distribute(self, transport, recipients, event):
        if transport != 'sms':
            return
        if not self.sms_enabled:
            return
        if not self.twilio_client:
            return

        # Get SMS formatter
        formatter = None
        for f in self.formatters:
            for style, realm in f.get_supported_styles(transport):
                if realm == event.realm:
                    formatter = f
                    break
            if formatter:
                break

        if not formatter:
            self.log.error("No SMS formatter found")
            return

        # Send to each recipient
        for sid, auth, phone, fmt in recipients:
            if not phone:
                phone = get_session_attribute(self.env, sid, auth, 'phone_number')

            if not phone:
                continue

            # Format and send message
            try:
                message = formatter.format(transport, 'text/plain', event)
                if message:
                    self._send_sms(phone, message)
            except Exception as e:
                self.log.error("Failed to send SMS to %s: %s", phone, e)

    def _send_sms(self, phone, message):
        """Send SMS via Twilio."""
        # Ensure phone number has + prefix for international format
        if not phone.startswith('+'):
            phone = '+' + phone
            
        try:
            result = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_from_number,
                to=phone
            )
            # Only log success after we get a successful response
            self.log.info("SMS sent to %s (SID: %s, Status: %s)", 
                         phone, result.sid, result.status)
        except Exception as e:
            self.log.error("Twilio SMS failed for %s: %s", phone, e)
            # Re-raise to ensure caller knows it failed
            raise


class SmsFormatter(Component):
    """Format ticket events for SMS."""

    implements(INotificationFormatter)

    def get_supported_styles(self, transport):
        if transport == 'sms':
            yield ('text/plain', 'ticket')

    def format(self, transport, style, event):
        if transport != 'sms':
            return None

        ticket = event.target

        if event.category == 'created':
            return f"New ticket #{ticket.id}: {ticket['summary']}"

        elif event.category == 'changed':
            message = f"Ticket #{ticket.id} updated: {ticket['summary']}"

            # Add field changes
            if 'fields' in event.changes:
                changes = []
                for field, values in event.changes['fields'].items():
                    changes.append(f"{field}: {values['new']}")
                if changes:
                    message += f" ({', '.join(changes)})"

            return message

        return None