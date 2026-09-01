"""Public campus content: how it is described, fetched, parsed, and indexed.

The four campus MCP servers in :mod:`app.campus.catalog` answer questions about
*this student*. Nothing in them answers "when is Add-Drop", "is the pool open",
or "how do I join meturoam", because those live on public METU websites that no
student credential unlocks and no single scraper covers.

This package is the other half of the environment. A source is a row
(:class:`app.db.models.CampusSource`), an adapter is a parser selected by that
row, and the result is documents in one searchable corpus. Admins add sources;
nobody deploys to cover a new department.
"""
