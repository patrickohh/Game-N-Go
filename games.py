from flask import Blueprint, request, jsonify, make_response
from google.cloud import datastore
import json
import constants
from user import verify_jwt, is_valid_JWT
import re

client = datastore.Client()

bp = Blueprint('games', __name__, url_prefix='/games')

@bp.route('', methods=['POST','GET', 'PATCH', 'DELETE'])
def games_get_post():
    # Request for adding a new game for rental
    if request.method == 'POST':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            # validate to see that post does not include id, stores, owner, or renters changes
            if 'id' in content or 'stores' in content or 'owner' in content or 'renters' in content:
                return jsonify({'Error':'Cannot post ID, stores, renters, or owner attributes of game'}), 400
            # if game with missing content is sent in the request body
            if error_missing_content_games(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if game contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for genre attribute of game
            if(regex.search(content['genre']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            # input validation for maturity rating attribute of game
            if(regex.search(content['rating']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            
            # input validation for length of game title, genre, rating, and publisher
            if ((len(content['title']) == 0) or (len(content['title']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['rating']) == 0) or (len(content['rating']) > 1)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['genre']) == 0) or (len(content['genre']) > 20)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['publisher']) == 0) or (len(content['publisher']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            
            # input validation for ratings attribute of game
            if maturity_rating_validation(content):
                return jsonify({'Error': 'The rating attribute of the game contains invalid characters. Allowed characters: C, E, T, M, A'}), 400

            # constraint maintenance for title of game
            query = client.query(kind=constants.games)
            results = list(query.fetch())
            for game in results:
                if content['title'] == game['title']:
                    return jsonify({'Error':'Title of game in request body is not unique'}), 403
                
            new_game = datastore.entity.Entity(key=client.key(constants.games))
            new_game.update({'title': content['title'], 'genre': content['genre'],
            'rating': content['rating'], 'publisher': content['publisher'], 'stores': [], 'renters': [], 'poster': payload['sub']})
            client.put(new_game)
            new_game['id'] = new_game.key.id
            new_game['self'] = request.base_url + '/' + str(new_game.key.id)
            res = make_response(json.dumps(new_game))
            res.mimetype = 'application/json'
            res.status_code = 201
            return res 
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    # Get list of games posted currently by user
    elif request.method == 'GET':
        payload = verify_jwt(request) 
        query = client.query(kind=constants.games)
        query.add_filter('poster', '=', payload['sub'])
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit= q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None

        if len(results) == 0:
            return jsonify({'Message': 'Currently no games posted under this user'}), 200

        for posted_game in results:
            posted_game['id'] = posted_game.key.id
            posted_game['self'] = request.base_url + "/" + str(posted_game.key.id)
            for store in posted_game['stores']:
                store['self'] = request.host_url + 'stores/' + str(store['id'])
            for renter in posted_game['renters']:
                renter['self'] = request.host_url + 'users/' + str(renter['id'])

        output = {'games': results}
        if next_url:
            output['next'] = next_url
        res = make_response(json.dumps(output))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res 
    # API does not allow delete list of games
    elif request.method == 'DELETE':
        return jsonify({'Error':'API does not support DELETE requests at this URL'}), 405
    # API does not allow edit list of games
    elif request.method == 'PUT':
        return jsonify({'Error':'API does not support PUT requests at this URL'}), 405
    else:
        return jsonify(error='Method not recogonized')

@bp.route('/<game_id>', methods=['DELETE', 'PATCH', 'PUT', 'GET'])
def games_delete_patch_put_get(game_id):
    # Request for deleting game
    if request.method == 'DELETE':
        payload = verify_jwt(request)
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)
        if game == None:
            return jsonify({"Error": "No game with this game_id exists"}), 404
        # If another user is trying to delete another user's game
        if game['poster'] != payload['sub']:
            return jsonify({'Error': 'Game with this id can only be deleted by its original poster'}), 403
        query = client.query(kind=constants.stores)
        results = list(query.fetch())
        if len(results) != 0:        
            for store in results:
                for i in range(len(store['games'])):                    
                    if store['games'][i]['id'] == int(game_id):
                        del store['games'][i]
                        client.put(store)        
        client.delete(game_key)
        return ('',204) 
    # Request for editing one attribute at a time   
    elif request.method == 'PATCH':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            game_key = client.key(constants.games, int(game_id))
            game = client.get(key=game_key)

            # validate to see that edit does not include id, stores, renters, or poster changes
            if 'id' in content or 'stores' in content or 'renters' in content or 'poster' in content:
                return jsonify({'Error':'Cannot edit ID, stores, renters, or poster attributes of game'}), 400

            # if game with missing content is sent in the request body
            if error_missing_content_games(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if game contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400

            # if game with specified game_id does not exist
            if game == None:
                return jsonify({'Error': 'No game with this game_id exists'}), 404
            # If another user is trying to patch another user's game
            if game['poster'] != payload['sub']:
                return jsonify({'Error': 'Game with this id can only be patched by its original poster'}), 403

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for genre attribute of game
            if(regex.search(content['genre']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            # input validation for maturity rating attribute of game
            if(regex.search(content['rating']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            
            # input validation for length of game title, genre, rating, and publisher
            if ((len(content['title']) == 0) or (len(content['title']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['rating']) == 0) or (len(content['rating']) > 1)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['genre']) == 0) or (len(content['genre']) > 20)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['publisher']) == 0) or (len(content['publisher']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            
            # input validation for ratings attribute of game
            if maturity_rating_validation(content):
                return jsonify({'Error': 'The rating attribute of the game contains invalid characters. Allowed characters: C, E, T, M, A'}), 400

            # validate to see if only one attribute is updated at a time
            if game['title'] != content['title'] and game['genre'] != content['genre'] and \
               game['rating'] != content['rating'] and game['publisher'] != game['publisher']:
                return jsonify({'Error':'API only allows one attribute to be edited at a time with PATCH request'}), 400
            elif (game['title'] != content['title'] and game['genre'] != content['genre']) or \
                 (game['title'] != content['title'] and game['rating'] != content['rating']) \
                 or (game['title'] != content['title'] and game['publisher'] != content['publisher']) \
                 or (game['rating'] != content['rating'] and game['publisher'] != content['publisher']) \
                 or (game['rating'] != content['rating'] and game['genre'] != content['genre']) \
                 or (game['publisher'] != content['publisher'] and game['genre'] != content['genre']):
                return jsonify({'Error': 'API only allows one attribute to be edited at a time with PATCH request'}), 400

            # constraint maintenance for title of game
            query = client.query(kind=constants.games)
            results = list(query.fetch())
            for game in results:
                if content['title'] == game['title']:
                    return jsonify({'Error':'Title of game in request body is not unique'}), 403

            if game['title'] != content['title']:
                game.update({'title': content['title']})
            elif game['genre'] != content['genre']:
                game.update({'genre': content['genre']})
            elif game['rating'] != content['rating']:
                game.update({'rating': content['rating']})
            elif game['publisher'] != content['publisher']:
                game.update({'publisher': content['publisher']})

            client.put(game)
            game['id'] = game.key.id
            game['self'] = constants.self_url_games + str(game.key.id)
            res = make_response(json.dumps(game))
            res.mimetype = 'application/json'
            res.status_code = 200
            return res
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    # Request for editing all attributes
    elif request.method == 'PUT':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            game_key = client.key(constants.games, int(game_id))
            game = client.get(key=game_key)

            # validate to see that edit does not include id, stores, renters, or poster changes
            if 'id' in content or 'stores' in content or 'renters' in content or 'poster' in content:
                return jsonify({'Error':'Cannot edit ID, stores, renters, or poster attributes of game'}), 400

            # if game with missing content is sent in the request body
            if error_missing_content_games(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if game contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400

            # if game with specified game_id does not exist
            if game == None:
                return jsonify({'Error': 'No game with this game_id exists'}), 404
            # If another user is trying to edit another user's game
            if game['poster'] != payload['sub']:
                return jsonify({'Error': 'Game with this id can only be edited by its original poster'}), 403

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for genre attribute of game
            if(regex.search(content['genre']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            # input validation for maturity rating attribute of game
            if(regex.search(content['rating']) != None):
                return jsonify({'Error':'Genre or rating of game contains characters that are not allowed'}), 400
            
            # input validation for length of game title, genre, rating, and publisher
            if ((len(content['title']) == 0) or (len(content['title']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['rating']) == 0) or (len(content['rating']) > 1)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['genre']) == 0) or (len(content['genre']) > 20)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            if ((len(content['publisher']) == 0) or (len(content['publisher']) > 30)):
                return jsonify({'Error':'Invalid size of game title, genre, rating, or publisher. Correct ranges: Title (0 < characters <= 30);'
                        ' Rating (0 < characters < 2); Genre (0 < characters <= 20); Publisher (0 < characters <= 30)'}), 400
            
            # input validation for ratings attribute of game
            if maturity_rating_validation(content):
                return jsonify({'Error': 'The rating attribute of the game contains invalid characters. Allowed characters: C, E, T, M, A'}), 400
            
            # constraint maintenance for title of game
            query = client.query(kind=constants.games)
            results = list(query.fetch())
            for game in results:
                if content['title'] == game['title']:
                    return jsonify({'Error':'Title of game in request body is not unique'}), 403

            game.update({'title': content['title'], 'genre': content['genre'],
            'publisher': content['publisher'], 'rating': content['rating']})
            client.put(game)
            game['id'] = game.key.id
            game['self'] = constants.self_url_games + str(game.key.id)
            res = make_response(json.dumps(game))
            res.mimetype = 'application/json'
            res.status_code = 303
            return res
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    elif request.method == 'GET':
        verify_jwt(request)  
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)
        if game == None:
            return jsonify({"Error": "No game with this game_id exists"}), 404
        game['id'] = game.key.id
        game['self'] = request.base_url 
        for store in game['stores']:
            store['self'] = request.host_url + "stores/" + str(store['id'])  
        res = make_response(json.dumps(game))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res
    else:
        return 'Method not recognized'

@bp.route('/<game_id>/stores/<store_id>', methods=['PUT', 'DELETE'])
def stores_games_assign(game_id, store_id):
    # Assign game to a store
    if request.method == 'PUT':
        payload = verify_jwt(request)
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)
        store_key = client.key(constants.stores, int(store_id))
        store = client.get(key=store_key)

        if game == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404
        if store == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404
        # If another user is trying to assign another user's game to a store
        if game['poster'] != payload['sub']:
            return jsonify({'Error': 'Game with this id can only be assigned to a store by its original poster'}), 403
        
        for i in range(len(game['stores'])):
            if game['stores'][i]['id'] == int(store_id):
                return jsonify({'Error': 'Game already assigned to this store'}), 400

        store['games'].append({'id': int(game.key.id)})        
        game['stores'].append({'id': int(store.id)})
        client.put(game)  
        client.put(store)      
        return('',200)
    # Un-assign a game to a store
    elif request.method == 'DELETE':
        payload = verify_jwt(request)
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)
        store_key = client.key(constants.stores, int(store_id))
        store = client.get(key=store_key)  
        if game == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404
        if store == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404

        # If another user is trying to un-assign another user's game to a store
        if game['poster'] != payload['sub']:
            return jsonify({'Error': 'Game with this id can only be un-assigned to a store by its original poster'}), 403  
        
        if len(game['stores']) == 0:
             return jsonify({'Message': 'Game is not assigned to store with store_id'}), 400

        for i in range(len(game['stores'])):            
            if game['stores'][i]['id'] == int(store_id):
                del game['stores'][i]
                client.put(game)
                for j in range(len(store['games'])):
                    if store['games'][j]['id'] == int(game_id):
                        del store['games'][j]
                client.put(store)
        

        return('',200)
    else:
        return 'Method not recognized'

@bp.route('/<game_id>/rent', methods=['PUT', 'DELETE'])
def games_rent(game_id):
    # Method when user is trying to rent a game
    if request.method == 'PUT':
        payload = verify_jwt(request)
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)

        if game == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404
        
        if len(game['stores']) == 0:
            return jsonify({'Error': 'Game is not found in any stores'}), 400
        for i in range(len(game['renters'])):
            if game['renters'][i]['id'] == payload['sub']:
                return jsonify({'Error': 'Already renting this game'}), 400
      
        game['renters'].append({'id': payload['sub']})
        client.put(game)  
        return('',200)
    # Method when user is done renting game
    elif request.method == 'DELETE':
        no_rents = 0
        payload = verify_jwt(request)
        game_key = client.key(constants.games, int(game_id))
        game = client.get(key=game_key)
 
        if game == None:
            return jsonify({'Error': 'No game with this game_id or store with store_id exists'}), 404 
        
        for i in range(len(game['renters'])):
            if game['renters'][i]['id'] != payload['sub']:
                no_rents = no_rents + 1

        if no_rents == len(game['renters']):    
            return jsonify({'Error': 'User not renting this game'}), 400
        
        for j in range(len(game['renters'])):
            if game['renters'][j]['id'] == payload['sub']:
                del game['renters'][j]

        client.put(game)
        return('',200)
    else:
        return 'Method not recognized'

# Function for error handling in case of request body for games having missing content
def error_missing_content_games(content):
    if 'title' not in content or 'genre' not in content or 'rating' not in content or 'publisher' not in content:
        return True
    else:
        return False

# function to validate if game contains a invalid attribute
def validation_non_valid_attributes(content):
    if 'title' in content and 'genre' in content and 'rating' in content and 'publisher' in content and(len(content) == 4):
        return True
    else:
        return False

# function for input validation of maturity rating 
def maturity_rating_validation(content):
    allowed_chars = 'CETMA'
    if content['rating'] not in allowed_chars:
        return True
    else:
        return False