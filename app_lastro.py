import os,json,secrets,sqlite3,uuid,re
from functools import wraps
from datetime import datetime,timedelta
from pathlib import Path
from flask import Flask,request,session,redirect,url_for,render_template_string,flash,send_from_directory,abort
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename

# Preserve the existing application implementation; only the login gate is patched below.
