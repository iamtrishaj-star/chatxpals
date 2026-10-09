from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SubmitField


class ChatUploadForm(FlaskForm):
    """Form for uploading chat log export files with CSRF protection and validation."""
    chat_file = FileField(
        "Chat Log File (.txt)",
        validators=[
            FileRequired(message="Please select a .txt chat log file to upload."),
            FileAllowed(["txt"], message="Invalid file format. Only plain text (.txt) files are allowed.")
        ],
        description="Select a .txt chat export file (up to 2MB)"
    )
    submit = SubmitField("Summarize Chat")
