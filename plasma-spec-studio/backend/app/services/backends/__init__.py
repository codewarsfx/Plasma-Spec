"""Pluggable persistence backends (local SQLite vs. Supabase).

See ``base.py`` for the ``Store`` interface and the ambient
"current store" mechanism that lets the rest of the app call
``app.services.spectrum_service``/``recipe_service`` exactly as before
without knowing which backend is active.
"""
