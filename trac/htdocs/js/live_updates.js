/**
 * Live Updates for Trac Tickets
 * Polls the server for ticket changes and shows notifications
 * Integrated directly into Trac core
 */

(function($) {
    'use strict';
    
    // Configuration
    var POLL_INTERVAL = 5000; // 5 seconds
    var NOTIFICATION_DURATION = 8000; // 8 seconds
    
    var LiveUpdates = {
        ticketId: null,
        lastUpdate: 0,
        pollTimer: null,
        isPolling: false,
        
        init: function() {
            // Extract ticket ID from the current page URL
            var match = window.location.pathname.match(/\/ticket\/(\d+)/);
            if (!match) {
                return; // Not on a ticket page
            }
            
            this.ticketId = parseInt(match[1], 10);
            this.lastUpdate = Math.floor(Date.now() * 1000); // Current timestamp in microseconds (Trac format)
            
            // Create notification container if it doesn't exist
            this.createNotificationContainer();
            
            // Start polling
            this.startPolling();
            
            // Stop polling when page is hidden (performance optimization)
            $(document).on('visibilitychange', this.handleVisibilityChange.bind(this));
        },
        
        createNotificationContainer: function() {
            if ($('#live-updates-notifications').length === 0) {
                $('body').append(
                    '<div id="live-updates-notifications" style="' +
                    'position: fixed; top: 20px; right: 20px; z-index: 9999; ' +
                    'min-width: 300px; max-width: 400px;' +
                    '"></div>'
                );
            }
            
            // Add CSS for highlight animations if not already added
            if ($('#live-updates-styles').length === 0) {
                $('head').append(
                    '<style id="live-updates-styles">' +
                    '.live-update-highlight {' +
                    '  background-color: #ffffcc !important;' +
                    '  transition: background-color 0.3s ease;' +
                    '  border-radius: 3px;' +
                    '  box-shadow: 0 0 5px rgba(255, 255, 0, 0.5);' +
                    '}' +
                    '</style>'
                );
            }
        },
        
        startPolling: function() {
            if (this.isPolling) {
                return;
            }
            
            this.isPolling = true;
            this.pollForUpdates();
            this.pollTimer = setInterval(this.pollForUpdates.bind(this), POLL_INTERVAL);
        },
        
        stopPolling: function() {
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
            this.isPolling = false;
        },
        
        handleVisibilityChange: function() {
            if (document.hidden) {
                this.stopPolling();
            } else {
                this.startPolling();
            }
        },
        
        pollForUpdates: function() {
            var self = this;
            
            // Get the base URL from the current page
            var basePath = window.location.pathname.replace(/\/ticket\/\d+.*$/, '');
            
            $.ajax({
                url: basePath + '/ticket/' + this.ticketId + '/updates',
                type: 'GET',
                data: {
                    since: this.lastUpdate
                },
                dataType: 'json',
                timeout: 10000,
                success: function(data) {
                    self.handleUpdatesResponse(data);
                },
                error: function(xhr, status, error) {
                    console.warn('Live updates poll failed:', status, error);
                    // Don't show error notifications for polling failures
                    // to avoid spam, just log them
                }
            });
        },
        
        handleUpdatesResponse: function(data) {
            if (data.has_updates && data.changes && data.changes.length > 0) {
                // Update our last update timestamp
                this.lastUpdate = data.last_update;
                
                // Group changes by timestamp (changes made in the same save operation)
                var changeGroups = this.groupChangesByTime(data.changes);
                
                // Update page content, show notifications, and add to change history
                for (var timestamp in changeGroups) {
                    var changes = changeGroups[timestamp];
                    
                    // Update main content and show notifications
                    for (var i = 0; i < changes.length; i++) {
                        this.updatePageContent(changes[i]);
                        this.showNotification(changes[i]);
                    }
                    
                    // Add to change history if there are meaningful changes
                    this.addToChangeHistory(changes, timestamp);
                }
            }
        },
        
        groupChangesByTime: function(changes) {
            var groups = {};
            for (var i = 0; i < changes.length; i++) {
                var change = changes[i];
                var time = change.time;
                if (!groups[time]) {
                    groups[time] = [];
                }
                groups[time].push(change);
            }
            return groups;
        },
        
        addToChangeHistory: function(changes, timestamp) {
            var changelog = $('#changelog');
            if (changelog.length === 0) return;
            
            // Find comment and field changes
            var comment = null;
            var fieldChanges = [];
            
            for (var i = 0; i < changes.length; i++) {
                var change = changes[i];
                if (change.field === 'comment') {
                    comment = change;
                } else {
                    fieldChanges.push(change);
                }
            }
            
            // Only add if there's a comment or field changes
            if (!comment && fieldChanges.length === 0) return;
            
            // Get the next comment number
            var lastChangeId = $('.change[id*="trac-change-"]').last().attr('id') || 'trac-change-0-0';
            var commentNum = parseInt(lastChangeId.split('-')[2]) + 1;
            
            // Create the change entry
            var changeHtml = this.createChangeHistoryEntry(changes, timestamp, commentNum, comment, fieldChanges);
            
            // Add to changelog
            changelog.append(changeHtml);
            
            // Update the change count
            this.updateChangeCount();
            
            // Highlight the new change briefly
            var newChange = $('#trac-change-' + commentNum + '-' + timestamp);
            newChange.css('background-color', '#ffffcc').hide().fadeIn(500);
            setTimeout(function() {
                newChange.animate({'background-color': 'transparent'}, 1000);
            }, 2000);
        },
        
        createChangeHistoryEntry: function(changes, timestamp, commentNum, comment, fieldChanges) {
            var changeId = 'trac-change-' + commentNum + '-' + timestamp;
            var author = changes[0].author;
            var timeStr = changes[0].formatted_time;
            
            var html = '<div class="change" id="' + changeId + '">';
            
            // Header
            html += '<h3 class="change" id="comment:' + commentNum + '">';
            html += '<span class="threading"></span>';
            html += '<span class="cnum"><a href="#comment:' + commentNum + '" class="">comment:' + commentNum + '</a></span>';
            html += ' by <span class="trac-author">' + this.escapeHtml(author) + '</span>, ';
            html += '<span class="timeline">just now</span>';
            html += '</h3>';
            
            html += '<div class="trac-change-panel">';
            html += '<div class="trac-ticket-buttons"></div>';
            
            // Field changes table
            if (fieldChanges.length > 0) {
                html += '<table class="changes">';
                for (var i = 0; i < fieldChanges.length; i++) {
                    var change = fieldChanges[i];
                    html += '<tr>';
                    html += '<th id="comment:' + commentNum + ':' + change.field + '">';
                    html += '<em class="trac-field-' + change.field + '">' + this.escapeHtml(change.field) + '</em>';
                    html += '</th>';
                    html += '<td headers="comment:' + commentNum + ':' + change.field + '" class="trac-field-' + change.field + '">';
                    html += 'changed from <em>' + this.escapeHtml(change.oldvalue || '') + '</em> to <em>' + this.escapeHtml(change.newvalue || '') + '</em>';
                    html += '</td>';
                    html += '</tr>';
                }
                html += '</table>';
            }
            
            // Comment text
            if (comment && comment.newvalue) {
                html += '<div class="trac-ticket-description">';
                html += '<p>' + this.escapeHtml(comment.newvalue) + '</p>';
                html += '</div>';
            }
            
            html += '</div>'; // close trac-change-panel
            html += '</div>'; // close change
            
            return html;
        },
        
        updateChangeCount: function() {
            // Count only actual change history entries (those with trac-change-* ids)
            var changeCount = $('#changelog .change[id^="trac-change-"]').length;
            $('.trac-count').text('(' + changeCount + ')');
        },
        
        updatePageContent: function(change) {
            // Update the actual content on the page based on field changes
            switch (change.field) {
                case 'summary':
                    // Update the main title
                    $('#trac-ticket-title .summary').text(change.newvalue);
                    break;
                    
                case 'priority':
                    // Update priority in the table
                    $('td[headers="h_priority"] a').text(change.newvalue);
                    // Update the href to match new priority
                    var basePath = window.location.pathname.replace(/\/ticket\/\d+.*$/, '');
                    $('td[headers="h_priority"] a').attr('href', 
                        basePath + '/query?priority=' + encodeURIComponent(change.newvalue) + '&status=!closed');
                    break;
                    
                case 'status':
                    // Update status in the header
                    $('.trac-status a').text(change.newvalue);
                    var basePath = window.location.pathname.replace(/\/ticket\/\d+.*$/, '');
                    $('.trac-status a').attr('href', basePath + '/query?status=' + encodeURIComponent(change.newvalue));
                    break;
                    
                case 'owner':
                    // Update owner in the table
                    var ownerValue = change.newvalue || '< default >';
                    $('td[headers="h_owner"] a').text(ownerValue);
                    var basePath = window.location.pathname.replace(/\/ticket\/\d+.*$/, '');
                    $('td[headers="h_owner"] a').attr('href', 
                        basePath + '/query?owner=' + encodeURIComponent(ownerValue) + '&status=!closed');
                    break;
                    
                case 'component':
                    // Update component if it exists
                    $('td[headers="h_component"] a').text(change.newvalue || '');
                    break;
                    
                case 'milestone':
                    // Update milestone if it exists  
                    $('td[headers="h_milestone"]').text(change.newvalue || '');
                    break;
                    
                case 'comment':
                    // For comments, we could add them to the change log, but that's more complex
                    // For now, just note that there's a new comment
                    break;
            }
            
            // Add a subtle highlight animation to show what changed
            this.highlightFieldChange(change.field);
        },
        
        highlightFieldChange: function(fieldName) {
            var selector;
            switch (fieldName) {
                case 'summary':
                    selector = '#trac-ticket-title .summary';
                    break;
                case 'priority':
                    selector = 'td[headers="h_priority"]';
                    break;
                case 'status':
                    selector = '.trac-status';
                    break;
                case 'owner':
                    selector = 'td[headers="h_owner"]';
                    break;
                default:
                    return; // Don't highlight unknown fields
            }
            
            if (selector) {
                var $element = $(selector);
                if ($element.length > 0) {
                    // Add a temporary highlight class
                    $element.addClass('live-update-highlight');
                    
                    // Remove after animation
                    setTimeout(function() {
                        $element.removeClass('live-update-highlight');
                    }, 2000);
                }
            }
        },
        
        showNotification: function(change) {
            var message = this.formatChangeMessage(change);
            var notificationId = 'notification-' + Date.now() + '-' + Math.random();
            
            var notification = $(
                '<div id="' + notificationId + '" class="live-update-notification" style="' +
                'background: #4CAF50; color: white; padding: 12px; margin-bottom: 8px; ' +
                'border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.2); ' +
                'font-size: 14px; line-height: 1.4; opacity: 0; transform: translateX(100%); ' +
                'transition: all 0.3s ease;' +
                '">' +
                '<div style="font-weight: bold; margin-bottom: 4px;">Ticket Updated</div>' +
                '<div>' + this.escapeHtml(message) + '</div>' +
                '<div style="font-size: 12px; opacity: 0.8; margin-top: 4px;">' +
                'by ' + this.escapeHtml(change.author) + ' at ' + change.formatted_time +
                '</div>' +
                '</div>'
            );
            
            $('#live-updates-notifications').append(notification);
            
            // Animate in
            setTimeout(function() {
                notification.css({
                    opacity: 1,
                    transform: 'translateX(0)'
                });
            }, 50);
            
            // Auto-remove after duration
            setTimeout(function() {
                notification.css({
                    opacity: 0,
                    transform: 'translateX(100%)'
                });
                setTimeout(function() {
                    notification.remove();
                }, 300);
            }, NOTIFICATION_DURATION);
        },
        
        formatChangeMessage: function(change) {
            if (change.field === 'comment') {
                return 'New comment added';
            } else if (change.field === 'status') {
                return 'Status changed from "' + (change.oldvalue || '') + '" to "' + (change.newvalue || '') + '"';
            } else if (change.field === 'summary') {
                return 'Summary updated';
            } else if (change.field === 'description') {
                return 'Description updated';
            } else if (change.field === 'owner') {
                return 'Owner changed to "' + (change.newvalue || 'none') + '"';
            } else if (change.field === 'priority') {
                return 'Priority changed to "' + (change.newvalue || '') + '"';
            } else {
                return 'Field "' + change.field + '" updated';
            }
        },
        
        escapeHtml: function(text) {
            if (!text) return '';
            return text.replace(/[&<>"']/g, function(char) {
                var escapeMap = {
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#x27;'
                };
                return escapeMap[char];
            });
        }
    };
    
    // Initialize when document is ready
    $(document).ready(function() {
        LiveUpdates.init();
    });
    
    // Expose for testing
    window.TracLiveUpdates = LiveUpdates;
    
})(jQuery);
