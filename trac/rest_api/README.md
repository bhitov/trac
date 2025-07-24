# Trac REST API

This module provides a modern REST API for Trac, allowing programmatic access to Trac resources via JSON.

## Architecture

The REST API is built using a base handler pattern:

- **BaseRESTHandler** - Abstract base class providing common CRUD operations
- **Resource-specific handlers** - Extend the base class for each resource type (tickets, wiki, etc.)

## Current Implementation

### Tickets API

**Base URL**: `/api/ticket`

#### Endpoints

- `GET /api/ticket` - List tickets with optional filtering
  - Query parameters: `status`, `owner`, `milestone`, `component`, `limit`, `offset`
  
- `GET /api/ticket/{id}` - Get a specific ticket
  
- `POST /api/ticket` - Create a new ticket
  - Request body: JSON with ticket fields
  
- `PUT /api/ticket/{id}` - Update an existing ticket
  - Request body: JSON with fields to update
  
- `DELETE /api/ticket/{id}` - Delete a ticket (requires TICKET_ADMIN)

#### Example Usage

```bash
# List all tickets
curl http://localhost:8000/myproject/api/ticket

# Get ticket #1
curl http://localhost:8000/myproject/api/ticket/1

# Create a new ticket
curl -X POST http://localhost:8000/myproject/api/ticket \
  -H "Content-Type: application/json" \
  -d '{"summary": "New ticket", "description": "Description here"}'

# Update ticket #1
curl -X PUT http://localhost:8000/myproject/api/ticket/1 \
  -H "Content-Type: application/json" \
  -d '{"priority": "critical", "comment": "Updating priority"}'
```

### Wiki API

**Base URL**: `/api/wiki`

#### Endpoints

- `GET /api/wiki` - List all wiki pages
  - Query parameters: `limit`, `offset`
  
- `GET /api/wiki/{page_name}` - Get a specific wiki page
  
- `PUT /api/wiki/{page_name}` - Create or update a wiki page
  - Request body: JSON with `text` and optional `comment`
  
- `DELETE /api/wiki/{page_name}` - Delete a wiki page (requires WIKI_ADMIN)

- `GET /api/wiki/{page_name}/history` - Get page history
  
- `GET /api/wiki/{page_name}/versions/{version}` - Get specific version

#### Example Usage

```bash
# List all wiki pages
curl http://localhost:8000/myproject/api/wiki

# Get WikiStart page
curl http://localhost:8000/myproject/api/wiki/WikiStart

# Create a new wiki page
curl -X PUT http://localhost:8000/myproject/api/wiki/NewPage \
  -H "Content-Type: application/json" \
  -d '{"text": "= New Page =\n\nThis is a new wiki page.", "comment": "Created via API"}'

# Update existing page
curl -X PUT http://localhost:8000/myproject/api/wiki/WikiStart \
  -H "Content-Type: application/json" \
  -d '{"text": "Updated content", "comment": "Updated via API"}'

# Get page history
curl http://localhost:8000/myproject/api/wiki/WikiStart/history

# Get specific version
curl http://localhost:8000/myproject/api/wiki/WikiStart/versions/3
```

## Response Format

All successful responses return JSON with the requested data:

```json
{
  "id": 1,
  "summary": "Ticket summary",
  "status": "new",
  "priority": "major",
  "time_created": 1234567890,
  "time_changed": 1234567891
}
```

Error responses include an error object:

```json
{
  "error": {
    "code": 404,
    "message": "Ticket not found"
  }
}
```

## Permissions

The REST API respects Trac's permission system:

### Tickets API
- `TICKET_VIEW` - Required to list/view tickets
- `TICKET_CREATE` - Required to create tickets
- `TICKET_MODIFY` - Required to update tickets
- `TICKET_ADMIN` - Required to delete tickets

### Wiki API
- `WIKI_VIEW` - Required to list/view wiki pages
- `WIKI_CREATE` - Required to create new wiki pages
- `WIKI_MODIFY` - Required to update existing wiki pages
- `WIKI_ADMIN` - Required to delete wiki pages

## Adding New APIs

To add a new REST API endpoint:

1. Create a new handler class extending `BaseRESTHandler`
2. Implement the required abstract methods
3. Add routing in `handlers.py`
4. Add the module to `setup.cfg` entry points

Example:

```python
from trac.rest_api.base import BaseRESTHandler

class WikiAPI(BaseRESTHandler):
    @property
    def model_class(self):
        return WikiPage
    
    @property
    def resource_name(self):
        return 'WIKI'
    
    @property
    def collection_name(self):
        return 'pages'
    
    # Implement other required methods...
```

## Testing

Comprehensive tests are provided in the `tests/` directory:

```bash
python -m unittest discover -s trac/rest_api/tests
```