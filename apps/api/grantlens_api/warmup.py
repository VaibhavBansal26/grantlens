"""Do the slow first-time work before a worker takes traffic, so no user waits for it."""
from flask import Flask


def warm_up(app: Flask) -> None:
    from .retrieval import embedder, lexical

    with app.app_context():
        lexical.get_index()  # builds the keyword index over the whole corpus
        embedder.embed_query("warm up")  # loads the embedding model
