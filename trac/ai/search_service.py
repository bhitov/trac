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

"""Fuzzy search service for finding tickets based on keywords."""

from trac.core import Component
from trac.ticket.model import Ticket
from trac.util.datefmt import format_datetime


class FuzzySearchService(Component):
    """Service to perform fuzzy searches on tickets and comments."""
    
    def get_total_ticket_count(self):
        """Get the total number of tickets in the system.
        
        Returns:
            int: Total ticket count
        """
        with self.env.db_query as db:
            for count, in db("SELECT COUNT(*) FROM ticket"):
                return count
        return 0
    
    def search_tickets(self, req, query, limit=20):
        """Search for tickets matching the query in summary or description.
        
        Args:
            req: The request object (for permission checking)
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of ticket dictionaries matching the search
        """
        if not query:
            return []
        
        tickets = []
        
        # Prepare search pattern for SQL LIKE
        # Split query into words and search for all of them
        search_terms = query.lower().split()
        
        # Build WHERE clause for searching
        where_conditions = []
        params = []
        
        for term in search_terms:
            like_pattern = f'%{term}%'
            where_conditions.append("(LOWER(summary) LIKE %s OR LOWER(description) LIKE %s)")
            params.extend([like_pattern, like_pattern])
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        sql = f"""
            SELECT id, summary, description, status, priority, owner,
                   component, milestone, time, changetime
            FROM ticket
            WHERE {where_clause}
            ORDER BY changetime DESC
            LIMIT %s
        """
        params.append(limit)
        
        with self.env.db_query as db:
            for row in db(sql, params):
                ticket_id = row[0]
                
                # Check permission
                ticket = Ticket(self.env, ticket_id)
                if 'TICKET_VIEW' in req.perm(ticket.resource):
                    tickets.append({
                        'id': ticket_id,
                        'summary': row[1],
                        'description': row[2],
                        'status': row[3],
                        'priority': row[4],
                        'owner': row[5],
                        'component': row[6],
                        'milestone': row[7],
                        'created': format_datetime(row[8], tzinfo=req.tz),
                        'modified': format_datetime(row[9], tzinfo=req.tz),
                        'relevance': self._calculate_relevance(row[1], row[2], search_terms)
                    })
        
        # Sort by relevance
        tickets.sort(key=lambda x: x['relevance'], reverse=True)
        
        return tickets
    
    def search_comments(self, req, query, limit=20):
        """Search for tickets with comments matching the query.
        
        Args:
            req: The request object
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of dictionaries with ticket and matching comment info
        """
        if not query:
            return []
        
        results = []
        search_terms = query.lower().split()
        
        # Build WHERE clause for comment search
        where_conditions = []
        params = []
        
        for term in search_terms:
            like_pattern = f'%{term}%'
            where_conditions.append("LOWER(tc.newvalue) LIKE %s")
            params.append(like_pattern)
        
        where_clause = " AND ".join(where_conditions)
        
        sql = f"""
            SELECT DISTINCT tc.ticket, t.summary, tc.time, tc.author, tc.newvalue,
                   t.status, t.priority, t.changetime
            FROM ticket_change tc
            JOIN ticket t ON tc.ticket = t.id
            WHERE tc.field = 'comment'
              AND tc.newvalue != ''
              AND {where_clause}
            ORDER BY tc.time DESC
            LIMIT %s
        """
        params.append(limit)
        
        with self.env.db_query as db:
            for row in db(sql, params):
                ticket_id = row[0]
                
                # Check permission
                ticket = Ticket(self.env, ticket_id)
                if 'TICKET_VIEW' in req.perm(ticket.resource):
                    results.append({
                        'ticket_id': ticket_id,
                        'summary': row[1],
                        'comment_time': format_datetime(row[2], tzinfo=req.tz),
                        'comment_author': row[3],
                        'comment_text': row[4],
                        'status': row[5],
                        'priority': row[6],
                        'modified': format_datetime(row[7], tzinfo=req.tz),
                        'relevance': self._calculate_relevance(row[1], row[4], search_terms)
                    })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        
        return results
    
    def combined_search(self, req, query, limit=20):
        """Perform a combined search on tickets and comments.
        
        Args:
            req: The request object
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            Dictionary with 'tickets' and 'comments' results
        """
        # Get half the limit for each type to balance results
        ticket_limit = limit // 2
        comment_limit = limit - ticket_limit
        
        tickets = self.search_tickets(req, query, ticket_limit)
        comments = self.search_comments(req, query, comment_limit)
        
        return {
            'tickets': tickets,
            'comments': comments,
            'total_results': len(tickets) + len(comments)
        }
    
    def _calculate_relevance(self, title, content, search_terms):
        """Calculate relevance score for search results.
        
        Args:
            title: Title/summary to search in
            content: Content/description to search in
            search_terms: List of search terms
            
        Returns:
            float: Relevance score (higher is more relevant)
        """
        score = 0.0
        title_lower = title.lower() if title else ''
        content_lower = content.lower() if content else ''
        
        for term in search_terms:
            # Title matches are worth more
            score += title_lower.count(term) * 2.0
            # Content matches
            score += content_lower.count(term) * 1.0
            
            # Exact word matches are worth more
            if f' {term} ' in f' {title_lower} ':
                score += 3.0
            if f' {term} ' in f' {content_lower} ':
                score += 1.5
        
        return score
    
    def format_search_results_for_context(self, req, query):
        """Format search results as context for the AI.
        
        Args:
            req: The request object
            query: The search query
            
        Returns:
            Formatted string with search results
        """
        results = self.combined_search(req, query)
        
        if results['total_results'] == 0:
            return f"No tickets or comments found matching '{query}'."
        
        context_parts = [f"Search results for '{query}':\n"]
        
        # Format ticket results
        if results['tickets']:
            context_parts.append(f"\nTickets matching '{query}' ({len(results['tickets'])} found):")
            for ticket in results['tickets']:
                ticket_info = f"""
Ticket #{ticket['id']}: {ticket['summary']}
Status: {ticket['status']} | Priority: {ticket['priority']} | Owner: {ticket['owner']}
Modified: {ticket['modified']}
Description excerpt: {ticket['description'][:200]}{'...' if len(ticket['description']) > 200 else ''}
"""
                context_parts.append(ticket_info)
        
        # Format comment results
        if results['comments']:
            context_parts.append(f"\nComments matching '{query}' ({len(results['comments'])} found):")
            for comment in results['comments']:
                comment_excerpt = comment['comment_text'][:200] + '...' if len(comment['comment_text']) > 200 else comment['comment_text']
                comment_info = f"""
Ticket #{comment['ticket_id']}: {comment['summary']}
Comment by {comment['comment_author']} on {comment['comment_time']}:
"{comment_excerpt}"
"""
                context_parts.append(comment_info)
        
        return "\n".join(context_parts)