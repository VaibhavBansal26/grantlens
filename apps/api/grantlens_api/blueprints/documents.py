import os
from dataclasses import asdict
from datetime import UTC, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from .. import docqa, usage
from ..extensions import db, limiter
from ..llm import LLMError, LLMNotConfigured, get_llm
from ..models import DocChunk, Document
from ..retrieval import embedder
from .auth import login_required

bp = Blueprint("documents", __name__, url_prefix="/documents")
MAX_DOCS = 10
MAX_BYTES = 15 * 1024 * 1024
MAX_QUESTION = 500


def _mine(doc_id: int) -> Document | None:
    return Document.query.filter_by(id=doc_id, user_id=g.user.id).first()


def _view(d: Document) -> dict:
    days = current_app.config["RETENTION_DOCUMENT_DAYS"]
    created = d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=UTC)
    return {"id": d.id, "title": d.title, "pages": d.page_count, "created_at": d.created_at.isoformat(),
            "expires_at": (created + timedelta(days=days)).isoformat() if days > 0 else None}


@bp.get("")
@login_required
def list_documents():
    docs = Document.query.filter_by(user_id=g.user.id).order_by(Document.created_at.desc())
    return jsonify(documents=[_view(d) for d in docs])


@bp.post("")
@limiter.limit("20/hour")
@login_required
def upload():
    file = request.files.get("file")
    if file is None:
        return jsonify(error="attach a PDF as the 'file' field"), 400
    if Document.query.filter_by(user_id=g.user.id).count() >= MAX_DOCS:
        return jsonify(error=f"limit of {MAX_DOCS} documents reached; delete one first"), 409
    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return jsonify(error=f"PDFs are limited to {MAX_BYTES // (1024 * 1024)} MB"), 413
    try:
        pages = docqa.extract_pages(data)
    except docqa.PdfError as e:
        return jsonify(error=str(e)), 400
    pieces = docqa.chunk_pages(pages)
    vectors = embedder.embed_documents([text for _, text in pieces])
    title = os.path.splitext(os.path.basename(file.filename or "document"))[0][:255] or "document"
    doc = Document(user_id=g.user.id, title=title, page_count=len(pages))
    db.session.add(doc)
    db.session.flush()
    db.session.add_all(
        DocChunk(document_id=doc.id, idx=i, page=page, text=text, embedding=vec)
        for i, ((page, text), vec) in enumerate(zip(pieces, vectors, strict=True))
    )
    db.session.commit()
    return jsonify({**_view(doc), "chunks": len(pieces)}), 201


@bp.delete("/<int:doc_id>")
@login_required
def delete(doc_id: int):
    doc = _mine(doc_id)
    if doc is None:
        return jsonify(error="not found"), 404
    DocChunk.query.filter_by(document_id=doc.id).delete()
    db.session.delete(doc)
    db.session.commit()
    return "", 204


@bp.post("/<int:doc_id>/ask")
@limiter.limit("10/minute")
@login_required
def ask(doc_id: int):
    doc = _mine(doc_id)
    if doc is None:
        return jsonify(error="not found"), 404
    question = str((request.get_json(silent=True) or {}).get("question", "")).strip()
    if not question or len(question) > MAX_QUESTION:
        return jsonify(error=f"ask a question of up to {MAX_QUESTION} characters"), 400
    try:
        llm = get_llm(current_app.config)
    except LLMNotConfigured as e:
        return jsonify(error=str(e)), 503
    if not usage.consume(g.user.id):
        return jsonify(error="you have reached today's limit of AI requests; try again tomorrow"), 429
    chunks = DocChunk.query.filter_by(document_id=doc.id).order_by(DocChunk.idx).all()
    excerpts = docqa.retrieve(question, chunks, embedder.embed_query)
    try:
        result = docqa.ask(question, excerpts, llm)
    except LLMError as e:
        usage.refund(g.user.id)  # a failed call produced nothing, so it shouldn't use up the allowance
        return jsonify(error=str(e)), 502
    return jsonify(
        answer=result.answer, supported=result.supported, removed_citations=result.removed,
        citations=[asdict(c) for c in result.citations],
    )
