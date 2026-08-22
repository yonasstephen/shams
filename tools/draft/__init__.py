"""Live draft assistant: normalized draft state, valuation, and recommendations.

The Chrome extension reads Yahoo's draft-room Redux store and POSTs the whole
state on every change. Everything here is pure computation over that payload —
no Yahoo API calls, no network, no clock. That keeps the draft path fast and
makes the whole engine testable from a JSON fixture.

See ``docs/draft-room-recon.md`` for the store's shape.
"""
