import logging
from datetime import datetime
import traceback
import os
import json
from flask import Flask, render_template, request, session, send_file, redirect
from ftplib import FTP, error_perm
from io import BytesIO
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("ftp_client.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
load_dotenv()

# Конфигурация по умолчанию
DEFAULT_CONFIG = {"host": "ftp.example.com", "username": "anonymous", "password": ""}


def load_config():
    try:
        with open("config.json") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_CONFIG


def connect_ftp(host, username, password):
    try:
        logger.info(f"Connecting to FTP: {host} (user: {username})")
        ftp = FTP()
        ftp.connect(host)
        ftp.login(username, password)
        logger.info("FTP connection successful")
        return ftp
    except Exception as e:
        logger.error(f"FTP connection failed: {str(e)}")
        raise


@app.route("/", methods=["GET", "POST"])
def index():
    logger.info("Accessing main page")
    config = load_config()

    if request.method == "POST":
        session["ftp_host"] = request.form.get("host")
        session["ftp_user"] = request.form.get("username")
        session["ftp_pass"] = request.form.get("password")
        logger.info(
            f"Login attempt - host: {session['ftp_host']}, user: {session['ftp_user']}"
        )
        # Пароль специально не логируем!
        return redirect("/files")
    else:
        return render_template("index.html", config=config)


@app.route("/files")
def list_files():
    try:
        logger.info("Accessing files page")
        ftp = connect_ftp(
            session.get("ftp_host"), session.get("ftp_user"), session.get("ftp_pass")
        )
        files = []
        ftp.retrlines("LIST", lambda x: files.append(x.split()[-1]))
        ftp.quit()
        logger.info(f"Found {len(files)} files")
        return render_template("files.html", files=files)
    except error_perm as e:
        logger.error(f"Permission error: {str(e)}")
        return f"Ошибка подключения: {str(e)}", 400
    except Exception as e:
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        return f"Ошибка подключения: {str(e)}"


@app.route("/download", methods=["POST"])
def download_files():
    selected_files = request.form.getlist("files")
    logger.info(f"Download request: {len(selected_files)} files selected")

    if not selected_files:
        return "Файлы не выбраны", 400

    try:
        ftp = connect_ftp(
            session.get("ftp_host"), session.get("ftp_user"), session.get("ftp_pass")
        )
        logger.debug(f"Downloading files: {selected_files}")

        zip_io = BytesIO()

        for file in selected_files:
            bio = BytesIO()
            ftp.retrbinary(f"RETR {file}", bio.write)
            bio.seek(0)
            zip_io.write(bio.read())
        logger.info("Files successfully packed into ZIP")

        ftp.quit()
        zip_io.seek(0)

        return send_file(
            zip_io,
            mimetype="application/zip",
            as_attachment=True,
            download_name="downloaded_files.zip",
        )
    except error_perm as e:
        logger.error(f"Permission error: {str(e)}")
        return f"Ошибка загрузки: {str(e)}", 400
    except Exception as e:
        logger.error(f"Download failed: {traceback.format_exc()}")
        return f"Ошибка : {str(e)}"


if __name__ == "__main__":
    app.run(debug=True)
