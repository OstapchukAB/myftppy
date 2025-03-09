import os
import json
import logging
import traceback
from flask import Flask, render_template, request, session, send_file, redirect
from ftplib import FTP, error_perm
from io import BytesIO
from datetime import datetime
import zipfile
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = os.urandom(24)
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ftp_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parse_ftp_list(line):
    parts = line.split(maxsplit=8)
    if len(parts) < 9:
        return None
    
    perm = parts[0]
    name = parts[8].rstrip()
    is_dir = perm.startswith('d')
    size = int(parts[4])
    date_str = ' '.join(parts[5:8])
    
    try:
        mtime = datetime.strptime(date_str, '%b %d %H:%M')
        mtime = mtime.replace(year=datetime.now().year)
    except ValueError:
        try:
            mtime = datetime.strptime(date_str, '%b %d %Y')
        except:
            mtime = datetime.now()
    
    return {
        'name': name,
        'is_dir': is_dir,
        'size': size,
        'mtime': mtime.strftime('%Y-%m-%d %H:%M'),
        'type': 'Folder' if is_dir else 'File'
    }

def human_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def connect_ftp(host, username, password):
    try:
        logger.info(f"Connecting to FTP: {host}")
        ftp = FTP(host, timeout=10)
        ftp.login(username, password)
        return ftp
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        raise

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session['ftp_host'] = request.form.get('host')
        session['ftp_user'] = request.form.get('username')
        session['ftp_pass'] = request.form.get('password')
        return redirect('/files')
    
    config = load_config()
    return render_template('index.html', config=config)

@app.route('/files', defaults={'path': ''})
@app.route('/files/<path:path>')
def list_files(path):
    try:
        ftp = connect_ftp(
            session.get('ftp_host'),
            session.get('ftp_user'),
            session.get('ftp_pass')
        )
        
        files = []
        try:
            ftp.cwd(path)
            lines = []
            ftp.retrlines('LIST', lambda x: lines.append(x))
            
            for line in lines:
                item = parse_ftp_list(line)
                if item:
                    item['size_h'] = human_size(item['size']) if not item['is_dir'] else ''
                    files.append(item)
        except error_perm as e:
            logger.error(f"Directory error: {str(e)}")
        
        current_dir = ftp.pwd()
        ftp.quit()
        
        return render_template('files.html', 
                            files=files,
                            current_dir=current_dir,
                            parent_dir=os.path.dirname(current_dir))
    
    except Exception as e:
        logger.error(f"Error: {traceback.format_exc()}")
        return f"Error: {str(e)}", 500

@app.route('/download', methods=['POST'])
def download_files():
    selected_files = request.form.getlist('files')
    if not selected_files:
        return "No files selected", 400
    
    try:
        ftp = connect_ftp(
            session.get('ftp_host'),
            session.get('ftp_user'),
            session.get('ftp_pass')
        )
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in selected_files:
                with BytesIO() as bio:
                    ftp.retrbinary(f'RETR {filename}', bio.write)
                    bio.seek(0)
                    zipf.writestr(filename, bio.getvalue())
        
        ftp.quit()
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='ftp_files.zip'
        )
    
    except Exception as e:
        logger.error(f"Download failed: {traceback.format_exc()}")
        return f"Download error: {str(e)}", 500

def load_config():
    try:
        with open('config.json') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "host": "ftp.dlptest.com",
            "username": "dlpuser",
            "password": "rNrKYTX9g7z3RgJBmxUyhC2m"
        }

if __name__ == '__main__':
    app.run(debug=True)