from flask import Blueprint, request, jsonify, make_response
from google.cloud import datastore
import json
import constants
from user import verify_jwt, is_valid_JWT
import re

client = datastore.Client()

bp = Blueprint('stores', __name__, url_prefix='/stores')

@bp.route('', methods = ['POST','GET','PATCH','DELETE'])
def stores_get_post():
    # Request for adding a new store
    if request.method == 'POST':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            # validate to see that post does not include id, games, or owner attributes
            if 'id' in content or 'games' in content or 'owner' in content:
                return jsonify({'Error':'Cannot post ID, games, or owner attributes of store'}), 400
            # if store with missing content is sent in the request body
            if error_missing_content_stores(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if store contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for location attribute of store
            if(regex.search(content['location']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            # input validation for type attribute of store
            if(regex.search(content['type']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            
            # input validation for length of store name, location, and type
            if ((len(content['name']) == 0) or (len(content['name']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['location']) == 0) or (len(content['location']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['type']) == 0) or (len(content['type']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400

            # constraint maintenance for name of store
            query = client.query(kind=constants.stores)
            results = list(query.fetch())
            for store in results:
                if content['name'] == store['name']:
                    return jsonify({'Error':'Name of store in request body is not unique'}), 403
                
            new_store = datastore.entity.Entity(key=client.key(constants.stores))
            new_store.update({'name': content['name'], 'location': content['location'],
            'type': content['type'], 'owner': payload['sub'], 'games': []})
            client.put(new_store)
            new_store['id'] = new_store.key.id
            new_store['self'] = request.base_url + '/' + str(new_store.key.id)
            res = make_response(json.dumps(new_store))
            res.mimetype = 'application/json'
            res.status_code = 201
            return res 
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    # Get list of stores owned currently by user
    elif request.method == 'GET':
        payload = verify_jwt(request)
        query = client.query(kind=constants.stores)
        query.add_filter('owner', '=', payload['sub'])
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
            return jsonify({'Message': 'Currently owning no stores under this user'}), 200

        for owned_store in results:
            owned_store['id'] = owned_store.key.id
            owned_store['self'] = request.base_url + "/" + str(owned_store.key.id)
            for game in owned_store['games']:
                game['self'] = request.host_url + 'games/' + str(game['id'])

        output = {'stores': results}
        if next_url:
            output['next'] = next_url
        res = make_response(json.dumps(output))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res 
    # API does not allow delete list of stores
    elif request.method == 'DELETE':
        return jsonify({'Error':'API does not support DELETE requests at this URL'}), 405
    # API does not allow edit list of stores
    elif request.method == 'PUT':
        return jsonify({'Error':'API does not support PUT requests at this URL'}), 405
    else:
        return jsonify(error='Method not recogonized')

@bp.route('/<store_id>', methods=['DELETE', 'PATCH', 'PUT', 'GET'])
def stores_delete_patch_put_get(store_id):
    # Request for deleting store
    if request.method == 'DELETE':
        payload = verify_jwt(request)
        store_key = client.key(constants.stores, int(store_id))
        store = client.get(key=store_key)
        if store == None:
            return jsonify({"Error": "No store with this store_id exists"}), 404
        # If another user is trying to delete another user's store
        if store['owner'] != payload['sub']:
            return jsonify({'Error': 'Store with this id can only be deleted by its original owner'}), 403
        query = client.query(kind=constants.games)
        results = list(query.fetch())
        if len(results) != 0:        
            for game in results:
                for i in range(len(game['stores'])):                    
                    if game['stores'][i]['id'] == int(store_id):
                        del game['stores'][i]
                        client.put(game)        
        client.delete(store_key)
        return ('',204)  
    # Request for editing one attribute of store  
    elif request.method == 'PATCH':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            store_key = client.key(constants.stores, int(store_id))
            store = client.get(key=store_key)

            # validate to see that edit does not include id, games, or owner changes
            if 'id' in content or 'games' in content or 'owner' in content:
                return jsonify({'Error':'Cannot edit ID, games, or owner attributes of store'}), 400

            # if store with missing content is sent in the request body
            if error_missing_content_stores(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if store contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400

            # if store with specified store_id does not exist
            if store == None:
                return jsonify({'Error': 'No store with this store_id exists'}), 404

            if store['owner'] != payload['sub']:
                return jsonify({'Error': 'Store with this id can only be patched by its original owner'}), 403

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for location attribute of store
            if(regex.search(content['location']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            # input validation for type attribute of store
            if(regex.search(content['type']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            
            # input validation for length of store name, location, and type
            if ((len(content['name']) == 0) or (len(content['name']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['location']) == 0) or (len(content['location']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['type']) == 0) or (len(content['type']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400

            # validate to see if only one attribute is updated at a time
            if store['name'] != content['name'] and store['location'] != content['location'] and \
               store['type'] != content['type']:
                return jsonify({'Error':'API only allows one attribute to be edited at a time with PATCH request'}), 400
            elif (store['name'] != content['name'] and store['location'] != content['location']) or \
                 (store['name'] != content['name'] and store['type'] != content['type']) \
                 or (store['type'] != content['type'] and store['location'] != content['location']):
                return jsonify({'Error': 'API only allows one attribute to be edited at a time with PATCH request'}), 400

            # constraint maintenance for name of store
            query = client.query(kind=constants.stores)
            results = list(query.fetch())
            for store in results:
                if content['name'] == store['name']:
                    return jsonify({'Error':'Name of store in request body is not unique'}), 403

            if store['name'] != content['name']:
                store.update({'name': content['name']})
            elif store['location'] != content['location']:
                store.update({'location': content['location']})
            elif store['type'] != content['type']:
                store.update({'type': content['type']})

            client.put(store)
            store['id'] = store.key.id
            store['self'] = constants.self_url_stores + str(store.key.id)
            res = make_response(json.dumps(store))
            res.mimetype = 'application/json'
            res.status_code = 200
            return res
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    # Request for editing all attribute of store  
    elif request.method == 'PUT':
        if 'application/json' in request.content_type:
            payload = verify_jwt(request)      
            content = request.get_json()
            store_key = client.key(constants.stores, int(store_id))
            store = client.get(key=store_key)

            # validate to see that edit does not include id, games, or owner changes
            if 'id' in content or 'games' in content or 'owner' in content:
                return jsonify({'Error':'Cannot edit ID, games, or owner attributes of store'}), 400

            # if store with missing content is sent in the request body
            if error_missing_content_stores(content):
                return jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400
                
            # if store contains a invalid attribute
            if validation_non_valid_attributes(content) == False:
                return jsonify({'Error': 'The request contains a invalid attribute'}), 400
 
            # if store with specified store_id does not exist
            if store == None:
                return jsonify({'Error': 'No store with this store_id exists'}), 404

            if store['owner'] != payload['sub']:
                return jsonify({'Error': 'Store with this id can only be edited by its original owner'}), 403

            # input validation for special characters for attributes of request body
            regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')
            # input validation for location attribute of store
            if(regex.search(content['location']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            # input validation for type attribute of store
            if(regex.search(content['type']) != None):
                return jsonify({'Error':'Location or type of store contains characters that are not allowed'}), 400
            
            # input validation for length of store name, location, and type
            if ((len(content['name']) == 0) or (len(content['name']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['location']) == 0) or (len(content['location']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400
            if ((len(content['type']) == 0) or (len(content['type']) > 15)):
                return jsonify({'Error':'Invalid size of store name, location, or type. Correct ranges: Name (0 < characters <= 15);'
                        ' Location (0 < characters < 15); Type (0 < characters <= 15)'}), 400

            # constraint maintenance for name of store
            query = client.query(kind=constants.stores)
            results = list(query.fetch())
            for store in results:
                if content['name'] == store['name']:
                    return jsonify({'Error':'Name of store in request body is not unique'}), 403
                    
            store.update({'name': content['name'], 'location': content['location'],'type': content['type']})
            client.put(store)
            store['id'] = store.key.id
            store['self'] = constants.self_url_stores + str(store.key.id)
            res = make_response(json.dumps(store))
            res.mimetype = 'application/json'
            res.status_code = 303
            return res
        else:
            return jsonify({'Error':'Not acceptable'}), 406
    # Request for getting store with store_id
    elif request.method == 'GET':
        verify_jwt(request)  
        store_key = client.key(constants.stores, int(store_id))
        store = client.get(key=store_key)
        if store == None:
            return jsonify({"Error": "No store with this store_id exists"}), 404
        store['id'] = store.key.id
        store['self'] = request.base_url 
        for game in store['games']:
            game['self'] = request.host_url + "games/" + str(game['id']) 
        res = make_response(json.dumps(store))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res 
    else:
        return 'Method not recognized'

# Function for error handling in case of request body for stores having missing content
def error_missing_content_stores(content):
    if 'name' not in content or 'location' not in content or 'type' not in content:
        return True
    else:
        return False

# function to validate if store contains a invalid attribute
def validation_non_valid_attributes(content):
    if 'name' in content and 'location' in content and 'type' in content and(len(content) == 3):
        return True
    else:
        return False
