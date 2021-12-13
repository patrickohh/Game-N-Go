from google.cloud import datastore
from flask import Flask, request
import json
import constants
import games
import stores
import user

app = Flask(__name__)
app.register_blueprint(games.bp)
app.register_blueprint(stores.bp)
app.register_blueprint(user.bp)

app.secret_key = constants.SECRET_KEY
user.oauth.init_app(app)

@app.route('/')
def index():
    return "Please navigate to / to use this API"

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)