import logging
from flask import Blueprint, render_template, request, jsonify
from werkzeug.utils import secure_filename
from app.forms import ChatUploadForm
from app.utils import sanitize_chat_text, process_chat_log

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET"])
def index():
    """Render the main landing page with the upload form."""
    form = ChatUploadForm()
    return render_template("index.html", form=form)


@main_bp.route("/api/summarize", methods=["POST"])
async def summarize():
    """
    API endpoint to accept and summarize a .txt chat log export.
    Validates CSRF, enforces .txt file type, sanitizes content against XSS,
    and invokes Gemini API via google-generativeai SDK.
    Returns 500 error if Gemini processing fails.
    """
    form = ChatUploadForm()

    # Form and CSRF validation
    if not form.validate():
        errors = []
        for field_name, field_errors in form.errors.items():
            for err in field_errors:
                errors.append(f"{err}")
        return jsonify({
            "error": "Validation failed",
            "details": errors
        }), 400

    uploaded_file = form.chat_file.data
    filename = secure_filename(uploaded_file.filename)

    # Validate file extension
    if not filename.lower().endswith(".txt"):
        return jsonify({
            "error": "Invalid file format",
            "details": ["Only plain text (.txt) files are accepted."]
        }), 400

    # Read file content safely
    try:
        raw_bytes = uploaded_file.read()
    except Exception as e:
        return jsonify({
            "error": "File read error",
            "details": [f"Unable to read uploaded file: {str(e)}"]
        }), 400

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        return jsonify({
            "error": "Empty file",
            "details": ["The uploaded chat log is empty. Please provide a file with chat messages."]
        }), 400

    # Safe UTF-8 decoding with fallback
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = raw_bytes.decode("utf-8", errors="replace")

    # Sanitize content to prevent XSS
    sanitized_text = sanitize_chat_text(raw_text)

    # Call Gemini API via process_chat_log without any mock fallbacks
    try:
        result = await process_chat_log(sanitized_text)
    except Exception as exc:
        logger.exception("Gemini API call failed during chat log processing")
        return jsonify({
            "error": "Gemini API processing failed",
            "message": str(exc),
            "error_type": exc.__class__.__name__
        }), 500

    # Return expected JSON response with exact required keys
    return jsonify({
        "summary": result["summary"],
        "action_items": result["action_items"],
        "mentions": result["mentions"]
    }), 200
