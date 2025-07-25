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

"""Context service that provides recent ticket data for AI chatbot."""

from trac.core import Component
from trac.ticket.model import Ticket
from trac.util.datefmt import format_datetime, user_time, utc


class ContextService(Component):
    """Service to fetch and format recent tickets for AI context."""
    
    def get_recent_tickets(self, req, limit=20):
        """Get the most recently modified tickets.
        
        Args:
            req: The request object (for permission checking)
            limit: Number of tickets to retrieve (default: 20)
            
        Returns:
            List of ticket dictionaries with relevant fields
        """
        tickets = []
        
        # Query for recent tickets ordered by changetime
        query = """
            SELECT id, summary, description, status, priority, owner, 
                   component, milestone, time, changetime
            FROM ticket
            ORDER BY changetime DESC
            LIMIT %s
        """
        
        with self.env.db_query as db:
            for row in db(query, (limit,)):
                ticket_id = row[0]
                
                # Check permission for this ticket
                ticket = Ticket(self.env, ticket_id)
                if 'TICKET_VIEW' in req.perm(ticket.resource):
                    # Use request timezone or UTC as fallback
                    tzinfo = getattr(req, 'tz', None) or utc
                    tickets.append({
                        'id': ticket_id,
                        'summary': row[1],
                        'description': row[2],
                        'status': row[3],
                        'priority': row[4],
                        'owner': row[5],
                        'component': row[6],
                        'milestone': row[7],
                        'created': format_datetime(row[8], tzinfo=tzinfo),
                        'modified': format_datetime(row[9], tzinfo=tzinfo)
                    })
        
        return tickets
    
    def get_recent_comments(self, req, ticket_ids, limit=10):
        """Get recent comments for the given tickets.
        
        Args:
            req: The request object
            ticket_ids: List of ticket IDs to get comments for
            limit: Max comments per ticket
            
        Returns:
            Dictionary mapping ticket_id to list of comments
        """
        if not ticket_ids:
            return {}
        
        comments = {}
        placeholders = ','.join(['%s'] * len(ticket_ids))
        
        query = f"""
            SELECT ticket, time, author, newvalue
            FROM ticket_change
            WHERE ticket IN ({placeholders})
              AND field = 'comment'
              AND newvalue != ''
            ORDER BY ticket, time DESC
        """
        
        params = list(ticket_ids)
        
        with self.env.db_query as db:
            current_ticket = None
            ticket_comments = []
            
            for row in db(query, params):
                ticket_id = row[0]
                
                # Check if we've moved to a new ticket
                if current_ticket != ticket_id:
                    if current_ticket is not None:
                        comments[current_ticket] = ticket_comments[:limit]
                    current_ticket = ticket_id
                    ticket_comments = []
                
                # Add comment if under limit
                if len(ticket_comments) < limit:
                    # Use request timezone or UTC as fallback
                    tzinfo = getattr(req, 'tz', None) or utc
                    ticket_comments.append({
                        'time': format_datetime(row[1], tzinfo=tzinfo),
                        'author': row[2],
                        'comment': row[3]
                    })
            
            # Don't forget the last ticket
            if current_ticket is not None:
                comments[current_ticket] = ticket_comments[:limit]
        
        return comments
    
    def format_tickets_for_context(self, req, include_comments=True, limit=20):
        """Format recent tickets into a context string for the AI.
        
        Args:
            req: The request object
            include_comments: Whether to include recent comments
            limit: Number of tickets to retrieve (default: 20)
            
        Returns:
            Formatted string containing ticket information
        """
        tickets = self.get_recent_tickets(req, limit)
        
        if not tickets:
            return "No tickets found in the system."
        
        # Get comments if requested
        comments = {}
        if include_comments:
            ticket_ids = [t['id'] for t in tickets]
            comments = self.get_recent_comments(req, ticket_ids)
        
        # Format the context
        context_parts = [f"Here are the {len(tickets)} most recently updated tickets:\n"]
        
        for ticket in tickets:
            # Handle None values safely
            description = ticket['description'] or ""
            summary = ticket['summary'] or f"Ticket #{ticket['id']}"
            status = ticket['status'] or "unknown"
            priority = ticket['priority'] or "unknown"
            owner = ticket['owner'] or "unassigned"
            component = ticket['component'] or "unknown"
            milestone = ticket['milestone'] or "none"
            
            ticket_info = f"""
Ticket #{ticket['id']}: {summary}
Status: {status} | Priority: {priority} | Owner: {owner}
Component: {component} | Milestone: {milestone}
Created: {ticket['created']} | Modified: {ticket['modified']}
Description: {description[:200]}{'...' if len(description) > 200 else ''}
"""
            
            # Add recent comments if available
            if ticket['id'] in comments and comments[ticket['id']]:
                ticket_info += "\nRecent comments:\n"
                for comment in comments[ticket['id']][:3]:  # Show up to 3 recent comments
                    comment_text = comment['comment'][:150] + '...' if len(comment['comment']) > 150 else comment['comment']
                    ticket_info += f"  - {comment['author']} ({comment['time']}): {comment_text}\n"
            
            context_parts.append(ticket_info)
        
        return "\n".join(context_parts)