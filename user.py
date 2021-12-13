from google.cloud import datastore
from flask import Flask, request, jsonify, _request_ctx_stack, make_response, redirect, render_template, Blueprint
import requests
import constants

from functools import wraps
import json

from six.moves.urllib.request import urlopen
from flask_cors import cross_origin
from jose import jwt

import json
from os import environ as env
from werkzeug.exceptions import HTTPException

from dotenv import load_dotenv, find_dotenv
from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import session
from flask import url_for
from authlib.integrations.flask_client import OAuth
from six.moves.urllib.parse import urlencode

bp = Blueprint('user', __name__, static_url_path='/public', static_folder='./public')

client = datastore.Client()

ALGORITHMS = ["RS256"]

oauth = OAuth()

auth0 = oauth.register(
    'auth0',
    client_id=constants.CLIENT_ID,
    client_secret=constants.CLIENT_SECRET,
    api_base_url="https://" + constants.DOMAIN,
    access_token_url="https://" + constants.DOMAIN + "/oauth/token",
    authorize_url="https://" + constants.DOMAIN + "/authorize",
    client_kwargs={
        'scope': 'openid profile email',
    },
)

# This code is adapted from https://auth0.com/docs/quickstart/backend/python/01-authorization?_ga=2.46956069.349333901.1589042886-466012638.1589042885#create-the-jwt-validation-decorator

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@bp.app_errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

# Wrapper that requires authorization token
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if constants.TOKEN not in session:
            return redirect('/login')
        return f(*args, **kwargs)

    return decorated

# Verify the JWT in the request's Authorization header
def verify_jwt(request):
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization'].split()
        token = auth_header[1]
    else:
        raise AuthError({"code": "no auth header",
                            "description":
                                "Authorization header is missing"}, 401)
    
    jsonurl = urlopen("https://"+ constants.DOMAIN+"/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.JWTError:
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Invalid header. "
                            "Use an RS256 signed JWT Access Token"}, 401)
    if unverified_header["alg"] == "HS256":
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Invalid header. "
                            "Use an RS256 signed JWT Access Token"}, 401)
    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=constants.CLIENT_ID,
                issuer="https://"+ constants.DOMAIN+"/"
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code": "token_expired",
                            "description": "token is expired"}, 401)
        except jwt.JWTClaimsError:
            raise AuthError({"code": "invalid_claims",
                            "description":
                                "incorrect claims,"
                                " please check the audience and issuer"}, 401)
        except Exception:
            raise AuthError({"code": "invalid_header",
                            "description":
                                "Unable to parse authentication"
                                " token."}, 401)

        return payload
    else:
        raise AuthError({"code": "no_rsa_key",
                            "description":
                                "No RSA key in JWKS"}, 401)

# Function to see if valid JWT is in use for CRUD operations
def is_valid_JWT(request):
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization'].split()
        token = auth_header[1]        
    else:
        return False
    
    jsonurl = urlopen("https://"+ constants.DOMAIN+"/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.JWTError:
        return False
    if unverified_header["alg"] == "HS256":
        return False
    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=constants.CLIENT_ID,
                issuer="https://"+ constants.DOMAIN+"/"
            )
        except jwt.ExpiredSignatureError:
            return False
        except jwt.JWTClaimsError:
            return False
        except Exception:
            return False

        return payload
    else:
        return False

# Home page
@bp.route('/')
def home():
    return render_template('home.html')

# Request to retrieve list of registered users
@bp.route('/users', methods = ['GET'])
def users_get():
    if request.method == 'GET':
        query = client.query(kind=constants.users)
        users = list(query.fetch())
        for person in users:
            person['id'] = person.key.name  
        res = make_response(json.dumps(users))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res 
    else:
        return jsonify(error='Method not recogonized')

# Retrieves authorization token and then redirects to user info page
@bp.route('/callback')
def callback_handling():
    token_res = auth0.authorize_access_token()
    token = token_res['id_token'] 
    info_res = auth0.get('userinfo')
    userinfo = info_res.json()

    session[constants.TOKEN] = token
    session[constants.INFO_KEY] = {
        'nickname': userinfo['nickname'],
        'email': userinfo['email'],
        'sub': userinfo['sub']
    }

    info_data = session[constants.INFO_KEY]
    query = client.query(kind=constants.users)
    query.add_filter('id', '=', info_data['sub'])
    users = list(query.fetch())
    if len(users) == 0:
        new_user = datastore.entity.Entity(key=client.key(constants.users, info_data['sub']))
        new_user.update({'name': info_data['nickname'], 'email': info_data['email']})
        client.put(new_user)
        new_user['id'] = new_user.key.id
        new_user['self'] = request.base_url + '/' + str(new_user.key.id)

    return redirect('/dashboard')

# When user presses login button on welcome page directs them to login and registration page
@bp.route('/login')
def login_user():
    return auth0.authorize_redirect(redirect_uri=constants.CALLBACK_URL)

# Route that logs out user and redirects to home page
@bp.route('/logout')
def logout():
    session.clear()
    params = {'returnTo': url_for('user.home',  _external=True), 'client_id': constants.CLIENT_ID}
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))

# Route to user info page
@bp.route('/dashboard')
@requires_auth
def dashboard():
    return render_template('dashboard.html', userinfo_pretty=session[constants.TOKEN], user_info=session[constants.INFO_KEY], indent=4)

if __name__ == '__main__':
    bp.run(host='127.0.0.1', port=8080, debug=True)