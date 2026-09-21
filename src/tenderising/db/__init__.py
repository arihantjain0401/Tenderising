"""Database package: engine, session, and ORM models.

The DB is its own concern and must not know about MCP or HTTP. It is reached
only through the service layer (tenderising.service).
"""
